import os
import json
import uuid
import random
import traceback
import boto3
from utils.cors import response as cors_response
from utils.authz import is_admin
from utils.aws import TABLE_NAME

def seed(event, context):
    if not is_admin(event):
        return cors_response(403, {"error": "Admins only"})

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
        traceback.print_exc()
        return cors_response(500, {"message": "Internal Server Error", "detail": str(e)})

def reset_music(event, context):
    if not is_admin(event):
        return cors_response(403, {"error": "Admins only"})

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
        print("reset_music ERROR:", traceback.format_exc())
        body = {"message": "Internal Server Error"}
        if os.environ.get("DEBUG") == "1":
            body["detail"] = str(e)
        return cors_response(500, body)
