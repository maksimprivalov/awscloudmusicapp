import os, json, uuid, random, urllib.parse
import boto3
from datetime import datetime
from typing import Optional, Dict
from boto3.dynamodb.conditions import Key, Attr
from utils.cors import response as cors_response
from decimal import Decimal

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

def _convert_decimals(x):
    if isinstance(x, list):
        return [_convert_decimals(v) for v in x]
    if isinstance(x, dict):
        return {k: _convert_decimals(v) for k, v in x.items()}
    if isinstance(x, Decimal):
        # int ako je ceo broj, inače float
        return int(x) if x % 1 == 0 else float(x)
    return x

def cors_response(status, body):
    try:
        safe_body = _convert_decimals(body)
        return {
            "statusCode": status,
            "headers": {
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Headers": "*",
                "Access-Control-Allow-Methods": "*",
            },
            "body": json.dumps(safe_body, ensure_ascii=False),
        }
    except Exception:
        # Fallback da NIKAD ne padne zbog serializacije
        print("cors_response serialization error:\n", traceback.format_exc())
        return {
            "statusCode": 500,
            "headers": {
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Headers": "*",
                "Access-Control-Allow-Methods": "*",
            },
            "body": json.dumps({"error": "Serialization failure"}, ensure_ascii=False),
        }

def _err(status, msg, exc=None):
    if exc:
        print(f"[ERROR] {msg}\n{traceback.format_exc()}")
    payload = {"error": msg}
    if os.getenv("STAGE", "dev") == "dev" and exc:
        payload["details"] = str(exc)
    return cors_response(status, payload)

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

def update_content(event, context):
    # samo admin
    if not _is_admin(event):
        return cors_response(403, {"error": "Admins only"})

    body = json.loads(event.get("body") or "{}")
    content_id = body.get("contentId")
    if not content_id:
        return cors_response(400, {"error": "contentId is required"})

    # Učitaj postojeći zapis
    pk = f"CONTENT#{content_id}"
    try:
        existing = music_table.get_item(Key={"PK": pk, "SK": "METADATA"}).get("Item")
    except Exception as e:
        return cors_response(500, {"error": f"DDB get_item failed: {e}"})

    if not existing:
        return cors_response(404, {"error": "Content not found"})

    # Polja koja dozvoljavamo da se menjaju (sva opciona)
    name = body.get("name")
    description = body.get("description")
    tags = body.get("tags")
    genres = body.get("genres")
    artists = body.get("artists")
    album_id = body.get("albumId") if "albumId" in body else None  # prisustvo ključa znači “postavi čak i na null”
    track_no = body.get("trackNo") if "trackNo" in body else None
    new_s3_key = body.get("s3Key")

    # Dinamički build update izraza
    update_sets = []
    update_removes = []
    ean = {}  # ExpressionAttributeNames
    eav = {}  # ExpressionAttributeValues

    now = datetime.utcnow().isoformat()

    def set_attr(name_key, attr_name, value):
        ean[f"#{name_key}"] = attr_name
        val_key = f":{attr_name.replace('.', '_')}"
        eav[val_key] = value
        update_sets.append(f"#{name_key} = {val_key}")

    # 1) Prost(iji) meta-podaci
    if name is not None:
        set_attr("name", "name", name)
    if description is not None:
        set_attr("description", "description", description)
    if tags is not None:
        set_attr("tags", "tags", tags)

    # 2) Genres i GSI1
    if genres is not None:
        set_attr("genres", "genres", genres)
        gsi1pk_val = f"GENRE#{genres[0]}" if genres else "GENRE#unknown"
        set_attr("GSI1PK", "GSI1PK", gsi1pk_val)
        # (ostavljamo postojeći GSI1SK; opcionalno bi moglo da prati updatedAt)

    # 3) Artists / Album i GSI2 (mutual exclusive prioritet: album > artist)
    #    - Ako eksplicitno dođe albumId (uklj. None), postavimo/obrišemo album mapping.
    if "albumId" in body:
        if album_id is not None:
            set_attr("albumId", "albumId", album_id)
            if "trackNo" in body:
                # ako nije poslat, ne diramo postojeći
                set_attr("trackNo", "trackNo", track_no if track_no is not None else 0)
                z = str(track_no or 0).zfill(3)
            else:
                z = str(existing.get("trackNo", 0)).zfill(3)
            set_attr("GSI2PK", "GSI2PK", f"ALBUM#{album_id}")
            set_attr("GSI2SK", "GSI2SK", f"TRACK#{z}")
        else:
            # uklanjamo album mapping
            update_removes += ["#albumId", "#GSI2PK", "#GSI2SK"]
            ean["#albumId"] = "albumId"
            ean["#GSI2PK"] = "GSI2PK"
            ean["#GSI2SK"] = "GSI2SK"

    # Ako nije menjan album, ali su menjani artists – možemo postaviti ARTIST GSI2
    if ("albumId" not in body) and (artists is not None):
        set_attr("artists", "artists", artists)
        if artists and len(artists) > 0:
            set_attr("GSI2PK", "GSI2PK", f"ARTIST#{artists[0]}")
            # Sort ključ možemo voditi po vremenu izmene (ili zadržati stari)
            set_attr("GSI2SK", "GSI2SK", f"TRACK#{now}")
        else:
            # nema više artists → ukloni GSI2 mapping ako je bio artistički
            update_removes += ["#GSI2PK", "#GSI2SK"]
            ean["#GSI2PK"] = "GSI2PK"
            ean["#GSI2SK"] = "GSI2SK"

    # 4) trackNo nezavisno (ako nije već pokriven grane gore)
    if ("trackNo" in body) and ("albumId" not in body):
        # ažuriramo trackNo polje, ali GSI2SK za album menjamo samo ako je ALBUM mapping već prisutan
        set_attr("trackNo", "trackNo", track_no if track_no is not None else 0)
        if existing.get("GSI2PK", "").startswith("ALBUM#"):
            z = str(track_no or 0).zfill(3)
            set_attr("GSI2SK", "GSI2SK", f"TRACK#{z}")

    # 5) Promena fajla (novi s3Key) → povuci meta iz S3
    if new_s3_key is not None:
        try:
            head = s3.head_object(Bucket=BUCKET, Key=new_s3_key)
            file_type = head.get("ContentType", "application/octet-stream")
            file_size = head["ContentLength"]
            last_modified = head["LastModified"].isoformat()
        except Exception as e:
            return cors_response(400, {"error": f"S3 object not found or not uploaded yet: {e}"})

        set_attr("s3Key", "s3Key", new_s3_key)
        set_attr("fileType", "fileType", file_type)
        set_attr("fileSize", "fileSize", file_size)
        set_attr("fileLastModified", "fileLastModified", last_modified)
        # fileName iz key-a
        set_attr("fileName", "fileName", new_s3_key.split("/")[-1])

    # 6) Uvek ažuriramo updatedAt
    set_attr("updatedAt", "updatedAt", now)

    if not update_sets and not update_removes:
        return cors_response(400, {"error": "No updatable fields provided"})

    update_expr = []
    if update_sets:
        update_expr.append("SET " + ", ".join(update_sets))
    if update_removes:
        update_expr.append("REMOVE " + ", ".join(update_removes))

    try:
        resp = music_table.update_item(
            Key={"PK": pk, "SK": "METADATA"},
            UpdateExpression=" ".join(update_expr),
            ExpressionAttributeNames=ean or None,
            ExpressionAttributeValues=eav or None,
            ConditionExpression="attribute_exists(PK) AND attribute_exists(SK)",
            ReturnValues="ALL_NEW",
        )
        return cors_response(200, {
            "message": "Content updated",
            "content": resp.get("Attributes", {})
        })
    except Exception as e:
        return cors_response(500, {"error": f"DDB update failed: {e}"})


def delete_content(event, context):
    if not _is_admin(event):
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
        return _err(500, "DDB delete failed", e)

# =============== 2) DELETE ALBUM (kaskadno briše pesme) ===
from boto3.dynamodb.conditions import Key

def delete_album(event, context):
    if not _is_admin(event):
        return cors_response(403, {"error": "Admins only"})
    album_id = (event.get("pathParameters") or {}).get("albumId")
    if not album_id:
        return cors_response(400, {"error": "albumId path param required"})

    try:
        # 1) Nađi sve pesme u albumu preko GSI2
        q = music_table.query(
            IndexName="GSI2",
            KeyConditionExpression=Key("GSI2PK").eq(f"ALBUM#{album_id}")
        )
        items = q.get("Items", [])

        # 2) Obriši sve stavke (sve SK-ove) za svaki CONTENT#<id>
        pk_values = {it["PK"] for it in items}  # npr. {"CONTENT#<uuid1>", "CONTENT#<uuid2>"}
        rows_deleted = 0
        for pk in pk_values:
            all_items = music_table.query(KeyConditionExpression=Key("PK").eq(pk)).get("Items", [])
            with music_table.batch_writer() as bw:
                for it in all_items:
                    bw.delete_item(Key={"PK": it["PK"], "SK": it["SK"]})
                    rows_deleted += 1

        # 3) (NOVO) Obriši i sam album ako postoji kao entitet: PK="ALBUM#<albumId>"
        album_pk = f"ALBUM#{album_id}"
        album_items = music_table.query(KeyConditionExpression=Key("PK").eq(album_pk)).get("Items", [])
        album_deleted_rows = 0
        if album_items:
            with music_table.batch_writer() as bw:
                for it in album_items:
                    bw.delete_item(Key={"PK": it["PK"], "SK": it["SK"]})
                    album_deleted_rows += 1

        return cors_response(200, {
            "message": "Album deleted with tracks",
            "albumId": album_id,
            "tracksDeleted": len(pk_values),      # koliko pesama (PK) je obrisano
            "rowsDeleted": rows_deleted,          # ukupno obrisanih redova za pesme
            "albumDeleted": album_deleted_rows > 0,
            "albumRowsDeleted": album_deleted_rows
        })
    except Exception as e:
        return _err(500, "Cascade delete for album failed", e)


# =============== 3) DELETE ARTIST (NE briše pesme) ========
#  - uklanja umetnika iz liste 'artists' svake pesme
#  - ako posle uklanjanja nema više artista, ostavlja prazan niz (ili placeholder)
#  - održava GSI2: ako je mapping bio ARTIST#, apdejtuje/uklanja
def delete_artist(event, context):
    if not _is_admin(event):
        return cors_response(403, {"error": "Admins only"})
    artist_id = (event.get("pathParameters") or {}).get("artistId")
    if not artist_id:
        return cors_response(400, {"error": "artistId path param required"})

    try:
        updated = 0

        # 1) Pesme gde je taj umetnik primarni u GSI2 (ARTIST#<id>)
        q1 = music_table.query(
            IndexName="GSI2",
            KeyConditionExpression=Key("GSI2PK").eq(f"ARTIST#{artist_id}")
        )
        candidate_items = q1.get("Items", [])

        # 2) Fallback: sve TRACK stavke koje u listi 'artists' sadrže artist_id
        scan = music_table.scan(
            FilterExpression=Attr("entityType").eq("TRACK") & Attr("artists").contains(artist_id),
            ProjectionExpression="PK, SK, artists, GSI2PK, GSI2SK, contentId"
        )
        candidate_items.extend(scan.get("Items", []))

        # deduplikacija po (PK, SK)
        seen = set()
        uniq = []
        for it in candidate_items:
            key = (it["PK"], it["SK"])
            if key not in seen:
                uniq.append(it)
                seen.add(key)

        now = datetime.utcnow().isoformat()

        for it in uniq:
            pk = it["PK"]
            # uvek radi nad METADATA zapisom
            meta = music_table.get_item(Key={"PK": pk, "SK": "METADATA"}).get("Item")
            if not meta:
                continue

            artists = list(meta.get("artists", []))
            if artist_id in artists:
                artists = [a for a in artists if a != artist_id]

            # priprema update izraza
            ean = {
                "#artists": "artists",
                "#updatedAt": "updatedAt",
                "#GSI2PK": "GSI2PK",
                "#GSI2SK": "GSI2SK"
            }
            eav = {
                ":artists": artists,
                ":updatedAt": now
            }
            sets = ["#artists = :artists", "#updatedAt = :updatedAt"]
            removes = []

            # ako je GSI2 bio ARTIST#, uskladi ga sa novim stanjem
            gsi2pk = meta.get("GSI2PK", "")
            if gsi2pk.startswith("ARTIST#"):
                if artists:
                    eav[":g2pk"] = f"ARTIST#{artists[0]}"
                    eav[":g2sk"] = f"TRACK#{now}"
                    sets += ["#GSI2PK = :g2pk", "#GSI2SK = :g2sk"]
                else:
                    removes += ["#GSI2PK", "#GSI2SK"]

            update_expr = []
            if sets:
                update_expr.append("SET " + ", ".join(sets))
            if removes:
                update_expr.append("REMOVE " + ", ".join(removes))

            music_table.update_item(
                Key={"PK": pk, "SK": "METADATA"},
                UpdateExpression=" ".join(update_expr),
                ExpressionAttributeNames=ean,
                ExpressionAttributeValues=eav,
                ConditionExpression="attribute_exists(PK) AND attribute_exists(SK)"
            )
            updated += 1

        # --- posle što su SVE pesme ažurirane, obriši zapis u Artists tabeli ---
        ddb = boto3.resource("dynamodb")
        artists_table_name = os.getenv("ARTISTS_TABLE", "Artists")
        artists_table = ddb.Table(artists_table_name)
        artists_table.delete_item(Key={"artistId": artist_id})

        return cors_response(200, {
            "message": "Artist deleted (references updated)",
            "artistId": artist_id,
            "tracksUpdated": updated,
            "artistTableDeleted": True
        })

    except Exception as e:
        return _err(500, "Delete artist failed", e)
