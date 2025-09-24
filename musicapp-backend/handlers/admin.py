import os
import json
import uuid
from datetime import datetime

import boto3
from utils.cors import response as cors_response

dynamodb = boto3.resource("dynamodb")
artists_table = dynamodb.Table("Artists")

def _is_admin(event) -> bool:
    """Admin from Cognito JWT (through API Gateway Authorizer)."""
    claims = (event.get("requestContext", {})
                    .get("authorizer", {})
                    .get("claims", {})) or {}
    groups = claims.get("cognito:groups", "")
    return "Admin" in groups

def create_artist(event, context):
    if not _is_admin(event):
        return cors_response(403, {"error": "Admins only"})

    body = json.loads(event.get("body") or "{}")
    name  = body.get("name")
    bio   = body.get("bio")
    genres = body.get("genres", [])

    if not name or not bio:
        return cors_response(400, {"error": "name and bio required"})

    artist_id = str(uuid.uuid4())
    item = {
        "artistId": artist_id,
        "name": name,
        "bio": bio,
        "genres": genres,
        "createdAt": datetime.utcnow().isoformat(),
    }

    try:
        artists_table.put_item(Item=item)
        return cors_response(201, {"message": "Artist created", "artistId": artist_id})
    except Exception as e:
        return cors_response(500, {"error": str(e)})
