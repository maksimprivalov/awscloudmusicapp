import os
import json
import uuid
from datetime import datetime

import boto3
from utils.cors import response as cors_response

dynamodb = boto3.resource("dynamodb")
# bolje preko env var da se poklapa sa serverless.yml
TABLE_NAME = os.environ.get("TABLE_NAME", "Music")
ARTISTS_TABLE = os.environ.get("ARTISTS_TABLE", "Artists")

music_table = dynamodb.Table(TABLE_NAME)
artists_table = dynamodb.Table(ARTISTS_TABLE)

def _is_admin(event) -> bool:
    """Admin from Cognito JWT (through API Gateway Authorizer)."""
    claims = (event.get("requestContext", {})
                    .get("authorizer", {})
                    .get("claims", {})) or {}
    groups = claims.get("cognito:groups", "")
    return "Admin" in groups

def _slug(s: str) -> str:
    return "-".join((s or "").strip().lower().split())

def create_artist(event, context):
    if not _is_admin(event):
        return cors_response(403, {"error": "Admins only"})

    body = json.loads(event.get("body") or "{}")
    name   = (body.get("name") or "").strip()
    bio    = (body.get("bio") or "").strip()
    genres = body.get("genres", [])

    if not name or not bio:
        return cors_response(400, {"error": "name and bio required"})

    artist_id = str(uuid.uuid4())
    now = datetime.utcnow().isoformat()
    primary_genre = (genres[0].strip().lower() if genres else "unknown")

    # 1) primarni zapis u tabeli Artists
    artist_row = {
        "artistId": artist_id,
        "name": name,
        "bio": bio,
        "genres": genres,
        "createdAt": now,
        "updatedAt": now,
    }

    try:
        artists_table.put_item(Item=artist_row)

        # 2) mirror zapis u tabeli Music (da /discover vidi ARTIST-e preko GSI1)
        music_row = {
            "PK": f"ARTIST#{artist_id}",
            "SK": "ARTIST",
            "entityType": "ARTIST",
            "artistId": artist_id,
            "name": name,
            "primaryGenre": primary_genre,
            "genres": genres,
            "createdAt": now,
            "updatedAt": now,
            "GSI1PK": f"GENRE#{primary_genre}",
            "GSI1SK": f"TYPE#ARTIST#NAME#{_slug(name)}",
        }
        # zaštita od slučajnog overwrite-a
        music_table.put_item(
            Item=music_row,
            ConditionExpression="attribute_not_exists(PK) AND attribute_not_exists(SK)"
        )

        return cors_response(201, {"message": "Artist created", "artistId": artist_id})

    except Exception as e:
        return cors_response(500, {"error": str(e)})
