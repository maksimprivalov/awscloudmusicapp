import os, json, uuid, random, urllib.parse
import boto3
from datetime import datetime
from typing import Optional, Dict
from boto3.dynamodb.conditions import Key, Attr
from utils.cors import response as cors_response
from decimal import Decimal
from urllib.parse import unquote

# ===== AWS clients & env =====
s3 = boto3.client("s3")
dynamodb = boto3.resource("dynamodb")

TABLE_NAME = os.environ.get("TABLE_NAME", "Music")
music_table = dynamodb.Table(TABLE_NAME)

ARTISTS_TABLE = os.getenv("ARTISTS_TABLE", "Artists")
artists_table = dynamodb.Table(ARTISTS_TABLE)

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

#                        1) ADMIN: upload flow
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
        import traceback
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

#                   4) Seed / Reset (admin)
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
            # tracks (zamena za SONG)
            for t in range(1, songs_per_album + 1):
                track_id = str(uuid.uuid4())
                album_song_items.append({
                    "PK": {"S": f"CONTENT#{track_id}"},
                    "SK": {"S": "METADATA"},
                    "entityType": {"S": "TRACK"},
                    "contentId": {"S": track_id},

                    "name": {"S": f"Song {a + 1}-{t}"},
                    "trackNo": {"N": str(t)},
                    "albumId": {"S": album_id},
                    "artistId": {"S": artist_id},
                    "primaryGenre": {"S": g},

                    "GSI1PK": {"S": f"GENRE#{g}"},
                    "GSI1SK": {"S": f"TYPE#TRACK#NAME#song-{a + 1}-{t}"},

                    "GSI2PK": {"S": f"ALBUM#{album_id}"},
                    "GSI2SK": {"S": f"TRACK#{str(t).zfill(3)}"},
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

def update_content(event, context):
    if not _is_admin(event):
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



def delete_album(event, context):
    if not _is_admin(event):
        return cors_response(403, {"error": "Admins only"})
    album_id = (event.get("pathParameters") or {}).get("albumId")
    if not album_id:
        return cors_response(400, {"error": "albumId path param required"})

    album_id = unquote(album_id)
    if album_id.startswith("ALBUM#"):
        album_id = album_id.split("#", 1)[1]

    try:
        q = music_table.query(
            IndexName="GSI2",
            KeyConditionExpression=Key("GSI2PK").eq(f"ALBUM#{album_id}")
        )
        items = q.get("Items", [])

        pk_values = {it["PK"] for it in items}
        rows_deleted = 0
        for pk in pk_values:
            all_items = music_table.query(
                KeyConditionExpression=Key("PK").eq(pk)
            ).get("Items", [])
            with music_table.batch_writer() as bw:
                for it in all_items:
                    bw.delete_item(Key={"PK": it["PK"], "SK": it["SK"]})
                    rows_deleted += 1

        # obriši i sam album, ako postoji kao entitet
        album_pk = f"ALBUM#{album_id}"
        album_items = music_table.query(
            KeyConditionExpression=Key("PK").eq(album_pk)
        ).get("Items", [])
        album_deleted_rows = 0
        if album_items:
            with music_table.batch_writer() as bw:
                for it in album_items:
                    bw.delete_item(Key={"PK": it["PK"], "SK": it["SK"]})
                    album_deleted_rows += 1

        return cors_response(200, {
            "message": "Album deleted with tracks",
            "albumId": album_id,
            "tracksDeleted": len(pk_values),
            "rowsDeleted": rows_deleted,
            "albumDeleted": album_deleted_rows > 0,
            "albumRowsDeleted": album_deleted_rows
        })
    except Exception as e:
        return _err(500, "Cascade delete for album failed", e)



# =============== 3) DELETE ARTIST (NE briše pesme) ========
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
        music_table.delete_item(Key={"PK": f"ARTIST#{artist_id}", "SK": "ARTIST"})

        return cors_response(200, {
            "message": "Artist deleted (references updated)",
            "artistId": artist_id,
            "tracksUpdated": updated,
            "artistTableDeleted": True
        })

    except Exception as e:
        return _err(500, "Delete artist failed", e)

def create_album(event, context):
    if not _is_admin(event):
        return cors_response(403, {"error": "Admins only"})

    try:
        body = json.loads(event.get("body") or "{}")
    except Exception:
        return cors_response(400, {"error": "Invalid JSON body"})

    album_id      = (body.get("albumId") or "").strip()
    name          = (body.get("name") or "").strip()
    primary_genre = (body.get("primaryGenre") or "").strip().lower()

    # opciona polja
    artist_id    = (body.get("artistId") or "").strip() or None
    year         = body.get("year")               # int | None
    description  = (body.get("description") or "").strip() or None
    cover_s3_key = (body.get("coverS3Key") or "").strip() or None

    if not album_id or not name or not primary_genre:
        return cors_response(400, {"error": "albumId, name, primaryGenre are required"})

    # pripremi stavku
    now = datetime.utcnow().isoformat()

    def _slug(s: str) -> str:
        return "-".join(s.lower().split())

    item = {
        "PK": f"ALBUM#{album_id}",
        "SK": "ALBUM",
        "entityType": "ALBUM",
        "albumId": album_id,
        "name": name,
        "primaryGenre": primary_genre,
        "artistId": artist_id,         # može biti None
        "year": year,                  # može biti None (int ili Decimal)
        "description": description,    # može biti None
        "coverS3Key": cover_s3_key,    # može biti None (npr. albums/<id>/cover.jpg)
        "createdAt": now,
        "updatedAt": now,
        # GSI1: po žanru, listamo albume po imenu
        "GSI1PK": f"GENRE#{primary_genre}",
        "GSI1SK": f"TYPE#ALBUM#NAME#{_slug(name)}",
    }

    # ukloni None vrednosti (DynamoDB ne prima null ako ne koristimo explicitni NULL tip)
    item = {k: v for k, v in item.items() if v is not None}

    try:
        music_table.put_item(
            Item=item,
            ConditionExpression="attribute_not_exists(PK) AND attribute_not_exists(SK)"
        )
        if cover_s3_key:
            try:
                item["coverUrl"] = s3.generate_presigned_url(
                    "get_object",
                    Params={"Bucket": BUCKET, "Key": cover_s3_key},
                    ExpiresIn=3600
                )
            except Exception:
                pass

        return cors_response(201, {"message": "Album created", "albumId": album_id, "album": item})
    except Exception as e:
        msg = str(e)
        if "ConditionalCheckFailed" in msg:
            return cors_response(409, {"error": "Album already exists"})
        return cors_response(500, {"error": f"DDB put failed: {msg}"})


def _norm_album_id(raw: str) -> str:
    a = unquote(raw or "")
    if a.startswith("ALBUM#"):
        a = a.split("#", 1)[1]
    return a

def update_album(event, context):
    # samo admin
    if not _is_admin(event):
        return cors_response(403, {"error": "Admins only"})

    try:
        body = json.loads(event.get("body") or "{}")
    except Exception:
        return cors_response(400, {"error": "Invalid JSON body"})

    album_id = (body.get("albumId") or "").strip()
    if not album_id:
        return cors_response(400, {"error": "albumId is required"})

    # optional meta polja
    name          = body.get("name")            # string?
    primary_genre = body.get("primaryGenre")    # string?
    description   = body.get("description")     # string?
    artists       = body.get("artists")         # list[str]?
    add_cids      = body.get("addContentIds")   # list[str]
    rem_cids      = body.get("removeContentIds")# list[str]
    resequence    = bool(body.get("resequence", False))

    if artists is not None and not isinstance(artists, list):
        return cors_response(400, {"error": "artists must be array of strings"})
    if add_cids is not None and not isinstance(add_cids, list):
        return cors_response(400, {"error": "addContentIds must be array of strings"})
    if rem_cids is not None and not isinstance(rem_cids, list):
        return cors_response(400, {"error": "removeContentIds must be array of strings"})

    add_cids = [c for c in (add_cids or []) if isinstance(c, str) and c.strip()]
    rem_cids = [c for c in (rem_cids or []) if isinstance(c, str) and c.strip()]
    artists  = [a for a in (artists  or []) if isinstance(a, str) and a.strip()]

    now = datetime.utcnow().isoformat()

    # 1) UPDATE meta zapisa albuma (ako postoji) → PK="ALBUM#<albumId>", SK="ALBUM"
    album_pk = f"ALBUM#{album_id}"
    try:
        album_meta = music_table.get_item(Key={"PK": album_pk, "SK": "ALBUM"}).get("Item")
        if album_meta:
            update_sets, ean, eav = [], {}, {}
            def s(nk, an, val):
                ean[f"#{nk}"] = an; eav[f":{an}"] = val; update_sets.append(f"#{nk} = :{an}")
            if name is not None:          s("name", "name", name)
            if primary_genre is not None:
                music_table.update_item(
                    Key={"PK": album_pk, "SK": "ALBUM"},
                    UpdateExpression="SET #pg=:g, #g1pk=:gpk, #updatedAt=:now",
                    ExpressionAttributeNames={"#pg": "primaryGenre", "#g1pk": "GSI1PK", "#updatedAt": "updatedAt"},
                    ExpressionAttributeValues={":g": primary_genre, ":gpk": f"GENRE#{primary_genre.strip().lower()}",
                                               ":now": now},
                    ConditionExpression="attribute_exists(PK) AND attribute_exists(SK)"
                )

            if description is not None:   s("description", "description", description)
            if artists is not None:       s("artists", "artists", artists)
            s("updatedAt", "updatedAt", now)

            if update_sets:
                music_table.update_item(
                    Key={"PK": album_pk, "SK": "ALBUM"},
                    UpdateExpression="SET " + ", ".join(update_sets),
                    ExpressionAttributeNames=ean,
                    ExpressionAttributeValues=eav,
                    ConditionExpression="attribute_exists(PK) AND attribute_exists(SK)"
                )
        else:
            # ako nema meta a korisnik šalje bar neki meta podatak — napravi meta red
            if any(v is not None for v in [name, primary_genre, description, artists]):
                put_row = {
                    "PK": album_pk, "SK": "ALBUM",
                    "entityType": "ALBUM",
                    "name": name or album_id,
                    "primaryGenre": (primary_genre or "unknown"),
                    "description": description or "",
                    "artists": artists or [],
                    "createdAt": now, "updatedAt": now,
                    "GSI1PK": f"GENRE#{(primary_genre or 'unknown')}",
                    "GSI1SK": f"TYPE#ALBUM#NAME#{(name or album_id).lower().replace(' ','-')}",
                }
                music_table.put_item(Item=put_row)
    except Exception as e:
        return _err(500, "Album meta update failed", e)

    # 2) DODAJ pesme u album: setuj GSI2PK/ GSI2SK i albumId na METADATA
    added = 0
    for cid in add_cids:
        pk = f"CONTENT#{cid}"
        # proveri da METADATA postoji
        meta = music_table.get_item(Key={"PK": pk, "SK": "METADATA"}).get("Item")
        if not meta:
            continue

        track_no = int(meta.get("trackNo", 0) or 0)
        try:
            music_table.update_item(
                Key={"PK": pk, "SK": "METADATA"},
                UpdateExpression="SET #albumId=:aid, #G2PK=:g2pk, #G2SK=:g2sk, #updatedAt=:now",
                ExpressionAttributeNames={
                    "#albumId": "albumId", "#G2PK": "GSI2PK", "#G2SK": "GSI2SK", "#updatedAt": "updatedAt"
                },
                ExpressionAttributeValues={
                    ":aid": album_id, ":g2pk": f"ALBUM#{album_id}",
                    ":g2sk": f"TRACK#{str(track_no).zfill(3)}",
                    ":now": now
                },
                ConditionExpression="attribute_exists(PK) AND attribute_exists(SK)"
            )
            added += 1
        except Exception:
            pass

    # 3) UKLONI pesme iz albuma (skini albumId i GSI2* ako je ALBUM#)
    removed = 0
    for cid in rem_cids:
        pk = f"CONTENT#{cid}"
        meta = music_table.get_item(Key={"PK": pk, "SK": "METADATA"}).get("Item")
        if not meta:
            continue
        if str(meta.get("albumId") or "") != album_id:
            continue
        try:
            music_table.update_item(
                Key={"PK": pk, "SK": "METADATA"},
                UpdateExpression="REMOVE #albumId, #G2PK, #G2SK SET #updatedAt=:now",
                ExpressionAttributeNames={
                    "#albumId": "albumId", "#G2PK": "GSI2PK", "#G2SK": "GSI2SK", "#updatedAt": "updatedAt"
                },
                ExpressionAttributeValues={":now": now},
                ConditionExpression="attribute_exists(PK) AND attribute_exists(SK)"
            )
            removed += 1
        except Exception:
            pass

    add_art = body.get("addArtists") or []
    rem_art = body.get("removeArtists") or []

    if (add_art or rem_art) and album_meta:
        cur = list(album_meta.get("artists", []))
        # dodaj (bez duplikata)
        for a in add_art:
            a = (a or "").strip()
            if a and a not in cur:
                cur.append(a)
        # ukloni
        if rem_art:
            cur = [a for a in cur if a not in rem_art]

        music_table.update_item(
            Key={"PK": album_pk, "SK": "ALBUM"},
            UpdateExpression="SET #artists=:a, #updatedAt=:now",
            ExpressionAttributeNames={"#artists": "artists", "#updatedAt": "updatedAt"},
            ExpressionAttributeValues={":a": cur, ":now": now},
            ConditionExpression="attribute_exists(PK) AND attribute_exists(SK)"
        )

    resequenced = 0
    if resequence:
        q = music_table.query(
            IndexName="GSI2",
            KeyConditionExpression=Key("GSI2PK").eq(f"ALBUM#{album_id}")
        )
        tracks = q.get("Items", [])
        def safe(x, k, d=0):
            v = x.get(k)
            if isinstance(v, Decimal): v = int(v) if v % 1 == 0 else float(v)
            return v if v is not None else d
        tracks.sort(key=lambda t: (safe(t,"trackNo"), t.get("name",""), t.get("contentId","")))
        for i, it in enumerate(tracks, start=1):
            pk = it["PK"]
            try:
                music_table.update_item(
                    Key={"PK": pk, "SK": "METADATA"},
                    UpdateExpression="SET #trackNo=:tn, #G2SK=:g2sk, #updatedAt=:now",
                    ExpressionAttributeNames={"#trackNo":"trackNo", "#G2SK":"GSI2SK", "#updatedAt":"updatedAt"},
                    ExpressionAttributeValues={":tn": i, ":g2sk": f"TRACK#{str(i).zfill(3)}", ":now": now}
                )
                resequenced += 1
            except Exception:
                pass

    return cors_response(200, {
        "message": "Album updated",
        "albumId": album_id,
        "added": added,
        "removed": removed,
        "resequenced": resequenced
    })

# --- GET ALBUM META ---
def get_album(event, context):
    try:
        album_id = (event.get("pathParameters") or {}).get("albumId")
        if not album_id:
            return cors_response(400, {"error": "albumId path param required"})

        # 1) Probaj direktno meta-zapis ALBUM#<id> / SK=ALBUM
        pk = f"ALBUM#{album_id}"
        resp = music_table.get_item(Key={"PK": pk, "SK": "ALBUM"})
        meta = resp.get("Item")

        if meta:
            out = {
                "albumId": album_id,
                "name": meta.get("name"),
                "primaryGenre": meta.get("primaryGenre"),
                "genres": meta.get("genres") or ([] if not meta.get("primaryGenre") else [meta.get("primaryGenre")]),
                "artists": meta.get("artists") or [],
                "description": meta.get("description") or meta.get("bio") or meta.get("desc"),
            }
            return cors_response(200, out)

        # 2) Fallback: izvedi iz pesama u albumu (GSI2: GSI2PK = ALBUM#<id>)
        q = music_table.query(
            IndexName="GSI2",
            KeyConditionExpression=Key("GSI2PK").eq(f"ALBUM#{album_id}")
        )
        tracks = q.get("Items", [])

        if not tracks:
            # nema ni meta ni pesama
            return cors_response(404, {"error": "Album not found"})

        # Izvedi polja iz traka
        def unique(seq):
            seen = set(); out = []
            for x in seq:
                if x is None: continue
                if x not in seen:
                    seen.add(x); out.append(x)
            return out

        name_candidates = [t.get("albumName") for t in tracks if t.get("albumName")]
        album_name = name_candidates[0] if name_candidates else None

        from collections import Counter
        g_list = []
        for t in tracks:
            # ako je na traci 'genres' lista – dodaj sve; ako je single 'primaryGenre' – dodaj i to
            if isinstance(t.get("genres"), list):
                g_list.extend([g for g in t["genres"] if isinstance(g, str)])
            if isinstance(t.get("primaryGenre"), str):
                g_list.append(t["primaryGenre"])
        primary_genre = None
        genres_sorted = []
        if g_list:
            cnt = Counter([g.strip().lower() for g in g_list if g])
            primary_genre = cnt.most_common(1)[0][0]
            genres_sorted = [g for g, _ in cnt.most_common()]

        artists_merged = []
        for t in tracks:
            if isinstance(t.get("artists"), list):
                artists_merged.extend([a for a in t["artists"] if isinstance(a, str)])
            elif isinstance(t.get("artistId"), str):
                artists_merged.append(t["artistId"])
        artists_uniq = unique(artists_merged)

        out = {
            "albumId": album_id,
            "name": album_name,
            "primaryGenre": primary_genre,
            "genres": genres_sorted or ([primary_genre] if primary_genre else []),
            "artists": artists_uniq,
            "description": None,
        }
        return cors_response(200, out)

    except Exception as e:
        return _err(500, "Get album failed", e)

def list_artists(event, context):
    try:
        items = []
        scan_kwargs = {}
        while True:
            resp = artists_table.scan(**scan_kwargs)
            items.extend(resp.get("Items", []))
            lek = resp.get("LastEvaluatedKey")
            if not lek:
                break
            scan_kwargs["ExclusiveStartKey"] = lek

        return cors_response(200, items)
    except Exception as e:
        return cors_response(500, {"error": str(e)})

def _slug(s: str) -> str:
    return "-".join((s or "").strip().lower().split())

def update_artist(event, context):
    if not _is_admin(event):
        return cors_response(403, {"error": "Admins only"})

    try:
        body = json.loads(event.get("body") or "{}")
    except Exception:
        return cors_response(400, {"error": "Invalid JSON"})

    artist_id = (body.get("artistId") or "").strip()
    if not artist_id:
        return cors_response(400, {"error": "artistId required"})

    # polja
    name   = body.get("name")
    bio    = body.get("bio")
    genres = body.get("genres")  # lista ili None

    # 1) update u Artists tabeli
    sets, ean, eav = [], {}, {}
    now = datetime.utcnow().isoformat()

    if name is not None:
        ean["#name"] = "name"; eav[":name"] = name; sets.append("#name=:name")
    if bio is not None:
        ean["#bio"] = "bio"; eav[":bio"] = bio; sets.append("#bio=:bio")
    if genres is not None:
        ean["#genres"] = "genres"; eav[":genres"] = genres; sets.append("#genres=:genres")
    ean["#updatedAt"] = "updatedAt"; eav[":now"] = now; sets.append("#updatedAt=:now")

    if not sets:
        return cors_response(400, {"error": "Nothing to update"})

    try:
        artists_table.update_item(
            Key={"artistId": artist_id},
            UpdateExpression="SET " + ", ".join(sets),
            ExpressionAttributeNames=ean,
            ExpressionAttributeValues=eav,
            ConditionExpression="attribute_exists(artistId)"
        )
    except Exception as e:
        return cors_response(500, {"error": f"Artists update failed: {e}"})

    # 2) mirror u Music (PK=ARTIST#id, SK=ARTIST) — da discover radi po GSI1
    #    (ako ne postoji, napravi; ako postoji, azuriraj ime/zanr)
    primary_genre = None
    if isinstance(genres, list) and genres:
        primary_genre = (genres[0] or "").strip().lower()

    try:
        pk = f"ARTIST#{artist_id}"
        mirror = music_table.get_item(Key={"PK": pk, "SK": "ARTIST"}).get("Item")

        now = datetime.utcnow().isoformat()

        if not mirror:
            # kreiraj novi mirror zapis
            put_item = {
                "PK": pk,
                "SK": "ARTIST",
                "entityType": "ARTIST",
                "artistId": artist_id,
                "name": (name or ""),  # može ostati prazno
                "genres": (genres or []),
                "primaryGenre": (primary_genre or "unknown"),
                "createdAt": now,
                "updatedAt": now,
                "GSI1PK": f"GENRE#{primary_genre or 'unknown'}",
                "GSI1SK": f"TYPE#ARTIST#NAME#{_slug(name or artist_id)}",
            }
            music_table.put_item(Item=put_item)

        else:
            # ažuriraj postojeći mirror
            u_sets = ["#updatedAt = :now"]
            u_ean = {"#updatedAt": "updatedAt"}
            u_eav = {":now": now}

            # ime
            if name is not None:
                u_ean["#name"] = "name"
                u_eav[":name"] = name
                u_sets.append("#name = :name")

                u_ean["#g1sk"] = "GSI1SK"
                u_eav[":g1sk"] = f"TYPE#ARTIST#NAME#{_slug(name)}"
                u_sets.append("#g1sk = :g1sk")

            # žanrovi + primaryGenre + GSI1PK
            if genres is not None:
                u_ean["#genres"] = "genres"
                u_eav[":genres"] = genres
                u_sets.append("#genres = :genres")

                pg = (genres[0].strip().lower() if genres else "unknown")
                u_ean["#primaryGenre"] = "primaryGenre"
                u_eav[":pg"] = pg
                u_sets.append("#primaryGenre = :pg")

                u_ean["#g1pk"] = "GSI1PK"
                u_eav[":g1pk"] = f"GENRE#{pg}"
                u_sets.append("#g1pk = :g1pk")

            music_table.update_item(
                Key={"PK": pk, "SK": "ARTIST"},
                UpdateExpression="SET " + ", ".join(u_sets),
                ExpressionAttributeNames=u_ean,
                ExpressionAttributeValues=u_eav,
            )

    except Exception as e:
        return cors_response(500, {"error": f"Mirror update failed: {e}"})

    return cors_response(200, {"message": "Artist updated", "artistId": artist_id})
