import os, json, urllib.parse
import boto3
from boto3.dynamodb.conditions import Key

from utils.cors import response as cors_response

dynamodb = boto3.resource("dynamodb")
# čita NOTIF_TABLE; ako ga nema, koristi "Notifications"
table = dynamodb.Table(os.getenv("NOTIF_TABLE", os.getenv("NOTIFS_TABLE", "Notifications")))

def _uid(event):
    return (event.get("requestContext") or {}).get("authorizer", {}).get("claims", {}).get("sub")

def _enc_last_key(lek):
    if not lek:
        return None
    return urllib.parse.quote(json.dumps(lek))  # ključevi su stringovi → bez Decimal problema

def _dec_last_key(s):
    if not s:
        return None
    try:
        return json.loads(urllib.parse.unquote(s))
    except Exception:
        return None

def list_notifications(event, context):
    if (event.get("httpMethod") or "").upper() == "OPTIONS":
        return cors_response(200, {})

    uid = _uid(event)
    if not uid:
        return cors_response(401, {"error": "Unauthorized"})

    qs = event.get("queryStringParameters") or {}
    try:
        limit = max(1, min(int(qs.get("limit") or "20"), 100))
    except Exception:
        limit = 20

    last_key = _dec_last_key(qs.get("lastKey"))

    try:
        kwargs = {
            "KeyConditionExpression": Key("userId").eq(uid),  # ✅ ispravno
            "ScanIndexForward": False,  # najnovije prvo
            "Limit": limit,
        }
        if last_key:
            kwargs["ExclusiveStartKey"] = last_key

        resp = table.query(**kwargs)
        items = resp.get("Items", [])
        lek = resp.get("LastEvaluatedKey")

        return cors_response(200, {
            "items": items,
            "nextKey": _enc_last_key(lek)
        })
    except Exception as e:
        print("list_notifications ERROR:", e)
        return cors_response(500, {"error": "Internal Server Error"})

def mark_read(event, context):
    if (event.get("httpMethod") or "").upper() == "OPTIONS":
        return cors_response(200, {})

    uid = _uid(event)
    if not uid:
        return cors_response(401, {"error": "Unauthorized"})

    try:
        body = json.loads(event.get("body") or "{}")
    except Exception:
        return cors_response(400, {"error": "Invalid JSON"})

    nid = (body.get("notifId") or "").strip()
    if not nid:
        return cors_response(400, {"error": "notifId required"})

    try:
        table.update_item(
            Key={"userId": uid, "notifId": nid},
            UpdateExpression="SET #u = :f",
            ExpressionAttributeNames={"#u": "unread"},
            ExpressionAttributeValues={":f": False},
            ConditionExpression="attribute_exists(userId) AND attribute_exists(notifId)"
        )
        return cors_response(200, {"ok": True})
    except Exception as e:
        print("mark_read ERROR:", e)
        return cors_response(500, {"error": "Internal Server Error"})

def mark_all_read(event, context):
    if (event.get("httpMethod") or "").upper() == "OPTIONS":
        return cors_response(200, {})

    uid = _uid(event)
    if not uid:
        return cors_response(401, {"error": "Unauthorized"})

    try:
        resp = table.query(
            KeyConditionExpression=Key("userId").eq(uid),
            ScanIndexForward=False,
            Limit=100
        )
        items = resp.get("Items", [])
        with table.batch_writer() as bw:
            for it in items:
                if it.get("unread"):
                    bw.put_item(Item={**it, "unread": False})
        return cors_response(200, {"ok": True})
    except Exception as e:
        print("mark_all_read ERROR:", e)
        return cors_response(500, {"error": "Internal Server Error"})
