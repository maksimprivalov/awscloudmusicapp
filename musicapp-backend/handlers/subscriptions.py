# handlers/subscriptions.py
import os, json
import boto3
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError
from datetime import datetime

from utils.cors import ok, created, bad_request, not_found, preflight, response

dynamodb = boto3.resource("dynamodb")
subs_table = dynamodb.Table("Subscriptions")

ALLOWED_TARGETS = {"TRACK", "ALBUM", "ARTIST"}

def _user_id(event):
    claims = (event.get("requestContext") or {}).get("authorizer", {}).get("claims", {})
    return claims.get("sub")

def subscribe(event, context):
    if event.get("httpMethod") == "OPTIONS":
        return preflight(event)
    uid = _user_id(event)
    if not uid:
        return response(401, {"error": "Unauthorized"})
    try:
        body = json.loads(event.get("body") or "{}")
    except Exception:
        return bad_request("Invalid JSON")

    ttype = (body.get("targetType") or "").upper()
    tid = (body.get("targetId") or "").strip()
    if ttype not in ALLOWED_TARGETS or not tid:
        return bad_request("targetType ∈ {TRACK,ALBUM,ARTIST} and targetId required")

    try:
        subs_table.put_item(
            Item={
                "userId": uid,
                "targetKey": f"{ttype}#{tid}",
                "createdAt": datetime.utcnow().isoformat()
            },
            ConditionExpression="attribute_not_exists(userId) AND attribute_not_exists(targetKey)"
        )
        return created({"message": "Subscribed"})
    except ClientError as e:
        if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
            return ok({"message": "Already subscribed"})
        raise

def unsubscribe(event, context):
    if event.get("httpMethod") == "OPTIONS":
        return preflight(event)
    
    uid = _user_id(event)
    if not uid:
        return response(401, {"error": "Unauthorized"})
    try:
        body = json.loads(event.get("body") or "{}")
    except Exception:
        return bad_request("Invalid JSON")

    ttype = (body.get("targetType") or "").upper()
    tid = (body.get("targetId") or "").strip()
    if ttype not in ALLOWED_TARGETS or not tid:
        return bad_request("targetType ∈ {TRACK,ALBUM,ARTIST} and targetId required")

    subs_table.delete_item(Key={"userId": uid, "targetKey": f"{ttype}#{tid}"})
    return ok({"message": "Unsubscribed"})

def list_subscriptions(event, context):
    if event.get("httpMethod") == "OPTIONS":
        return preflight(event)
    uid = _user_id(event)
    if not uid:
        return response(401, {"error": "Unauthorized"})

    resp = subs_table.query(KeyConditionExpression=Key("userId").eq(uid))
    return ok(resp.get("Items", []))
