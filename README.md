# Kaiten Matrix Bridge

Production-style MVP bridge between Kaiten and an existing self-hosted Matrix stack.

## What it does

- Accepts Kaiten webhooks at `POST /webhook/kaiten/{slug}`.
- Formats incoming Kaiten events and posts them into the mapped Matrix room.
- Runs a Matrix bot that auto-joins invites and listens in mapped rooms.
- Supports `!help`, `!task Title | description`, and `!card 123`.
- Creates and retrieves Kaiten cards through the Kaiten API.

## Repository layout

```text
kaiten-matrix-bridge/
├─ app/
│  ├─ __init__.py
│  ├─ main.py
│  ├─ config.py
│  ├─ kaiten.py
│  ├─ matrix_bot.py
│  ├─ formatter.py
│  └─ models.py
├─ requirements.txt
├─ Dockerfile
├─ compose.yml
├─ .env.example
├─ config.example.yaml
├─ README.md
└─ .gitignore
```

## Environment variables

Copy `.env.example` to `.env` and fill these values:

```env
KAITEN_API_BASE_URL=https://YOURCOMPANY.kaiten.ru/api/latest
KAITEN_WEB_BASE_URL=https://YOURCOMPANY.kaiten.ru
KAITEN_TOKEN=

MATRIX_HOMESERVER=https://matrix.fishingteam.su
MATRIX_USER_ID=@kbot:matrix.fishingteam.su
MATRIX_PASSWORD=

BRIDGE_SECRET=
LOG_LEVEL=INFO
CONFIG_PATH=/app/config.yaml
DATA_DIR=/app/data
```

Notes:

- If `KAITEN_API_BASE_URL` is set to the bare Kaiten domain, the app appends `/api/latest` automatically.
- `BRIDGE_SECRET` is the default webhook secret for every project mapping unless a project-specific `webhook_secret` is set in `config.yaml`.

## Mapping file

Copy `config.example.yaml` to `config.yaml` and adjust the room/board mapping:

```yaml
projects:
  alpha:
    room_id: "!REAL_MATRIX_ROOM_ID:matrix.fishingteam.su"
    board_id: 123
    position: 2
```

Supported project fields:

- `room_id`: Matrix room id where Kaiten events are posted.
- `board_id`: Kaiten board id used for `!task`.
- `position`: `1` for first in cell, `2` for last in cell.
- `column_id`: optional fixed column for new cards.
- `lane_id`: optional fixed lane for new cards.
- `webhook_secret`: optional per-project secret override.

Behavior:

- Webhook to `/webhook/kaiten/alpha` posts to the configured `room_id`.
- Matrix commands in that room create cards in `board_id`.

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

The service listens on `0.0.0.0:8000` inside the container and is exposed on host port `8060`.

## Reverse proxy via existing Caddy

Add this block to `/opt/matrix-stack/caddy/Caddyfile`:

```caddy
bridge.fishingteam.su {
    reverse_proxy host.docker.internal:8060
}
```

Then restart Caddy from the Matrix stack:

```bash
cd /opt/matrix-stack
sudo docker compose restart caddy
```

If the existing `caddy` service does not already resolve `host.docker.internal`, add this under the `caddy` service in `/opt/matrix-stack/docker-compose.yml`:

```yaml
extra_hosts:
  - "host.docker.internal:host-gateway"
```

## Bot behavior

- Uses a dedicated Matrix account such as `@kbot:matrix.fishingteam.su`.
- Auto-joins invited rooms.
- Ignores its own messages.
- Reacts only in rooms listed in `config.yaml`.
- Intended for a non-encrypted room for the MVP.

Create the Matrix bot account if needed:

```bash
cd /opt/matrix-stack
sudo docker compose exec synapse register_new_matrix_user http://localhost:8008 -c /data/homeserver.yaml
```

Recommended values:

- username: `kbot`
- password: choose a strong real password
- admin: `no`

## HTTP API

### `GET /healthz`

Returns JSON health status.

### `POST /webhook/kaiten/{slug}`

Auth methods:

- query string `?secret=...`
- or header `X-Bridge-Secret: ...`

Example:

```bash
curl -X POST "https://bridge.fishingteam.su/webhook/kaiten/alpha?secret=YOUR_BRIDGE_SECRET" \
  -H "Content-Type: application/json" \
  -d '{"event":"card.created","card":{"id":101,"title":"Test card"}}'
```

Example Matrix output:

```text
[Kaiten] card.created: #101 Test card
https://YOURCOMPANY.kaiten.ru/cards/101
```

If a comment exists in the payload, it is included as a second line.

## Matrix commands

### `!help`

Shows the available commands.

### `!task Title | description`

Creates a new card in the mapped Kaiten board and replies with:

```text
Created card #101: Prepare landing page
https://YOURCOMPANY.kaiten.ru/cards/101
```

### `!card 123`

Looks up a card by id and replies with title and link.

## Testing checklist

### 1. Local/HTTP health

```bash
curl http://127.0.0.1:8060/healthz
curl https://bridge.fishingteam.su/healthz
```

### 2. Kaiten webhook test

```bash
curl -X POST "https://bridge.fishingteam.su/webhook/kaiten/alpha?secret=YOUR_BRIDGE_SECRET" \
  -H "Content-Type: application/json" \
  -d '{"event":"card.created","card":{"id":101,"title":"Test card"}}'
```

Expected result:

- HTTP 200
- Matrix room receives a readable message

### 3. Matrix command test

Send this in the mapped Matrix room:

```text
!task Test from Matrix | created by bot command
```

Expected result:

- a card is created in Kaiten
- room receives confirmation with link

### 4. Card lookup test

Send this in the Matrix room:

```text
!card 101
```

Expected result:

- room receives card title + link

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

## Exact deploy steps for this server

1. Ensure `bridge.fishingteam.su` resolves to `79.174.90.22`. If missing, create DNS record `A bridge -> 79.174.90.22`.
2. Put this repository on the server at `/opt/kaiten-matrix-bridge`.
3. Create `.env` and `config.yaml` from the examples.
4. Make sure the Matrix bot account exists and is invited to the target non-encrypted room.
5. Start the bridge:

   ```bash
   cd /opt/kaiten-matrix-bridge
   docker compose -f compose.yml up -d --build
   ```

6. Add the Caddy route in `/opt/matrix-stack/caddy/Caddyfile`.
7. Restart Caddy:

   ```bash
   cd /opt/matrix-stack
   sudo docker compose restart caddy
   ```

8. Verify:

   ```bash
   curl http://127.0.0.1:8060/healthz
   curl -I https://bridge.fishingteam.su/healthz
   ```

## Extending after MVP

The code is intentionally split into small modules so the next features fit cleanly:

- `!comment <card_id> | text`
- `!move <card_id> | column_or_status`
- richer webhook normalization and formatting
- Matrix user to Kaiten user mapping
- tests for command parsing and formatters
