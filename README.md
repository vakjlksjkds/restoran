# 🍽️ Perfect Restaurant Bot

Telegram бот для выбора ресторанов в группе из 3 человек.

## 🚀 Функции

- **Случайный выбор ресторана** из базы 26 ресторанов
- **Подтверждение участия** всех 3 участников
- **Планирование даты и времени** встречи
- **Автоматические уведомления** за 5 дней и в день события
- **Система отзывов** после посещения
- **Статистика посещений** и отзывов
- **Админские команды** для управления

## 📋 Команды

- `/start` - Приветствие и инструкции
- `/random` - Выбрать случайный ресторан
- `/stats` - Статистика посещений
- `/next_event` - Ближайшее событие
- `/cancel_event` - Отменить событие (админ)
- `/clear_reviews` - Очистить отзывы (админ)

## 🛠️ Установка

### Локальная разработка

1. **Клонируйте репозиторий:**
   ```bash
   git clone https://github.com/vakjlksjkds/restoran.git
   cd restoran
   ```

2. **Создайте виртуальное окружение:**
   ```bash
   python -m venv venv
   source venv/bin/activate  # Linux/Mac
   # или
   venv\Scripts\activate     # Windows
   ```

3. **Установите зависимости:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Создайте файл .env:**
   ```env
   BOT_TOKEN=your_bot_token_here
   ADMIN_USER_ID=your_admin_user_id
   GROUP_CHAT_ID=your_group_chat_id
   ```

5. **Запустите бота:**
   ```bash
   python simple_bot.py
   ```

### Развертывание на сервере

#### Docker

1. **Соберите образ:**
   ```bash
   docker build -t restaurant-bot .
   ```

2. **Запустите контейнер:**
   ```bash
   docker run -d \
     --name restaurant-bot \
     -e BOT_TOKEN=your_bot_token \
     -e ADMIN_USER_ID=your_admin_id \
     -e GROUP_CHAT_ID=your_group_id \
     restaurant-bot
   ```

#### Docker Compose

```yaml
version: '3.8'
services:
  bot:
    build: .
    environment:
      - BOT_TOKEN=your_bot_token
      - ADMIN_USER_ID=your_admin_id
      - GROUP_CHAT_ID=your_group_id
    restart: unless-stopped
```

## 📁 Структура проекта

```
├── simple_bot.py          # Основной файл бота
├── restaurants.json       # База ресторанов (26 ресторанов)
├── requirements.txt       # Зависимости Python
├── Dockerfile            # Docker конфигурация
├── README.md             # Документация
├── set_commands.py       # Утилита для регистрации команд
└── .gitignore            # Игнорируемые файлы
```

## 🔧 Настройка

### Получение Bot Token

1. Найдите [@BotFather](https://t.me/botfather) в Telegram
2. Отправьте `/newbot`
3. Следуйте инструкциям
4. Скопируйте полученный токен

### Получение Chat ID

1. Добавьте бота в группу
2. Отправьте любое сообщение
3. Перейдите по ссылке: `https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates`
4. Найдите `chat.id` в ответе

### Регистрация команд

```bash
python set_commands.py
```

## 📊 База данных

Бот использует SQLite для хранения:
- События и их статусы
- Подтверждения участия
- Отзывы пользователей
- Статистика посещений

## 🔔 Система уведомлений

- **За 5 дней** до события
- **Утром** в день события (9:00)
- **Вечером** в день события (18:00)
- **Запрос отзыва** через 3 часа после события

## 🐛 Отладка

Логи сохраняются в консоль. Для отладки:

```bash
python simple_bot.py
```

## 📝 Лицензия

MIT License

## 🤝 Поддержка

При возникновении проблем создайте issue в репозитории.
