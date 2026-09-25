import os
import boto3

s3 = boto3.client("s3")
dynamodb = boto3.resource("dynamodb")

TABLE_NAME = os.environ.get("TABLE_NAME", "Music")
music_table = dynamodb.Table(TABLE_NAME)

ARTISTS_TABLE = os.getenv("ARTISTS_TABLE", "Artists")
artists_table = dynamodb.Table(ARTISTS_TABLE)

BUCKET = os.environ["BUCKET_NAME"]
