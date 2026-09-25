import json
import traceback
from datetime import datetime
from decimal import Decimal
from urllib.parse import unquote
from boto3.dynamodb.conditions import Key
from utils.cors import response as cors_response, err
from utils.authz import is_admin
from utils.aws import s3, music_table, BUCKET

def delete_album(event, context):
    if not is_admin(event):
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
        return err(500, "Cascade delete for album failed", e)

def create_album(event, context):
    if not is_admin(event):
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
    if not is_admin(event):
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
        return err(500, "Album meta update failed", e)

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
        return err(500, "Get album failed", e)

def _safe_num(x):
    # Dynamo Decimal -> int/float, ili None
    try:
        from decimal import Decimal
        if isinstance(x, Decimal):
            return int(x) if x % 1 == 0 else float(x)
    except Exception:
        pass
    return x

def get_album_details(event, context):
    try:
        # CORS preflight
        if (event.get("httpMethod") or "").upper() == "OPTIONS":
            return cors_response(200, {})

        path = (event.get("pathParameters") or {})
        album_id = path.get("albumId") or path.get("id")
        if not album_id:
            return cors_response(400, {"error": "albumId path param required"})

        # 1) Meta zapis: PK = ALBUM#<id>, SK = ALBUM
        album_pk = f"ALBUM#{album_id}"
        meta = music_table.get_item(Key={"PK": album_pk, "SK": "ALBUM"}).get("Item")

        # 2) Pesme u albumu: GSI2PK = ALBUM#<id>
        q = music_table.query(
            IndexName="GSI2",
            KeyConditionExpression=Key("GSI2PK").eq(album_pk)
        )
        items = q.get("Items", [])

        # sortiranje po GSI2SK (TRACK#NNN) ili po trackNo
        def sort_key(it):
            g2 = str(it.get("GSI2SK") or "")
            if g2.startswith("TRACK#") and len(g2) >= 9:
                # TRACK#001 → 1
                try:
                    return int(g2.split("#", 1)[1])
                except Exception:
                    pass
            tn = _safe_num(it.get("trackNo"))
            return tn if isinstance(tn, (int, float)) else 10**9  # nepoznati na kraj

        items.sort(key=sort_key)

        tracks = []
        for it in items:
            pk = str(it.get("PK", ""))
            cid = it.get("contentId") or (pk.split("#", 1)[1] if pk.startswith("CONTENT#") else None)
            tracks.append({
                "contentId": cid,
                "name": it.get("name"),
                "trackNo": _safe_num(it.get("trackNo")),
                "albumId": album_id,
                "durationSeconds": _safe_num(it.get("durationSeconds")),
            })

        # 3) Ako nema meta – pokušaj izvesti minimum iz pesama (fallback)
        cover_url = None
        if not meta:
            if not items:
                return cors_response(404, {"error": "Album not found"})
            # izvedi naziv / žanr iz pesama
            # (ako nema ničega, neka ostane None/unknown)
            name = None
            for it in items:
                if it.get("albumName"):
                    name = it["albumName"]
                    break
            primary_genre = None
            for it in items:
                if it.get("primaryGenre"):
                    primary_genre = it["primaryGenre"]
                    break

            album = {
                "albumId": album_id,
                "name": name or album_id,
                "primaryGenre": primary_genre,
                "description": None
            }
            return cors_response(200, {"album": album, "tracks": tracks})

        # 4) Ako ima meta – pripremi odgovor + cover URL ako postoji
        album = {
            "albumId": album_id,
            "name": meta.get("name") or album_id,
            "primaryGenre": meta.get("primaryGenre"),
            "description": meta.get("description"),
        }

        cover_key = meta.get("coverS3Key")
        if BUCKET and cover_key:
            try:
                cover_url = s3.generate_presigned_url(
                    "get_object",
                    Params={"Bucket": BUCKET, "Key": cover_key},
                    ExpiresIn=3600
                )
            except Exception:
                cover_url = None

        return cors_response(200, {"album": album, "tracks": tracks, "coverUrl": cover_url})

    except Exception as e:
        print("[get_album_details] ERROR\n", traceback.format_exc())
        return cors_response(500, {"error": "Internal Server Error", "detail": str(e)})
