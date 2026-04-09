# Taiga Matrix Bridge

Русскоязычный bridge между Matrix и Taiga для уже работающего self-hosted Matrix/Element стека. Серверный путь проекта сохранён как `/opt/kaiten-matrix-bridge` ради совместимости, но сервис уже полностью работает с Taiga и room widget.

## Что уже работает

- webhook из Taiga пишет уведомления в Matrix-комнату
- бот в комнате понимает `!help` и `!task Заголовок | описание`
- задачи создаются в Taiga как `user story`
- в комнате встроен self-hosted widget с русским интерфейсом

## Боевой контур

- Element Web: `https://fishingteam.su`
- Matrix homeserver: `https://matrix.fishingteam.su`
- Health check bridge: `https://bridge.fishingteam.su/healthz`
- Widget page: `https://bridge.fishingteam.su/widget/taiga/alpha`
- Полная доска Taiga: `https://tree.taiga.io/project/denbay0-test/kanban`
- Комната Matrix: `!EQxiFrVAIdKTSLtAJD:matrix.fishingteam.su`
- Серверный путь: `/opt/kaiten-matrix-bridge`

## Почему внутри комнаты не встроена сама cloud-доска Taiga

Taiga Cloud запрещает прямое iframe-встраивание страницы доски:

- URL: `https://tree.taiga.io/project/denbay0-test/kanban`
- blocker: `X-Frame-Options: DENY`

Поэтому bridge использует self-hosted widget page на нашем домене и не пытается обходить защитные заголовки Taiga Cloud.

## Widget в комнате

- URL виджета: `https://bridge.fishingteam.su/widget/taiga/alpha`
- Widget id: `taiga-alpha-widget`
- Event type виджета: `im.vector.modular.widgets`
- Layout event type: `io.element.widgets.layout`
- Текущее имя в room state: `Taiga Board`

Виджет показывает:

- название и статус проекта
- кнопку открытия полной доски Taiga
- список последних задач
- сводку по статусам
- форму быстрого создания задачи
- подсказки, как открыть виджет и как вернуться обратно к чату

## Как открыть виджет в Matrix

Открой комнату проекта и найди виджет `Taiga Board` в панели виджетов/приложений комнаты. В зависимости от версии Element он может быть закреплён сверху или открываться через информацию о комнате.

Если виджет не виден:

1. Открой комнату `!EQxiFrVAIdKTSLtAJD:matrix.fishingteam.su`.
2. Открой информацию о комнате или секцию widgets/apps.
3. Выбери `Taiga Board`.

## Как вернуться к чату

Точное название кнопки зависит от версии Element, но логика одна и та же:

1. Сверни или закрой панель виджета.
2. Либо просто переключись обратно на сообщения комнаты.

Сам widget тоже показывает эти подсказки прямо внутри интерфейса.

## Полезные действия

- открыть полную доску: кнопка `Открыть доску`
- создать задачу из виджета: форма `Создать задачу`
- создать задачу из чата: `!task Заголовок | описание`
- проверить связь с Taiga: создать или изменить user story и дождаться webhook-уведомления в комнате

## Язык интерфейса

Что русифицировано нами:

- сам widget UI
- кнопки, формы, статусы, пустые состояния и ошибки
- тексты help/UX внутри страницы виджета
- обращения bridge к Taiga API через `Accept-Language: ru`

Что не управляется сервером:

- язык самого клиента Element задаётся пользователем в `All Settings -> Account -> Language and Region`
- текущее имя room widget пока остаётся `Taiga Board`, потому что power policy комнаты требует уровень `50` для state-событий, а локальному техпользователю Synapse смог дать только `0`

## HTTP API

### `GET /healthz`

Возвращает JSON-статус сервиса. `HEAD /healthz` тоже поддерживается.

### `POST /webhook/taiga/{slug}`

Основной режим авторизации webhook из Taiga:

- заголовок `X-TAIGA-WEBHOOK-SIGNATURE`
- значение `hex(hmac_sha1(raw_body, BRIDGE_SECRET))`

Ручные fallback-варианты для тестов:

- query `?secret=...`
- либо заголовок `X-Bridge-Secret: ...`

Совместимость со старым URL сохранена:

- `POST /webhook/kaiten/{slug}`

### `GET /widget/taiga/{slug}`

Отдаёт self-hosted HTML widget page, пригодную для встраивания в Element.

### `POST /widget/taiga/{slug}/task`

Создаёт Taiga user story из формы виджета.

Пример JSON:

```json
{
  "title": "Тестовая задача",
  "description": "Описание"
}
```

## Команды бота

### `!help`

Показывает список доступных команд.

### `!task Заголовок | описание`

Создаёт user story в привязанном проекте Taiga и отвечает ссылкой в ту же комнату.

## Конфигурация

Скопируй `.env.example` в `.env` и заполни реальные значения:

```env
TAIGA_BASE_URL=https://tree.taiga.io
TAIGA_API_URL=https://api.taiga.io/api/v1
TAIGA_USERNAME=
TAIGA_PASSWORD=
TAIGA_TOKEN=
TAIGA_ACCEPT_LANGUAGE=ru
TAIGA_PROJECT_ID=1784454
TAIGA_PROJECT_SLUG=denbay0-test

MATRIX_HOMESERVER=https://matrix.fishingteam.su
MATRIX_USER_ID=@kbot:matrix.fishingteam.su
MATRIX_PASSWORD=

BRIDGE_SECRET=
LOG_LEVEL=INFO
CONFIG_PATH=/app/config.yaml
DATA_DIR=/app/data
WIDGET_FRAME_ANCESTORS=https://fishingteam.su https://matrix.fishingteam.su
```

Замечания:

- `TAIGA_TOKEN` необязателен
- если `TAIGA_TOKEN` пустой, bridge логинится через `TAIGA_USERNAME` и `TAIGA_PASSWORD`
- `TAIGA_ACCEPT_LANGUAGE=ru` просит Taiga API отдавать переводимые части ответа по-русски
- `WIDGET_FRAME_ANCESTORS` ограничивает, кто может встраивать widget page

## `config.yaml`

Скопируй `config.example.yaml` в `config.yaml` и привяжи комнату к проекту:

```yaml
projects:
  alpha:
    room_id: "!EQxiFrVAIdKTSLtAJD:matrix.fishingteam.su"
    project_id: 1784454
    project_slug: denbay0-test
```

Поля:

- `room_id`: комната Matrix для бота и webhook-уведомлений
- `project_id`: numeric id проекта Taiga
- `project_slug`: slug проекта для ссылок и widget page
- `webhook_secret`: необязательный секрет только для этого slug

## Локальный запуск

```bash
cp .env.example .env
cp config.example.yaml config.yaml
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:create_app --factory --host 0.0.0.0 --port 8000
```

## Деплой на сервер

```bash
cd /opt/kaiten-matrix-bridge
docker compose up -d --build
```

Если на сервере снова будут проблемы с pull базового образа, можно использовать уже проверенный fallback:

```bash
cd /opt/kaiten-matrix-bridge
docker build -f Dockerfile.localbase -t kaiten-matrix-bridge-kaiten-matrix-bridge:latest .
docker compose up -d --force-recreate
```

## Операционные команды

### Запуск / пересборка

```bash
cd /opt/kaiten-matrix-bridge
docker compose up -d --build
```

### Логи

```bash
cd /opt/kaiten-matrix-bridge
docker compose logs -f
```

### Перезапуск

```bash
cd /opt/kaiten-matrix-bridge
docker compose restart
```

### Остановка

```bash
cd /opt/kaiten-matrix-bridge
docker compose down
```

## Как получить auth и project id в Taiga

### Получить auth token

```bash
curl -X POST https://api.taiga.io/api/v1/auth \
  -H "Content-Type: application/json" \
  -d '{
    "type": "normal",
    "username": "YOUR_USERNAME",
    "password": "YOUR_PASSWORD"
  }'
```

### Узнать project id по slug

```bash
curl "https://api.taiga.io/api/v1/resolver?project=YOUR_PROJECT_SLUG"
```

Пример ответа:

```json
{"project": 1784454}
```

## Как настроить webhook в Taiga

Используй URL:

```text
https://bridge.fishingteam.su/webhook/taiga/alpha
```

В поле `key` в Taiga укажи то же значение, что и `BRIDGE_SECRET` в `.env` bridge.

## Smoke test

### Health

```bash
curl https://bridge.fishingteam.su/healthz
curl -I https://bridge.fishingteam.su/widget/taiga/alpha
```

### Проверка в Matrix

В комнате отправь:

```text
!help
!task Тестовая задача | проверить bridge
```

### Проверка widget

Открой:

```text
https://bridge.fishingteam.su/widget/taiga/alpha
```

Затем создай задачу через форму.

### Проверка webhook

Создай или измени user story в проекте Taiga и убедись, что в комнате приходит уведомление `[Taiga] ...`.
