# Cloud Music App

A small music streaming app built on AWS serverless services. Started as a university project, written as a team.

Users can browse albums and artists by genre, subscribe to them and get notified when a new track is added. Admins manage artists, albums and tracks and upload audio files.

## Stack

- **Frontend:** Angular 20 (`frontend/`)
- **Backend:** Python 3.9 Lambda functions behind API Gateway, deployed with the Serverless Framework (`musicapp-backend/`)
- **Auth:** Amazon Cognito, admins are members of the `Admin` group
- **Data:** DynamoDB, audio files in S3

```
Angular ──► API Gateway ──► Lambda ──► DynamoDB (Music, Artists, Subscriptions, Notifications)
                              │
                              └──► S3 (presigned upload/play URLs)

Music table stream ──► notify_dispatcher Lambda ──► Notifications table
```

## Data model

Tracks, albums and artists share one `Music` table (single-table design).

| Entity | PK | SK |
|--------|----|----|
| Track  | `CONTENT#<id>` | `METADATA` |
| Album  | `ALBUM#<id>`   | `ALBUM` |
| Artist | `ARTIST#<id>`  | `ARTIST` |

- `GSI1` (`GENRE#<genre>` / `TYPE#<type>#NAME#<name>`) powers the discover page.
- `GSI2` (`ALBUM#<id>` / `TRACK#<nnn>`) lists the tracks of an album in order.

When a track is written, the table's DynamoDB stream triggers `notify_dispatcher`, which looks up subscribers of the track's album and artists and creates notifications for them.

## Running it

Backend (needs an AWS account and a Cognito user pool with an `Admin` group):

```bash
cd musicapp-backend
cp .env.example .env      # fill in USER_POOL_ID and CLIENT_ID
npm install
npx serverless deploy
```

Frontend:

```bash
cd frontend
# put the API URL from the deploy output into src/environments/environment.ts
npm install
npm start
```

The app is then at http://localhost:4200. CORS is currently set up for that origin only.

`musicapp-backend/handlers/generate_music.py` generates a few test WAV files (already committed in `musicapp-backend/demo_wav/`) for trying the upload flow.

## Known gaps

- Every Lambda shares one broad IAM role.
- No real tests, the `.spec.ts` files are Angular boilerplate.
- `GET /content` scans the whole table.

## Authors

- Maksim Privalov
- Jovana Panić
- Teodora Nikolić

## License

MIT, see [LICENSE](LICENSE).
