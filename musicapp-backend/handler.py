import boto3
import os
import json
import uuid
from datetime import datetime

cognito = boto3.client("cognito-idp")

USER_POOL_ID = os.environ["USER_POOL_ID"]
CLIENT_ID = os.environ["CLIENT_ID"]

dynamodb = boto3.resource("dynamodb")
tableArtists = dynamodb.Table("Artists")

def create_artist(event, context):
    claims = event["requestContext"]["authorizer"]["claims"]
    groups = claims.get("cognito:groups", "")

    if "Admin" not in groups:
        return {"statusCode": 403, "body": "Forbidden – Admins only"}

    body = json.loads(event.get("body") or "{}")

    name = body.get("name")
    bio = body.get("bio")
    genres = body.get("genres", [])

    if not name or not bio:
        return {"statusCode": 400, "body": "Name and bio required"}

    artist_id = str(uuid.uuid4())

    item = {
        "artistId": artist_id,
        "name": name,
        "bio": bio,
        "genres": genres,
        "createdAt": datetime.utcnow().isoformat()
    }

    try:
        tableArtists.put_item(Item=item)
        return {
            "statusCode": 201,
            "body": json.dumps({"message": "Artist created", "artistId": artist_id})
        }
    except Exception as e:
        return {"statusCode": 500, "body": str(e)}
    
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
                {"Name": "given_name", "Value": data["first_name"]},
                {"Name": "family_name", "Value": data["last_name"]},
                {"Name": "email", "Value": data["email"]},
                {"Name": "birthdate", "Value": data["birthdate"]}
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
