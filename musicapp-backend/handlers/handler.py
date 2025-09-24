# import boto3
# import os
# import uuid
# from datetime import datetime
# import json
# import random
# import urllib.parse
# from boto3.dynamodb.conditions import Key, Attr
# from typing import Optional, Dict


# ALLOWED_ORIGIN = "http://localhost:4200"
# DEBUG = os.environ.get("DEBUG") == "1"

# def cors_response(status, body):
#     return {
#         "statusCode": status,
#         "headers": {
#             "Access-Control-Allow-Origin": ALLOWED_ORIGIN,
#             "Access-Control-Allow-Credentials": "true",
#             "Access-Control-Allow-Headers": "Content-Type,Authorization",
#             "Access-Control-Allow-Methods": "GET,POST,PUT,DELETE,OPTIONS",
#         },
#         "body": json.dumps(body) if not isinstance(body, str) else body,
#     }

# cognito = boto3.client("cognito-idp")

# USER_POOL_ID = os.environ["USER_POOL_ID"]
# CLIENT_ID = os.environ["CLIENT_ID"]

# dynamodb = boto3.resource("dynamodb")
# tableArtists = dynamodb.Table("Artists")

# TABLE_NAME = os.environ.get("TABLE_NAME", "Music")
# musicTable = dynamodb.Table(TABLE_NAME)


# def create_artist(event, context):
#     claims = event["requestContext"]["authorizer"]["claims"]
#     groups = claims.get("cognito:groups", "")

#     if "Admin" not in groups:
#         return {"statusCode": 403, "body": "Forbidden – Admins only"}

#     body = json.loads(event.get("body") or "{}")

#     name = body.get("name")
#     bio = body.get("bio")
#     genres = body.get("genres", [])

#     if not name or not bio:
#         return {"statusCode": 400, "body": "Name and bio required"}

#     artist_id = str(uuid.uuid4())

#     item = {
#         "artistId": artist_id,
#         "name": name,
#         "bio": bio,
#         "genres": genres,
#         "createdAt": datetime.utcnow().isoformat()
#     }

#     # try:
#     #     tableArtists.put_item(Item=item)
#     #     return {
#     #         "statusCode": 201,
#     #         "body": json.dumps({"message": "Artist created", "artistId": artist_id})
#     #     }
#     # except Exception as e:
#     #     return {"statusCode": 500, "body": str(e)}
#     try:
#         tableArtists.put_item(Item=item)
#         return cors_response(201, {"message": "Artist created", "artistId": artist_id})
#     except Exception as e:
#         return cors_response(500, {"error": str(e)})
    
# def register(event, context):
#     body = event.get("body")
#     if body is None:
#         return cors_response(400, {"error": "No data"})


#     data = json.loads(body)

#     try:
#         response = cognito.sign_up(
#             ClientId=CLIENT_ID,
#             Username=data["email"],
#             Password=data["password"],
#             UserAttributes=[
#                 {"Name": "given_name", "Value": data["first_name"]},
#                 {"Name": "family_name", "Value": data["last_name"]},
#                 {"Name": "email", "Value": data["email"]},
#                 {"Name": "birthdate", "Value": data["birthdate"]}
#             ],
#         )
#         return cors_response(200, {
#             "message": "User registered",
#             "userSub": response["UserSub"]
#         })
#     except Exception as e:
#         return cors_response(400, {"error": str(e)})

# def login(event, context):
#     body = event.get("body")
#     if body is None:
#         return cors_response(400, {"error": "No data"})

#     data = json.loads(body)

#     try:
#         response = cognito.initiate_auth(
#             ClientId=CLIENT_ID,
#             AuthFlow="USER_PASSWORD_AUTH",
#             AuthParameters={
#                 "USERNAME": data["email"],
#                 "PASSWORD": data["password"]
#             },
#         )
#         return cors_response(200, response["AuthenticationResult"])
#     except Exception as e:
#         return cors_response(400, {"error": str(e)})


# def _encode_last_key(last_key: Optional[Dict]) -> Optional[str]:
#     if not last_key:
#         return None
#     return urllib.parse.quote(json.dumps(last_key))

# def _decode_last_key(s: Optional[str]) -> Optional[Dict]:
#     if not s:
#         return None
#     try:
#         return json.loads(urllib.parse.unquote(s))
#     except Exception:
#         return None

# def discover(event, context):
#     try:
#         params = event.get("queryStringParameters") or {}
#         genre = (params.get("genre") or "").strip().lower()
#         typ = (params.get("type") or "").strip().upper()   # "ALBUM" | "ARTIST" | "" (oba)
#         limit_str = params.get("limit") or "12"

#         try:
#             limit = max(1, min(int(limit_str), 50))
#         except ValueError:
#             limit = 12

#         if not genre:
#             return cors_response(400, {"message": "Missing required query param: genre"})

#         # --- NOVO: pripremi prefix i (po potrebi) filter za isključivanje SONG ---
#         prefix = "TYPE#"
#         filter_expr = None
#         if typ == "ALBUM":
#             prefix = "TYPE#ALBUM"
#         elif typ == "ARTIST":
#             prefix = "TYPE#ARTIST"
#         else:
#             # "oba" (default) -> ALBUM + ARTIST, bez SONG
#             filter_expr = Attr("entityType").is_in(["ALBUM", "ARTIST"])

#         last_key = _decode_last_key(params.get("lastKey"))

#         query_kwargs = dict(
#             IndexName="GSI1",
#             KeyConditionExpression=Key("GSI1PK").eq(f"GENRE#{genre}") & Key("GSI1SK").begins_with(prefix),
#             Limit=limit,
#         )
#         if last_key is not None:
#             query_kwargs["ExclusiveStartKey"] = last_key
#         if filter_expr is not None:
#             query_kwargs["FilterExpression"] = filter_expr   # ⬅️ ključno: izbacuje SONG

#         result = musicTable.query(**query_kwargs)

#         items = result.get("Items", [])
#         lek = result.get("LastEvaluatedKey")

#         out = []
#         for x in items:
#             pk = x.get("PK", "")
#             _id = pk.split("#", 1)[1] if "#" in pk else pk
#             out.append({
#                 "id": _id,
#                 "name": x.get("name"),
#                 "entityType": x.get("entityType"),
#                 "primaryGenre": x.get("primaryGenre"),
#             })

#         return cors_response(200, {"items": out, "nextKey": _encode_last_key(lek)})

#     except Exception as e:
#         import traceback, os
#         print("discover ERROR:", traceback.format_exc())
#         body = {"message": "Internal Server Error"}
#         if os.environ.get("DEBUG") == "1":
#             body["detail"] = str(e)
#         return cors_response(500, body)


# def seed(event, context):
#     import time
#     import logging
#     logging.getLogger().setLevel("INFO")

#     try:
#         genres = ["pop", "rock", "lofi", "rap", "jazz", "electronic", "metal", "folk"]

#         # opcioni body (mali broj za start da izbegnemo timeout)
#         body = {}
#         if event.get("body"):
#             try:
#                 body = json.loads(event["body"])
#             except Exception:
#                 body = {}

#         n_artists = int(body.get("artists", 5))          # manjе default vrednosti
#         n_albums = int(body.get("albums", 10))
#         songs_per_album = int(body.get("songs_per_album", 5))

#         # helperi
#         def put_requests(items):
#             return [{"PutRequest": {"Item": it}} for it in items]

#         def write_batches(request_items):
#             """Client-level BatchWrite sa retry za UnprocessedItems"""
#             client = boto3.client("dynamodb")
#             unprocessed = {"RequestItems": {TABLE_NAME: request_items}}
#             backoff = 0.2
#             total_put = 0
#             while unprocessed["RequestItems"][TABLE_NAME]:
#                 resp = client.batch_write_item(**unprocessed)
#                 unp = resp.get("UnprocessedItems", {}).get(TABLE_NAME, [])
#                 total_put += len(unprocessed["RequestItems"][TABLE_NAME]) - len(unp)
#                 if unp:
#                     logging.info(f"Retrying {len(unp)} unprocessed items...")
#                     time.sleep(backoff)
#                     backoff = min(backoff * 2, 2.0)
#                     unprocessed = {"RequestItems": {TABLE_NAME: unp}}
#                 else:
#                     break
#             return total_put

#         # 1) ARTISTS
#         artist_ids = []
#         artist_items = []
#         for i in range(n_artists):
#             artist_id = str(uuid.uuid4())
#             g = random.choice(genres)
#             artist_items.append({
#                 "PK": {"S": f"ARTIST#{artist_id}"},
#                 "SK": {"S": "ARTIST"},
#                 "entityType": {"S": "ARTIST"},
#                 "name": {"S": f"Artist {i+1}"},
#                 "primaryGenre": {"S": g},
#                 "genres": {"L": [{"S": g}]},
#                 "GSI1PK": {"S": f"GENRE#{g}"},
#                 "GSI1SK": {"S": f"TYPE#ARTIST#NAME#artist-{i+1}"},
#             })
#             artist_ids.append(artist_id)

#         # piši po 25
#         total_written = 0
#         for i in range(0, len(artist_items), 25):
#             chunk = artist_items[i:i+25]
#             total_written += write_batches(put_requests(chunk))

#         # 2) ALBUMS + SONGS
#         album_song_items = []
#         for a in range(n_albums):
#             album_id = str(uuid.uuid4())
#             g = random.choice(genres)
#             artist_id = artist_ids[a % len(artist_ids)]

#             # album
#             album_song_items.append({
#                 "PK": {"S": f"ALBUM#{album_id}"},
#                 "SK": {"S": "ALBUM"},
#                 "entityType": {"S": "ALBUM"},
#                 "name": {"S": f"Album {a+1}"},
#                 "primaryGenre": {"S": g},
#                 "artistId": {"S": artist_id},
#                 "GSI1PK": {"S": f"GENRE#{g}"},
#                 "GSI1SK": {"S": f"TYPE#ALBUM#NAME#album-{a+1}"},
#             })

#             # songs
#             for t in range(1, songs_per_album + 1):
#                 album_song_items.append({
#                     "PK": {"S": f"SONG#{str(uuid.uuid4())}"},
#                     "SK": {"S": "SONG"},
#                     "entityType": {"S": "SONG"},
#                     "name": {"S": f"Song {a+1}-{t}"},
#                     "trackNo": {"N": str(t)},
#                     "albumId": {"S": album_id},
#                     "artistId": {"S": artist_id},
#                     "primaryGenre": {"S": g},
#                     "GSI1PK": {"S": f"GENRE#{g}"},
#                     "GSI1SK": {"S": f"TYPE#SONG#NAME#song-{a+1}-{t}"},
#                     "GSI2PK": {"S": f"ALBUM#{album_id}"},
#                     "GSI2SK": {"S": f"TRACK#{str(t).zfill(2)}"},
#                 })

#         for i in range(0, len(album_song_items), 25):
#             chunk = album_song_items[i:i+25]
#             total_written += write_batches(put_requests(chunk))

#         return cors_response(200, {
#             "message": "Seed completed",
#             "artists": n_artists,
#             "albums": n_albums,
#             "songs_per_album": songs_per_album,
#             "inserted": total_written
#         })

#     except Exception as e:
#         # detaljniji log ka CloudWatch-u
#         import traceback
#         traceback.print_exc()
#         return cors_response(500, {"message": "Internal Server Error", "detail": str(e)})


# def reset_music(event, context):
#     import time
#     import logging
#     logging.getLogger().setLevel("INFO")

#     try:
#         # 1) Skupi sve ključeve (PK, SK)
#         client = boto3.client("dynamodb")
#         keys = []
#         scan_kwargs = {
#             "TableName": TABLE_NAME,
#             "ProjectionExpression": "PK, SK",
#         }
#         while True:
#             resp = client.scan(**scan_kwargs)
#             items = resp.get("Items", [])
#             for it in items:
#                 keys.append({"PK": it["PK"], "SK": it["SK"]})
#             if "LastEvaluatedKey" in resp:
#                 scan_kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]
#             else:
#                 break

#         # 2) Batch delete po 25 sa retry
#         def delete_batch(key_batch):
#             req = [{"DeleteRequest": {"Key": k}} for k in key_batch]
#             unprocessed = {"RequestItems": {TABLE_NAME: req}}
#             backoff = 0.2
#             deleted = 0
#             while unprocessed["RequestItems"][TABLE_NAME]:
#                 r = client.batch_write_item(**unprocessed)
#                 unp = r.get("UnprocessedItems", {}).get(TABLE_NAME, [])
#                 deleted += len(unprocessed["RequestItems"][TABLE_NAME]) - len(unp)
#                 if unp:
#                     time.sleep(backoff)
#                     backoff = min(backoff * 2, 2.0)
#                     unprocessed = {"RequestItems": {TABLE_NAME: unp}}
#                 else:
#                     break
#             return deleted

#         total_deleted = 0
#         for i in range(0, len(keys), 25):
#             total_deleted += delete_batch(keys[i:i+25])

#         return cors_response(200, {"message": "Music truncated", "deleted": total_deleted})

#     except Exception as e:
#         import traceback, os
#         print("reset_music ERROR:", traceback.format_exc())
#         body = {"message": "Internal Server Error"}
#         if os.environ.get("DEBUG") == "1":
#             body["detail"] = str(e)
#         return cors_response(500, body)
