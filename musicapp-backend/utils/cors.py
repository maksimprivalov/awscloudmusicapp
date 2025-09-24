# utils/cors.py
import os
import json

ALLOWED_ORIGIN = os.getenv("ALLOWED_ORIGIN", "http://localhost:4200")

DEFAULT_HEADERS = {
    "Access-Control-Allow-Origin": ALLOWED_ORIGIN,
    "Access-Control-Allow-Credentials": "true",
    "Access-Control-Allow-Headers": "Content-Type,Authorization",
    "Access-Control-Allow-Methods": "GET,POST,PUT,DELETE,OPTIONS",
}

def response(status: int, body):
    return {
        "statusCode": status,
        "headers": DEFAULT_HEADERS,
        "body": json.dumps(body) if not isinstance(body, str) else body,
    }

def ok(body):         return response(200, body)
def created(body):    return response(201, body)
def bad_request(msg): return response(400, {"error": msg})
def forbidden(msg="Forbidden"): return response(403, {"error": msg})
def not_found(msg="Not found"): return response(404, {"error": msg})
def server_error(msg="Internal Server Error"): return response(500, {"error": msg})

# def preflight():
#     return {"statusCode": 204, "headers": DEFAULT_HEADERS, "body": ""}
