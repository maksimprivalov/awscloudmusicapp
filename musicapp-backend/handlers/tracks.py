import json
import uuid
import traceback
from datetime import datetime
from boto3.dynamodb.conditions import Key, Attr
from utils.cors import response as cors_response, err
from utils.authz import is_admin
from utils.aws import s3, music_table, BUCKET

def get_upload_url(event, context):
    # только админ
    if not is_admin(event):
        return cors_response(403, {"error": "Admins only"})

    body = json.loads(event.get("body") or "{}")
    file_name = body.get("fileName")      # напр. "song.mp3"
    content_type = body.get("contentType","application/octet-stream")

    if not file_name:
        return cors_response(400, {"error": "fileName required"})

    content_id = str(uuid.uuid4())
    # кладём файлы в папку tracks/<contentId>/<originalName>
    s3_key = f"tracks/{content_id}/{file_name}"

    url = s3.generate_presigned_url(
        ClientMethod="put_object",
        Params={"Bucket": BUCKET, "Key": s3_key, "ContentType": content_type},
        ExpiresIn=3600
    )

    return cors_response(200, {"contentId": content_id, "s3Key": s3_key, "uploadUrl": url})

def create_content(event, context):
    # только админ
    if not is_admin(event):
        return cors_response(403, {"error": "Admins only"})

    body = json.loads(event.get("body") or "{}")
    content_id = body.get("contentId")
    s3_key = body.get("s3Key")
    name = body.get("name") 
    genres = body.get("genres", [])
    artists = body.get("artists", [])
    album_id = body.get("albumId")
    track_no = body.get("trackNo")

    if not content_id or not s3_key or not name:
        return cors_response(400, {"error": "contentId, s3Key, name required"})

    try:
        head = s3.head_object(Bucket=BUCKET, Key=s3_key)
        file_type = head.get("ContentType", "application/octet-stream")
        file_size = head["ContentLength"]
        last_modified = head["LastModified"].isoformat()
    except Exception as e:
        return cors_response(400, {"error": f"S3 object not found or not uploaded yet: {e}"})

    now = datetime.utcnow().isoformat()

    item = {
        "PK": f"CONTENT#{content_id}",
        "SK": "METADATA",
        "entityType": "TRACK",
        "contentId": content_id,
        "name": name,
        "fileName": s3_key.split("/")[-1],
        "fileType": file_type,
        "fileSize": file_size,
        "createdAt": now,
        "updatedAt": now,
        "fileLastModified": last_modified,
        "genres": genres,
        "artists": artists,
        "albumId": album_id,
        "s3Key": s3_key,
        "GSI1PK": f"GENRE#{genres[0]}" if genres else "GENRE#unknown",
        "GSI1SK": f"TRACK#{now}#{content_id}",
    }

    if album_id:
        item["GSI2PK"] = f"ALBUM#{album_id}"
        item["GSI2SK"] = f"TRACK#{str(track_no or 0).zfill(3)}"
    elif artists:
        item["GSI2PK"] = f"ARTIST#{artists[0]}"
        item["GSI2SK"] = f"TRACK#{now}"

    music_table.put_item(Item=item)
    return cors_response(201, {"message": "Content created", "contentId": content_id})

#                2) LIST / GET

def list_content(event, context):
    try:
        resp = music_table.scan(
            FilterExpression=Attr("PK").begins_with("CONTENT#")
        )
        items = resp.get("Items", [])

        for it in items:
            key = it.get("s3Key")
            if key:
                it["playUrl"] = s3.generate_presigned_url(
                    "get_object", Params={"Bucket": BUCKET, "Key": key}, ExpiresIn=3600
                )
            if "contentId" not in it and "PK" in it:
                it["contentId"] = it["PK"].split("#", 1)[1]

        return cors_response(200, items)

    except Exception as e:
        print("list_content ERROR:", traceback.format_exc())
        return cors_response(500, {"error": str(e)})

def get_content(event, context):
    content_id = (event.get("pathParameters") or {}).get("id")
    if not content_id:
        return cors_response(400, {"error": "id required"})

    resp = music_table.get_item(Key={"PK": f"CONTENT#{content_id}", "SK": "METADATA"})
    item = resp.get("Item")
    if not item:
        return cors_response(404, {"error": "Not found"})

    key = item.get("s3Key")
    if key:
        item["playUrl"] = s3.generate_presigned_url(
            "get_object", Params={"Bucket": BUCKET, "Key": key}, ExpiresIn=3600
        )
    return cors_response(200, item)

#                       3) Discover (GSI1)

def delete_content(event, context):
    if not is_admin(event):
        return cors_response(403, {"error": "Admins only"})
    content_id = (event.get("pathParameters") or {}).get("contentId")
    if not content_id:
        return cors_response(400, {"error": "contentId path param required"})

    pk = f"CONTENT#{content_id}"
    try:
        # obriši SVE stavke sa tim PK (npr. METADATA, eventualne dodatne SK-ove)
        to_delete = music_table.query(
            KeyConditionExpression=Key("PK").eq(pk)
        )["Items"]

        if not to_delete:
            return cors_response(404, {"error": "Content not found"})

        with music_table.batch_writer() as bw:
            for it in to_delete:
                bw.delete_item(Key={"PK": it["PK"], "SK": it["SK"]})

        return cors_response(200, {"message": "Track deleted", "contentId": content_id})
    except Exception as e:
        return err(500, "DDB delete failed", e)

def update_content(event, context):
    if not is_admin(event):
        return cors_response(403, {"error": "Admins only"})
    body = json.loads(event.get("body") or "{}")
    cid = (body.get("contentId") or "").strip()
    if not cid:
        return cors_response(400, {"error":"contentId required"})

    pk = f"CONTENT#{cid}"
    now = datetime.utcnow().isoformat()
    sets, ean, eav = ["#updatedAt=:now"], {"#updatedAt":"updatedAt"}, {":now": now}

    name   = body.get("name")
    artists = body.get("artists")
    genres = body.get("genres")
    addA = body.get("addArtists") or []
    remA = body.get("removeArtists") or []
    addG = body.get("addGenres") or []
    remG = body.get("removeGenres") or []

    # full replace
    if name is not None:
        ean["#name"]="name"; eav[":name"]=name; sets.append("#name=:name")
    if artists is not None:
        ean["#artists"]="artists"; eav[":artists"]=artists; sets.append("#artists=:artists")
    if genres is not None:
        ean["#genres"]="genres"; eav[":genres"]=genres; sets.append("#genres=:genres")

    # incremental (ako želiš)
    if addA or remA or addG or remG:
        # uzmi postojeći
        meta = music_table.get_item(Key={"PK": pk, "SK":"METADATA"}).get("Item") or {}
        curA = set(meta.get("artists", []))
        curG = set(meta.get("genres", []))
        curA |= set(addA); curA -= set(remA)
        curG |= set(addG); curG -= set(remG)
        ean["#artists"]="artists"; eav[":artists"]=list(curA); sets.append("#artists=:artists")
        ean["#genres"]="genres"; eav[":genres"]=list(curG); sets.append("#genres=:genres")

    music_table.update_item(
        Key={"PK": pk, "SK": "METADATA"},
        UpdateExpression="SET " + ", ".join(sets),
        ExpressionAttributeNames=ean,
        ExpressionAttributeValues=eav,
        ConditionExpression="attribute_exists(PK)"
    )

    return cors_response(200, {"message":"Content updated","contentId":cid})
