cltkf# Telegram-бот для выбора ресторанов в группе

Функции: импорт ресторанов (JSON/CSV), случайный выбор с карточкой и кнопкой «Я иду!», установка напоминания `/set_reminder DD.MM.YYYY HH:MM`, сбор отзывов (ответом на сообщение), статистика `/stats`. Данные хранятся в SQLite (`bot.db`).

## Локальный запуск

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export BOT_TOKEN="<ТОКЕН_БОТА>"
python main.py
```

По умолчанию включён long polling. Для webhook добавьте `WEBHOOK_BASE_URL` и, при необходимости, `WEBHOOK_PATH` и `WEBHOOK_SECRET`.

## Переменные окружения
- `BOT_TOKEN` — токен из BotFather
- `WEBHOOK_BASE_URL` — публичный HTTPS URL приложения (если задан — используется webhook)
- `WEBHOOK_PATH` — путь вебхука (по умолчанию `/webhook`)
- `WEBHOOK_SECRET` — секрет, добавляется в конец пути
- `TIMEZONE` — таймзона для локального времени (по умолчанию `Europe/Moscow`)
- `DB_PATH` — путь к SQLite базе (по умолчанию `./bot.db`)

## Импорт ресторанов
- Автоматический импорт из `restaurants.json` при первом старте (если БД пуста)
- В чате администратор может отправить файл `.json` или `.csv` — бот импортирует

JSON формат:
```json
{"restaurants": [{"id": 1, "name": "Название", "address": "Адрес", "cuisine": "Тип кухни", "description": "Описание"}]}
```

CSV заголовки: `name,address,cuisine,description,average_check`

## Бесплатный деплой

### Calingo (контейнерный запуск)
1. Подготовьте репозиторий с файлами проекта (есть `Dockerfile`).
2. В панели Calingo создайте новое приложение (Docker/Container), укажите репозиторий.
3. Переменные окружения:
   - `BOT_TOKEN` — токен вашего бота;
   - `TIMEZONE=Europe/Moscow` (или ваша);
   - `WEBHOOK_SECRET=tg` (по желанию);
   - `DB_PATH=/app/data/bot.db` (сохранение SQLite).
4. Том хранения (Persistent Volume): примонтируйте к `/app/data`.
5. Порт приложения: 8080. После деплоя Calingo выдаст HTTPS‑домен — бот автоматически настроит webhook на этот домен.
6. Добавьте бота в группу и проверьте команды.

### Render (free web service)
1. Создайте репозиторий, загрузите файлы.
2. На `render.com` создайте Web Service:
   - Build: `pip install -r requirements.txt`
   - Start: `python main.py`
   - Env vars: `BOT_TOKEN`, `WEBHOOK_BASE_URL` (URL Render), `TIMEZONE`.
3. После деплоя Render выдаст URL — он попадёт в `WEBHOOK_BASE_URL`.

### PythonAnywhere (always-on для веб-приложений)
1. Загрузите код, создайте виртуальное окружение, установите зависимости.
2. Создайте Web app (Flask не требуется отдельно — скрипт запускает собственный сервер).
3. Установите переменные окружения `BOT_TOKEN`, `WEBHOOK_BASE_URL` (ваш домен PA), `TIMEZONE`.

Если нет возможности настроить webhook, удалите `WEBHOOK_BASE_URL` — бот запустится в режиме long polling (требует фоновый процесс).

## Команды
- `/random_restaurant` — вывод карточки ресторана с кнопкой «Я иду! ✅`
- `/set_reminder DD.MM.YYYY HH:MM` — устанавливает время для текущего выбранного ресторана
- `/stats` — сводка по посещённым и предстоящим

## Безопасность
Не храните токен в исходниках. Используйте переменные окружения.

## Статистика `/stats`

- По умолчанию демо-данные уже содержат один посещённый ресторан с тремя отзывами, чтобы увидеть формат вывода.
- Остальные записи в списке (27+ по умолчанию) доступны для следующих походов.