import os, json
from datetime import datetime
import boto3
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

ALLOWED_ORIGIN = os.environ.get("ALLOWED_ORIGIN", "http://localhost:4200")

def cors_response(status, body):
    return {
        "statusCode": status,
        "headers": {
            "Access-Control-Allow-Origin": ALLOWED_ORIGIN,
            "Access-Control-Allow-Credentials": "true",
            "Access-Control-Allow-Headers": "Content-Type,Authorization",
            "Access-Control-Allow-Methods": "GET,POST,PUT,DELETE,OPTIONS",
        },
        "body": json.dumps(body) if not isinstance(body, str) else body,
    }

dynamodb = boto3.resource("dynamodb")
subs_table = dynamodb.Table("Subscriptions")

ALLOWED_TARGETS = {"TRACK", "ALBUM", "ARTIST"}

def _user_id_from_event(event):
    claims = (event.get("requestContext") or {}).get("authorizer", {}).get("claims", {})

    return claims.get("sub")

def subscribe(event, context):
    uid = _user_id_from_event(event)
    if not uid:
        return cors_response(401, {"error": "Unauthorized"})
    try:
        body = json.loads(event.get("body") or "{}")
    except Exception:
        return cors_response(400, {"error": "Invalid JSON"})

    ttype = (body.get("targetType") or "").upper()
    tid = (body.get("targetId") or "").strip()

    if ttype not in ALLOWED_TARGETS or not tid:
        return cors_response(400, {"error": "targetType ∈ {TRACK,ALBUM,ARTIST} and targetId required"})

    try:
        subs_table.put_item(
            Item={
                "userId": uid,
                "targetKey": f"{ttype}#{tid}",
                "createdAt": datetime.utcnow().isoformat()
            },
            ConditionExpression="attribute_not_exists(userId) AND attribute_not_exists(targetKey)"
        )
        return cors_response(201, {"message": "Subscribed"})
    except ClientError as e:

        if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
            return cors_response(200, {"message": "Already subscribed"})
        raise

def unsubscribe(event, context):
    uid = _user_id_from_event(event)
    if not uid:
        return cors_response(401, {"error": "Unauthorized"})
    try:
        body = json.loads(event.get("body") or "{}")
    except Exception:
        return cors_response(400, {"error": "Invalid JSON"})

    ttype = (body.get("targetType") or "").upper()
    tid = (body.get("targetId") or "").strip()
    if ttype not in ALLOWED_TARGETS or not tid:
        return cors_response(400, {"error": "targetType ∈ {TRACK,ALBUM,ARTIST} and targetId required"})

    subs_table.delete_item(Key={"userId": uid, "targetKey": f"{ttype}#{tid}"})
    return cors_response(200, {"message": "Unsubscribed"})

def list_subscriptions(event, context):
    uid = _user_id_from_event(event)
    if not uid:
        return cors_response(401, {"error": "Unauthorized"})

    resp = subs_table.query(
        KeyConditionExpression=Key("userId").eq(uid)
    )
    # [{ userId, targetKey, createdAt }, ...]
    return cors_response(200, resp.get("Items", []))
