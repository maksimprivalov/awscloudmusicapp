import os, json, uuid, random, urllib.parse
import boto3
from datetime import datetime
from typing import Optional, Dict
from boto3.dynamodb.conditions import Key, Attr
from utils.cors import response as cors_response

# ===== AWS clients & env =====
s3 = boto3.client("s3")
dynamodb = boto3.resource("dynamodb")

TABLE_NAME = os.environ.get("TABLE_NAME", "Music")
music_table = dynamodb.Table(TABLE_NAME)

BUCKET = os.environ["BUCKET_NAME"]

# ===== helpers =====
def _is_admin(event):
    claims = (event.get("requestContext", {})
                    .get("authorizer", {})
                    .get("claims", {}))
    groups = claims.get("cognito:groups", "")
    return "Admin" in groups

def _encode_last_key(last_key: Optional[Dict]) -> Optional[str]:
    if not last_key:
        return None
    return urllib.parse.quote(json.dumps(last_key))

def _decode_last_key(s: Optional[str]) -> Optional[Dict]:
    if not s:
        return None
    try:
        return json.loads(urllib.parse.unquote(s))
    except Exception:
        return None

# =====================================================================
#                        1) ADMIN: upload flow
# =====================================================================
def get_upload_url(event, context):
    # только админ
    if not _is_admin(event):
        return cors_response(403, {"error": "Admins only"})

    body = json.loads(event.get("body") or "{}")
    file_name = body.get("fileName")      # напр. "song.mp3"
    content_type = body.get("contentType","application/octet-stream")

    if not file_name:
        return cors_response(400, {"error": "fileName required"})

    content_id = str(uuid.uuid4())
    # кладём файлы в папку tracks/<contentId>/<originalName>
    s3_key = f"tracks/{content_id}/{file_name}"

    # presigned URL на PUT (клиент загрузит файл напрямую)
    url = s3.generate_presigned_url(
        ClientMethod="put_object",
        Params={"Bucket": BUCKET, "Key": s3_key, "ContentType": content_type},
        ExpiresIn=3600
    )

    return cors_response(200, {"contentId": content_id, "s3Key": s3_key, "uploadUrl": url})

def create_content(event, context):
    # только админ
    if not _is_admin(event):
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

# =====================================================================
#                2) LIST / GET 
# =====================================================================
def list_content(event, context):
    # MVP: scan (позже лучше Query по индексам + пагинация)
    resp = music_table.scan(Limit=50)
    items = resp.get("Items", [])

    for it in items:
        key = it.get("s3Key")
        if key:
            it["playUrl"] = s3.generate_presigned_url(
                "get_object", Params={"Bucket": BUCKET, "Key": key}, ExpiresIn=3600
            )
    return cors_response(200, items)

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

# =====================================================================
#                       3) Discover (GSI1)
# =====================================================================
def discover(event, context):
    try:
        params = event.get("queryStringParameters") or {}
        genre = (params.get("genre") or "").strip().lower()
        typ = (params.get("type") or "").strip().upper()   # "ALBUM" | "ARTIST" | "" (оба)
        limit_str = params.get("limit") or "12"

        try:
            limit = max(1, min(int(limit_str), 50))
        except ValueError:
            limit = 12

        if not genre:
            return cors_response(400, {"message": "Missing required query param: genre"})

        prefix = "TYPE#"
        filter_expr = None
        if typ == "ALBUM":
            prefix = "TYPE#ALBUM"
        elif typ == "ARTIST":
            prefix = "TYPE#ARTIST"
        else:

            filter_expr = Attr("entityType").is_in(["ALBUM", "ARTIST"])

        last_key = _decode_last_key(params.get("lastKey"))

        query_kwargs = dict(
            IndexName="GSI1",
            KeyConditionExpression=Key("GSI1PK").eq(f"GENRE#{genre}") & Key("GSI1SK").begins_with(prefix),
            Limit=limit,
        )
        if last_key is not None:
            query_kwargs["ExclusiveStartKey"] = last_key
        if filter_expr is not None:
            query_kwargs["FilterExpression"] = filter_expr

        result = music_table.query(**query_kwargs)

        items = result.get("Items", [])
        lek = result.get("LastEvaluatedKey")

        out = []
        for x in items:
            pk = x.get("PK", "")
            _id = pk.split("#", 1)[1] if "#" in pk else pk
            out.append({
                "id": _id,
                "name": x.get("name"),
                "entityType": x.get("entityType"),
                "primaryGenre": x.get("primaryGenre"),
            })

        return cors_response(200, {"items": out, "nextKey": _encode_last_key(lek)})

    except Exception as e:
        import traceback
        print("discover ERROR:", traceback.format_exc())
        body = {"message": "Internal Server Error"}
        if os.environ.get("DEBUG") == "1":
            body["detail"] = str(e)
        return cors_response(500, body)

# =====================================================================
#                   4) Seed / Reset (admin)
# =====================================================================
def seed(event, context):
    import time, logging
    logging.getLogger().setLevel("INFO")

    try:
        genres = ["pop", "rock", "lofi", "rap", "jazz", "electronic", "metal", "folk"]

        body = {}
        if event.get("body"):
            try:
                body = json.loads(event["body"])
            except Exception:
                body = {}

        n_artists = int(body.get("artists", 5))
        n_albums = int(body.get("albums", 10))
        songs_per_album = int(body.get("songs_per_album", 5))

        def put_requests(items):
            return [{"PutRequest": {"Item": it}} for it in items]

        def write_batches(request_items):
            """Client-level BatchWrite с retry для UnprocessedItems"""
            client = boto3.client("dynamodb")
            unprocessed = {"RequestItems": {TABLE_NAME: request_items}}
            backoff = 0.2
            total_put = 0
            while unprocessed["RequestItems"][TABLE_NAME]:
                resp = client.batch_write_item(**unprocessed)
                unp = resp.get("UnprocessedItems", {}).get(TABLE_NAME, [])
                total_put += len(unprocessed["RequestItems"][TABLE_NAME]) - len(unp)
                if unp:
                    logging.info(f"Retrying {len(unp)} unprocessed items...")
                    time.sleep(backoff)
                    backoff = min(backoff * 2, 2.0)
                    unprocessed = {"RequestItems": {TABLE_NAME: unp}}
                else:
                    break
            return total_put

        artist_ids = []
        artist_items = []
        for i in range(n_artists):
            artist_id = str(uuid.uuid4())
            g = random.choice(genres)
            artist_items.append({
                "PK": {"S": f"ARTIST#{artist_id}"},
                "SK": {"S": "ARTIST"},
                "entityType": {"S": "ARTIST"},
                "name": {"S": f"Artist {i+1}"},
                "primaryGenre": {"S": g},
                "genres": {"L": [{"S": g}]},
                "GSI1PK": {"S": f"GENRE#{g}"},
                "GSI1SK": {"S": f"TYPE#ARTIST#NAME#artist-{i+1}"},
            })
            artist_ids.append(artist_id)

        total_written = 0
        for i in range(0, len(artist_items), 25):
            total_written += write_batches(put_requests(artist_items[i:i+25]))

        album_song_items = []
        for a in range(n_albums):
            album_id = str(uuid.uuid4())
            g = random.choice(genres)
            artist_id = artist_ids[a % len(artist_ids)]

            album_song_items.append({
                "PK": {"S": f"ALBUM#{album_id}"},
                "SK": {"S": "ALBUM"},
                "entityType": {"S": "ALBUM"},
                "name": {"S": f"Album {a+1}"},
                "primaryGenre": {"S": g},
                "artistId": {"S": artist_id},
                "GSI1PK": {"S": f"GENRE#{g}"},
                "GSI1SK": {"S": f"TYPE#ALBUM#NAME#album-{a+1}"},
            })

            # songs
            for t in range(1, songs_per_album + 1):
                album_song_items.append({
                    "PK": {"S": f"SONG#{str(uuid.uuid4())}"},
                    "SK": {"S": "SONG"},
                    "entityType": {"S": "SONG"},
                    "name": {"S": f"Song {a+1}-{t}"},
                    "trackNo": {"N": str(t)},
                    "albumId": {"S": album_id},
                    "artistId": {"S": artist_id},
                    "primaryGenre": {"S": g},
                    "GSI1PK": {"S": f"GENRE#{g}"},
                    "GSI1SK": {"S": f"TYPE#SONG#NAME#song-{a+1}-{t}"},
                    "GSI2PK": {"S": f"ALBUM#{album_id}"},
                    "GSI2SK": {"S": f"TRACK#{str(t).zfill(2)}"},
                })

        for i in range(0, len(album_song_items), 25):
            total_written += write_batches(put_requests(album_song_items[i:i+25]))

        return cors_response(200, {
            "message": "Seed completed",
            "artists": n_artists,
            "albums": n_albums,
            "songs_per_album": songs_per_album,
            "inserted": total_written
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return cors_response(500, {"message": "Internal Server Error", "detail": str(e)})

def reset_music(event, context):
    import time, logging
    logging.getLogger().setLevel("INFO")

    try:
        # 1) Собираем все ключи (PK, SK)
        client = boto3.client("dynamodb")
        keys = []
        scan_kwargs = {
            "TableName": TABLE_NAME,
            "ProjectionExpression": "PK, SK",
        }
        while True:
            resp = client.scan(**scan_kwargs)
            items = resp.get("Items", [])
            for it in items:
                keys.append({"PK": it["PK"], "SK": it["SK"]})
            if "LastEvaluatedKey" in resp:
                scan_kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]
            else:
                break

        # 2) Batch delete по 25 с retry
        def delete_batch(key_batch):
            req = [{"DeleteRequest": {"Key": k}} for k in key_batch]
            unprocessed = {"RequestItems": {TABLE_NAME: req}}
            backoff = 0.2
            deleted = 0
            while unprocessed["RequestItems"][TABLE_NAME]:
                r = client.batch_write_item(**unprocessed)
                unp = r.get("UnprocessedItems", {}).get(TABLE_NAME, [])
                deleted += len(unprocessed["RequestItems"][TABLE_NAME]) - len(unp)
                if unp:
                    time.sleep(backoff)
                    backoff = min(backoff * 2, 2.0)
                    unprocessed = {"RequestItems": {TABLE_NAME: unp}}
                else:
                    break
            return deleted

        total_deleted = 0
        for i in range(0, len(keys), 25):
            total_deleted += delete_batch(keys[i:i+25])

        return cors_response(200, {"message": "Music truncated", "deleted": total_deleted})

    except Exception as e:
        import traceback
        print("reset_music ERROR:", traceback.format_exc())
        body = {"message": "Internal Server Error"}
        if os.environ.get("DEBUG") == "1":
            body["detail"] = str(e)
        return cors_response(500, body)
