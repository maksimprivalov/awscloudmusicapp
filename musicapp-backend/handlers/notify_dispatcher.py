import os, json, uuid
from datetime import datetime
import boto3
from boto3.dynamodb.types import TypeDeserializer

ddb = boto3.client('dynamodb')
deser = TypeDeserializer()

SUBS_TABLE = os.getenv('SUBS_TABLE', 'Subscriptions')
SUBS_GSI   = os.getenv('SUBS_GSI',   'ByTarget')
NOTIF_TABLE= os.getenv('NOTIF_TABLE','Notifications')

def _d(x):  # DDB JSON -> python dict
    return {k: deser.deserialize(v) for k, v in x.items()}

def _as_list(v):
    if v is None: return []
    return v if isinstance(v, list) else [v]

def handler(event, context):
    puts = []
    for rec in event.get('Records', []):
        et = rec.get('eventName')  # INSERT | MODIFY | REMOVE
        if et not in ('INSERT','MODIFY'):
            continue

        new = rec.get('dynamodb', {}).get('NewImage')
        if not new:
            continue
        item = _d(new)

        # gledamo samo TRACK METADATA redove
        if item.get('entityType') != 'TRACK':
            continue
        if item.get('SK') != 'METADATA':
            continue

        content_id = item.get('contentId') or item.get('PK','').split('#',1)[-1]
        name       = item.get('name') or 'New track'
        album_id   = item.get('albumId')
        artists    = _as_list(item.get('artists'))
        primary_g  = item.get('primaryGenre')

        # ciljevi pretplate
        targets = set()
        if album_id:              targets.add(f'ALBUM#{album_id}')
        if artists:               targets.add(f'ARTIST#{artists[0]}')
        if primary_g:             targets.add(f'GENRE#{str(primary_g).lower()}')

        if not targets:
            continue

        # izvuci sve pretplaćene korisnike preko Subscriptions GSI
        user_ids = set()
        for tk in targets:
            resp = ddb.query(
                TableName=SUBS_TABLE,
                IndexName=SUBS_GSI,
                KeyConditionExpression='targetKey = :t',
                ExpressionAttributeValues={':t': {'S': tk}},
                ProjectionExpression='userId'
            )
            for r in resp.get('Items', []):
                user_ids.add(r['userId']['S'])

        if not user_ids:
            continue

        # pripremi notifikacije
        now = datetime.utcnow().isoformat()
        title = 'New track added'
        body  = name
        data  = {
            'contentId': content_id,
            'albumId': album_id,
            'artists': artists,
            'primaryGenre': primary_g
        }

        for uid in user_ids:
            notif_id = f"{now}#{uuid.uuid4().hex[:6]}"
            puts.append({
                'PutRequest': {'Item': {
                    'userId':   {'S': uid},
                    'notifId':  {'S': notif_id},
                    'type':     {'S': 'TRACK_ADDED'},
                    'title':    {'S': title},
                    'body':     {'S': body},
                    'targetType':{'S': 'MULTI'},
                    'targetId': {'S': list(targets)[0]},
                    'contentId':{'S': content_id},
                    'createdAt':{'S': now},
                    'unread':   {'BOOL': True},
                    'data':     {'S': json.dumps(data)}
                }}
            })

    # batch write u chunkovima do 25
    while puts:
        chunk = puts[:25]; puts = puts[25:]
        ddb.batch_write_item(RequestItems={NOTIF_TABLE: chunk})

    return {'statusCode': 200}
