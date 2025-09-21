import boto3
import os
import json

cognito = boto3.client("cognito-idp")

USER_POOL_ID = os.environ["USER_POOL_ID"]
CLIENT_ID = os.environ["CLIENT_ID"]

def register(event, context):
    body = event.get("body")
    if body is None:
        return {"statusCode": 400, "body": "No data"}

    data = json.loads(body)

    try:
        response = cognito.sign_up(
            ClientId=CLIENT_ID,
            Username=data["email"],
            Password=data["password"],
            UserAttributes=[
                {"Name": "given_name", "Value": data["first_name"]},  # required
                {"Name": "family_name", "Value": data["last_name"]},  # required
                {"Name": "email", "Value": data["email"]},            # required
                {"Name": "birthdate", "Value": data["birthdate"]}     # required (YYYY-MM-DD)
            ],
        )
        return {
            "statusCode": 200,
            "body": json.dumps({
                "message": "User registered",
                "userSub": response["UserSub"]
            })
        }
    except Exception as e:
        return {"statusCode": 400, "body": str(e)}

def login(event, context):
    body = event.get("body")
    if body is None:
        return {"statusCode": 400, "body": "No data"}

    data = json.loads(body)

    try:
        response = cognito.initiate_auth(
            ClientId=CLIENT_ID,
            AuthFlow="USER_PASSWORD_AUTH",
            AuthParameters={
                "USERNAME": data["email"],
                "PASSWORD": data["password"]
            },
        )
        return {
            "statusCode": 200,
            "body": json.dumps(response["AuthenticationResult"])
        }
    except Exception as e:
        return {"statusCode": 400, "body": str(e)}
