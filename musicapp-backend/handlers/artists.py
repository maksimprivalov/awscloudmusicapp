import os
import json
import traceback
import boto3
from datetime import datetime
from boto3.dynamodb.conditions import Key, Attr
from utils.cors import response as cors_response, err
from utils.authz import is_admin
from utils.text import slug
from utils.aws import music_table, artists_table

# =============== 3) DELETE ARTIST (NE briše pesme) ========
def delete_artist(event, context):
    if not is_admin(event):
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
        return err(500, "Delete artist failed", e)

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

def update_artist(event, context):
    if not is_admin(event):
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
                "GSI1SK": f"TYPE#ARTIST#NAME#{slug(name or artist_id)}",
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
                u_eav[":g1sk"] = f"TYPE#ARTIST#NAME#{slug(name)}"
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

def get_artist_details(event, context):
    try:
        # CORS preflight
        if (event.get("httpMethod") or "").upper() == "OPTIONS":
            return cors_response(200, {})

        path = (event.get("pathParameters") or {})
        artist_id = path.get("artistId") or path.get("id")
        if not artist_id:
            return cors_response(400, {"error": "artistId path param required"})

        # 1) meta iz Artists
        meta = artists_table.get_item(Key={"artistId": artist_id}).get("Item")

        # 1b) fallback mirror iz Music
        if not meta:
            mirror = music_table.get_item(Key={"PK": f"ARTIST#{artist_id}", "SK": "ARTIST"}).get("Item")
            if mirror:
                meta = {
                    "artistId": artist_id,
                    "name": mirror.get("name"),
                    "genres": mirror.get("genres") or ([mirror.get("primaryGenre")] if mirror.get("primaryGenre") else []),
                    "bio": None,
                    "primaryGenre": mirror.get("primaryGenre")
                }

        if not meta:
            return cors_response(404, {"error": "Artist not found"})

        artist = {
            "artistId": artist_id,
            "name": meta.get("name"),
            "genres": meta.get("genres") or [],
            "primaryGenre": meta.get("primaryGenre") or ((meta.get("genres") or [None])[0]),
            "bio": meta.get("bio")
        }

        # 2) pesme gde je primarni artist (GSI2)
        q = music_table.query(
            IndexName="GSI2",
            KeyConditionExpression=Key("GSI2PK").eq(f"ARTIST#{artist_id}")
        )
        items = q.get("Items", [])
        tracks = []
        for it in items:
            pk = str(it.get("PK", ""))
            cid = it.get("contentId") or (pk.split("#", 1)[1] if pk.startswith("CONTENT#") else None)
            tracks.append({
                "contentId": cid,
                "name": it.get("name"),
                "trackNo": it.get("trackNo"),
                "albumId": it.get("albumId"),
                "durationSeconds": it.get("durationSeconds"),
            })

        return cors_response(200, {"artist": artist, "tracks": tracks})

    except Exception as e:
        print("[get_artist_details] ERROR\n", traceback.format_exc())
        # vrati čitljiv 500 umesto “golog” 502
        return cors_response(500, {"error": "Internal Server Error", "detail": str(e)})
