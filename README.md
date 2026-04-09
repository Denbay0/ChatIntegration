# Taiga Matrix Bridge

Production-style MVP bridge between Taiga and a self-hosted Matrix stack.

The repository path on the server remains `/opt/kaiten-matrix-bridge` for compatibility, but the code now targets Taiga.

## What it does

- Accepts Taiga webhooks and posts readable notifications to Matrix.
- Runs a Matrix bot that auto-joins invites and listens in mapped rooms.
- Supports:
  - `!help`
  - `!task Title | description`
- Creates Taiga user stories through the Taiga API.

## Repository layout

```text
kaiten-matrix-bridge/
├─ app/
│  ├─ __init__.py
│  ├─ main.py
│  ├─ config.py
│  ├─ taiga.py
│  ├─ matrix_bot.py
│  ├─ formatter.py
│  └─ models.py
├─ requirements.txt
├─ Dockerfile
├─ compose.yml
├─ .env.example
├─ config.example.yaml
├─ README.md
├─ .dockerignore
└─ .gitignore
```

## Environment variables

Copy `.env.example` to `.env` and fill the real values:

```env
TAIGA_BASE_URL=https://tree.taiga.io
TAIGA_API_URL=https://api.taiga.io/api/v1
TAIGA_USERNAME=
TAIGA_PASSWORD=
TAIGA_TOKEN=
TAIGA_PROJECT_ID=
TAIGA_PROJECT_SLUG=

MATRIX_HOMESERVER=https://matrix.fishingteam.su
MATRIX_USER_ID=@kbot:matrix.fishingteam.su
MATRIX_PASSWORD=

BRIDGE_SECRET=
LOG_LEVEL=INFO
CONFIG_PATH=/app/config.yaml
DATA_DIR=/app/data
```

Notes:

- `TAIGA_TOKEN` is optional. If set, the bridge uses it directly. Otherwise it logs in with `TAIGA_USERNAME` and `TAIGA_PASSWORD`.
- `TAIGA_PROJECT_ID` and `TAIGA_PROJECT_SLUG` act as defaults. Per-room values in `config.yaml` override them.
- `BRIDGE_SECRET` is used both for manual webhook testing and as the Taiga webhook HMAC key.

## Mapping file

Copy `config.example.yaml` to `config.yaml` and adjust the room/project mapping:

```yaml
projects:
  alpha:
    room_id: "!REAL_MATRIX_ROOM_ID:matrix.fishingteam.su"
    project_id: 1784454
    project_slug: denbay0-test
```

Supported project fields:

- `room_id`: Matrix room id where Taiga events are posted.
- `project_id`: Taiga numeric project id used for `!task`.
- `project_slug`: Taiga project slug used for link building fallback.
- `webhook_secret`: optional per-room webhook secret override.

## Local run

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
cp config.example.yaml config.yaml
uvicorn app.main:create_app --factory --host 0.0.0.0 --port 8000
```

## Docker deployment

Expected server workflow:

```bash
cd /opt/kaiten-matrix-bridge
cp .env.example .env
cp config.example.yaml config.yaml
nano .env
nano config.yaml
docker compose -f compose.yml up -d --build
```

The service listens on `0.0.0.0:8000` in the container and is published on host port `8060`.

## Reverse proxy via Caddy

The bridge is exposed through the existing Caddy instance in `/opt/matrix-stack/caddy/Caddyfile`:

```caddy
bridge.fishingteam.su {
    reverse_proxy host.docker.internal:8060
}
```

If you change the Caddyfile, restart Caddy:

```bash
cd /opt/matrix-stack
docker compose restart caddy
```

## Matrix bot behavior

- Uses a dedicated Matrix account such as `@kbot:matrix.fishingteam.su`.
- Auto-joins invited rooms.
- Ignores its own messages.
- Reacts only in rooms listed in `config.yaml`.
- Intended for a non-encrypted room for the MVP.

Create the Matrix bot account if needed:

```bash
cd /opt/matrix-stack
docker compose exec synapse register_new_matrix_user \
  http://localhost:8008 \
  -c /data/homeserver.yaml
```

## HTTP API

### `GET /healthz`

Returns JSON health status.

`HEAD /healthz` is also supported.

### `POST /webhook/taiga/{slug}`

Primary auth mode for real Taiga webhooks:

- header `X-TAIGA-WEBHOOK-SIGNATURE`
- value is `hex(hmac_sha1(raw_body, BRIDGE_SECRET))`

Fallback auth modes for manual testing:

- query string `?secret=...`
- or header `X-Bridge-Secret: ...`

Compatibility alias:

- `POST /webhook/kaiten/{slug}` points to the same handler

Example Matrix output:

```text
[Taiga] created user story: #72 Demo story - denbay0
https://tree.taiga.io/project/denbay0-test/us/72
```

## Matrix commands

### `!help`

Shows the available commands.

### `!task Title | description`

Creates a Taiga user story in the mapped project and replies with:

```text
Created Taiga user story #72: Demo story
https://tree.taiga.io/project/denbay0-test/us/72
```

## How to get Taiga token and project id

### Auth token

Official Taiga auth flow:

```bash
curl -X POST https://api.taiga.io/api/v1/auth \
  -H "Content-Type: application/json" \
  -d '{
    "type": "normal",
    "username": "YOUR_USERNAME",
    "password": "YOUR_PASSWORD"
  }'
```

The response contains `auth_token`. You can set that token in `TAIGA_TOKEN` if you prefer token-based auth for the bridge.

### Project id

Resolver by slug:

```bash
curl "https://api.taiga.io/api/v1/resolver?project=YOUR_PROJECT_SLUG"
```

Example response:

```json
{"project": 1784454}
```

You can also fetch full public project metadata:

```bash
curl "https://api.taiga.io/api/v1/projects/by_slug?slug=YOUR_PROJECT_SLUG"
```

## Manual webhook test

Quick secret-based test:

```bash
curl -X POST "https://bridge.fishingteam.su/webhook/taiga/alpha?secret=YOUR_BRIDGE_SECRET" \
  -H "Content-Type: application/json" \
  -d '{
    "type": "userstory",
    "action": "create",
    "data": {
      "ref": 72,
      "subject": "Manual webhook test",
      "permalink": "https://tree.taiga.io/project/denbay0-test/us/72"
    },
    "by": {
      "username": "denbay0"
    }
  }'
```

Real HMAC-style test:

```bash
BODY='{"type":"userstory","action":"create","data":{"ref":72,"subject":"Manual webhook test","permalink":"https://tree.taiga.io/project/denbay0-test/us/72"},"by":{"username":"denbay0"}}'
SIG=$(printf '%s' "$BODY" | openssl dgst -sha1 -hmac "$BRIDGE_SECRET" -hex | sed 's/^.* //')
curl -X POST "https://bridge.fishingteam.su/webhook/taiga/alpha" \
  -H "Content-Type: application/json" \
  -H "X-TAIGA-WEBHOOK-SIGNATURE: $SIG" \
  -d "$BODY"
```

## Smoke test

### 1. Health

```bash
curl https://bridge.fishingteam.su/healthz
curl -I https://bridge.fishingteam.su/healthz
```

### 2. Matrix bot

Invite `@kbot:matrix.fishingteam.su` to the target room if it is not there yet.

### 3. Matrix commands

In the mapped Matrix room:

```text
!help
!task Test from Matrix | created by the bridge
```

Expected result:

- bot replies in the room
- Taiga user story is created
- reply contains a working Taiga link

### 4. Taiga webhook

Configure a Taiga webhook with:

- URL: `https://bridge.fishingteam.su/webhook/taiga/alpha`
- secret key: same value as `BRIDGE_SECRET` or `projects.alpha.webhook_secret`

Then create or update a user story in Taiga and verify the Matrix room receives a notification.

## Operational commands

### Build / start

```bash
cd /opt/kaiten-matrix-bridge
docker compose -f compose.yml up -d --build
```

### View logs

```bash
cd /opt/kaiten-matrix-bridge
docker compose -f compose.yml logs -f
```

### Restart

```bash
cd /opt/kaiten-matrix-bridge
docker compose -f compose.yml restart
```

### Stop

```bash
cd /opt/kaiten-matrix-bridge
docker compose -f compose.yml down
```

## Exact server location

- Bridge code: `/opt/kaiten-matrix-bridge`
- Caddy config: `/opt/matrix-stack/caddy/Caddyfile`
- Existing Caddy backup: `/opt/matrix-stack/caddy/Caddyfile.bak.kaiten-bridge`

## Extending after MVP

The code is intentionally split into small modules so the next features fit cleanly:

- `!comment <us_ref> | text`
- `!move <us_ref> | status`
- richer webhook formatting
- Matrix user to Taiga user mapping
- tests for command parsing and webhook normalization
