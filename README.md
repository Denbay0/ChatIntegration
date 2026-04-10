# Taiga Matrix Bridge

Русскоязычный bridge между Matrix/Element и Taiga с project-room flow: бот, room widget, webhook-уведомления, bind script для новых комнат и короткая шапка-инструкция в самой комнате.

## Что умеет сейчас

- webhook из Taiga пишет обновления обратно в Matrix
- бот понимает `!help`, `!task`, `!tasks`, `!open`, `!my`, `!comment`
- задачи создаются из чата и из widget
- widget в комнате показывает одну главную секцию `Задачи проекта` без дублирования `Фокус по задачам` / `Последние задачи`
- bind script подключает новую комнату к проекту Taiga через один flow
- bridge можно перегрузить по config без общего рестарта контейнера

## Project Room Template

После bind room получает:

- bot `@kbot:matrix.fishingteam.su`
- widget `Доска Taiga` в room state
- русскую шапку-инструкцию в виде notice-сообщения
- mapping `room_id ↔ project_id/project_slug ↔ widget_url ↔ webhook_url`
- webhook Taiga для обратных уведомлений

## Команды бота

- `!help` / `!помощь` — показать подсказку
- `!task Заголовок | описание` / `!задача ...` — создать задачу
- `!tasks` / `!задачи` — показать последние задачи проекта
- `!open` / `!открыть` — дать ссылки на проект и доску
- `!my` / `!мои` — показать задачи, назначенные текущему пользователю
- `!comment 123 | текст` — добавить комментарий к задаче Taiga

`!my` работает в best-effort режиме: сначала смотрит `user_mappings` из `config.yaml`, затем пробует сопоставить Matrix user id и display name с `username/full_name/email` пользователя Taiga.

## Widget

Widget открывается по адресу `https://bridge.fishingteam.su/widget/taiga/{slug}` и в комнате живёт как state event типа `im.vector.modular.widgets`.

Теперь внутри панели:

- заголовок проекта и быстрые действия
- блок `Задачи проекта` с переключателями `Новые`, `В работе`, `Последние`
- компактная сводка и прокручиваемые колонки `По статусам`
- форма `Создать задачу`
- короткая русская инструкция
- скрытый блок `Техническая информация`

Два почти одинаковых списка больше не показываются одновременно. Основной рабочий срез теперь собран в одной секции.

## Быстрое подключение новой комнаты

Предпочтительный способ: запускать bind script внутри контейнера bridge.

### Создать новую проектную комнату

```bash
docker compose exec -T kaiten-matrix-bridge python tools/bind_room.py \
  --slug backend \
  --create-room \
  --project-id 123456 \
  --project-slug backend \
  --project-name "Backend" \
  --invite-user @owner:matrix.fishingteam.su
```

### Привязать уже существующую комнату

```bash
docker compose exec -T kaiten-matrix-bridge python tools/bind_room.py \
  --slug backend \
  --room-id '!AAAA:matrix.fishingteam.su' \
  --project-id 123456 \
  --project-slug backend \
  --project-name "Backend"
```

### Что делает `bind_room.py`

1. Проверяет и/или подтягивает данные проекта из Taiga.
2. Создаёт новую комнату или использует существующую.
3. Приглашает бота в комнату.
4. Записывает widget state и layout.
5. Публикует русскую шапку-инструкцию и закрепляет её.
6. Создаёт или обновляет webhook в Taiga.
7. Обновляет `config.yaml`.
8. Вызывает `POST /admin/reload-config` у bridge.
9. Печатает итоговый JSON со `slug`, `room_id`, `widget_url`, `webhook_url`.

### Важное ограничение для существующих комнат

Для bind уже существующей комнаты сервисный пользователь должен иметь доступ к комнате и право писать state events. Если бот сам не может этого сделать, задайте отдельного state/admin пользователя через `MATRIX_STATE_USER_ID` и `MATRIX_STATE_PASSWORD`.

## Русская шапка комнаты

Bind script публикует заметное сообщение с:

- кратким описанием комнаты
- подсказкой, где открыть widget
- командами `!task`, `!tasks`, `!open`, `!my`, `!comment`
- ссылками на проект и доску Taiga
- кратким описанием того, что делает бот

Последняя опубликованная шапка сохраняется в `header_event_id`, чтобы при повторном bind можно было закрепить именно актуальное сообщение.

## Конфигурация

### `.env`

Скопируйте `.env.example` в `.env` и заполните значения:

```env
TAIGA_BASE_URL=https://tree.taiga.io
TAIGA_API_URL=https://api.taiga.io/api/v1
TAIGA_USERNAME=
TAIGA_PASSWORD=
TAIGA_TOKEN=
TAIGA_ACCEPT_LANGUAGE=ru
TAIGA_PROJECT_ID=
TAIGA_PROJECT_SLUG=

MATRIX_HOMESERVER=https://matrix.fishingteam.su
MATRIX_USER_ID=@kbot:matrix.fishingteam.su
MATRIX_PASSWORD=
MATRIX_STATE_USER_ID=
MATRIX_STATE_PASSWORD=

BRIDGE_PUBLIC_URL=https://bridge.fishingteam.su
BRIDGE_SECRET=
LOG_LEVEL=INFO
CONFIG_PATH=/app/config.yaml
DATA_DIR=/app/data
WIDGET_FRAME_ANCESTORS=https://fishingteam.su https://matrix.fishingteam.su
```

Пояснения:

- `MATRIX_STATE_*` необязательны; если они не заданы, bind flow будет работать от имени бота
- `BRIDGE_PUBLIC_URL` нужен для генерации `widget_url` и `webhook_url`
- `TAIGA_ACCEPT_LANGUAGE=ru` просит Taiga API возвращать переводимые части по-русски

### `config.yaml`

Пример:

```yaml
projects:
  alpha:
    room_id: "!ROOM:matrix.fishingteam.su"
    project_id: 1784454
    project_slug: denbay0-test
    project_name: Demo project
    project_url: https://tree.taiga.io/project/denbay0-test
    widget_id: taiga-alpha-widget
    widget_name: Доска Taiga
    widget_url: https://bridge.fishingteam.su/widget/taiga/alpha
    webhook_url: https://bridge.fishingteam.su/webhook/taiga/alpha
    header_event_id: "$event:matrix.fishingteam.su"
    user_mappings:
      "@denis:matrix.fishingteam.su": "Denbay0"
    webhook_secret: replace-with-project-secret
```

Поля:

- `room_id` — Matrix-комната проекта
- `project_id`, `project_slug`, `project_name`, `project_url` — данные Taiga-проекта
- `widget_id`, `widget_name`, `widget_url` — room widget
- `webhook_url`, `webhook_secret` — входящий webhook bridge
- `header_event_id` — последнее заметное room-message header notice
- `user_mappings` — явное сопоставление Matrix user id к Taiga username/email

## HTTP API

- `GET /healthz` — статус bridge
- `POST /webhook/taiga/{slug}` — основной webhook endpoint
- `POST /webhook/kaiten/{slug}` — совместимость со старым URL
- `GET /widget/taiga/{slug}` — HTML widget page
- `POST /widget/taiga/{slug}/task` — создание задачи из widget
- `POST /admin/reload-config` — внутренний reload `config.yaml` по `X-Bridge-Secret`

## MatrixRTC check

Для быстрой диагностики MatrixRTC есть утилита `tools/check_matrixrtc.py`. Она помогает отделить server-side проблему от stale mobile client config.

Что проверяет:

- `/.well-known/matrix/client`
- `/.well-known/element/element.json`
- `/_matrix/client/unstable/org.matrix.msc4143/rtc/transports` без токена
- тот же endpoint с токеном после Matrix login
- совпадение `livekit_service_url` между `.well-known` и `rtc_transports`
- доступность `call.widget_url` и `call.fishingteam.su/config.json`
- `element_call.use_exclusively`, если дать путь к `config.json`
- health-check для LiveKit JWT и SFU

Пример:

```bash
python tools/check_matrixrtc.py \
  --homeserver https://matrix.fishingteam.su \
  --client-domain matrix.fishingteam.su \
  --user alice \
  --password secret \
  --call-url https://call.fishingteam.su \
  --element-config /opt/matrix-stack/element/config.json \
  --jwt-health-url https://rtc.fishingteam.su/livekit/jwt/healthz \
  --sfu-url https://sfu.fishingteam.su
```

Ожидаемый healthy baseline:

- `.well-known` отвечает `200`
- `/.well-known/element/element.json` отвечает `200`
- `rtc/transports` без токена отвечает `401 M_MISSING_TOKEN`
- `rtc/transports` с токеном отвечает `200`
- `call.widget_url` указывает на живой `Element Call` frontend
- `livekit_service_url` в `.well-known` и transport payload совпадает

## Локальный запуск

```bash
cp .env.example .env
cp config.example.yaml config.yaml
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:create_app --factory --host 0.0.0.0 --port 8000
```

## Docker / deploy

```bash
docker compose up -d --build
```

`compose.yml` монтирует `config.yaml` в контейнер на запись, чтобы bind script мог обновлять mapping прямо на сервере.

## Smoke check

### Проверить, что сервис жив

```bash
curl https://bridge.fishingteam.su/healthz
curl -I https://bridge.fishingteam.su/widget/taiga/alpha
```

### Проверить текущую комнату

1. Открыть room widget.
2. Выполнить `!help`.
3. Выполнить `!task Заголовок | описание`.
4. Выполнить `!tasks`.
5. Выполнить `!open`.
6. Выполнить `!comment 123 | текст`.
7. Убедиться, что webhook возвращает событие в комнату.

### Проверить новую тестовую комнату

1. Запустить `tools/bind_room.py`.
2. Убедиться, что bot приглашён.
3. Проверить, что widget появился.
4. Проверить, что шапка опубликована и закреплена.
5. Выполнить те же команды в новой комнате.
