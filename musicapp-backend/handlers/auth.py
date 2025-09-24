import os, json, boto3
from utils.cors import response as cors_response

cognito = boto3.client("cognito-idp")
USER_POOL_ID = os.environ["USER_POOL_ID"]
CLIENT_ID    = os.environ["CLIENT_ID"]

def register(event, context):
    body = json.loads(event.get("body") or "{}")
    if not body:
        return cors_response(400, {"error": "No data"})

    required = ("first_name","last_name","email","password","birthdate")
    if any(k not in body or not body[k] for k in required):
        return cors_response(400, {"error": f"Missing fields: {', '.join([k for k in required if not body.get(k)])}"})

    try:
        resp = cognito.sign_up(
            ClientId=CLIENT_ID,
            Username=body["email"],
            Password=body["password"],
            UserAttributes=[
                {"Name": "given_name",  "Value": body["first_name"]},
                {"Name": "family_name", "Value": body["last_name"]},
                {"Name": "email",       "Value": body["email"]},
                {"Name": "birthdate",   "Value": body["birthdate"]},
            ],
        )
        return cors_response(200, {"message":"User registered", "userSub": resp["UserSub"]})
    except Exception as e:
        return cors_response(400, {"error": str(e)})

def login(event, context):
    body = json.loads(event.get("body") or "{}")
    if not body:
        return cors_response(400, {"error": "No data"})
    if not body.get("email") or not body.get("password"):
        return cors_response(400, {"error": "email and password required"})

    try:
        resp = cognito.initiate_auth(
            ClientId=CLIENT_ID,
            AuthFlow="USER_PASSWORD_AUTH",
            AuthParameters={"USERNAME": body["email"], "PASSWORD": body["password"]},
        )
        return cors_response(200, resp["AuthenticationResult"])
    except Exception as e:
        return cors_response(400, {"error": str(e)})

def refresh_token(event, context):
    body = json.loads(event.get("body") or "{}")
    rt = body.get("refreshToken")
    if not rt:
        return cors_response(400, {"error": "refreshToken required"})
    try:
        resp = cognito.initiate_auth(
            ClientId=CLIENT_ID,
            AuthFlow="REFRESH_TOKEN_AUTH",
            AuthParameters={"REFRESH_TOKEN": rt},
        )
        return cors_response(200, resp["AuthenticationResult"])
    except Exception as e:
        return cors_response(400, {"error": str(e)})
