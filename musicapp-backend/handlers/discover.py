import os
import traceback
from boto3.dynamodb.conditions import Key, Attr
from utils.cors import response as cors_response
from utils.pagination import encode_last_key, decode_last_key
from utils.aws import music_table

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

        last_key = decode_last_key(params.get("lastKey"))

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

        return cors_response(200, {"items": out, "nextKey": encode_last_key(lek)})

    except Exception as e:
        print("discover ERROR:", traceback.format_exc())
        body = {"message": "Internal Server Error"}
        if os.environ.get("DEBUG") == "1":
            body["detail"] = str(e)
        return cors_response(500, body)

#                   4) Seed / Reset (admin)
