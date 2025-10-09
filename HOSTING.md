# 🚀 Инструкции по хостингу Restaurant Bot

## 📋 Варианты развертывания

### 1. 🐳 Docker (Рекомендуется)

#### Быстрый старт:
```bash
# Клонируйте репозиторий
git clone <your-repo-url>
cd restaurant-bot

# Создайте .env файл
cp .env.example .env
# Отредактируйте .env с вашими данными

# Запустите бота
docker-compose up -d
```

#### Управление:
```bash
# Просмотр логов
docker-compose logs -f

# Остановка
docker-compose down

# Перезапуск
docker-compose restart

# Обновление
docker-compose pull && docker-compose up -d
```

### 2. ⚙️ Systemd (Linux сервер)

#### Установка:
```bash
# Запустите скрипт развертывания
sudo ./deploy.sh systemd
```

#### Управление:
```bash
# Статус сервиса
sudo systemctl status restaurant-bot

# Запуск/остановка
sudo systemctl start restaurant-bot
sudo systemctl stop restaurant-bot

# Просмотр логов
sudo journalctl -u restaurant-bot -f

# Автозапуск
sudo systemctl enable restaurant-bot
```

### 3. 🐍 Прямой запуск Python

#### Установка:
```bash
# Создайте виртуальное окружение
python3 -m venv venv
source venv/bin/activate

# Установите зависимости
pip install -r requirements.txt

# Создайте .env файл
cp .env.example .env
# Отредактируйте .env

# Запустите бота
python perfect_bot.py
```

## 🔧 Настройка переменных окружения

Создайте файл `.env` в корне проекта:

```env
# Токен бота от @BotFather
BOT_TOKEN=your_bot_token_here

# ID администратора (ваш Telegram ID)
ADMIN_USER_ID=your_telegram_id

# ID группы (где будет работать бот)
GROUP_CHAT_ID=your_group_chat_id
```

### Как получить ID:

1. **BOT_TOKEN**: Создайте бота через @BotFather
2. **ADMIN_USER_ID**: Напишите @userinfobot
3. **GROUP_CHAT_ID**: 
   - Добавьте бота в группу
   - Напишите в группе любое сообщение
   - Перейдите по ссылке: `https://api.telegram.org/bot<BOT_TOKEN>/getUpdates`
   - Найдите `chat.id` в ответе

## 📊 Мониторинг

### Docker:
```bash
# Статистика контейнера
docker stats restaurant-bot

# Логи в реальном времени
docker-compose logs -f restaurant-bot
```

### Systemd:
```bash
# Статус сервиса
systemctl status restaurant-bot

# Логи
journalctl -u restaurant-bot --since "1 hour ago"
```

## 🔄 Обновление

### Docker:
```bash
git pull
docker-compose build
docker-compose up -d
```

### Systemd:
```bash
git pull
sudo systemctl stop restaurant-bot
sudo systemctl start restaurant-bot
```

## 🛡️ Безопасность

1. **Никогда не коммитьте .env файл**
2. **Используйте отдельного пользователя для бота**
3. **Настройте файрвол**
4. **Регулярно обновляйте зависимости**

## 📝 Логирование

Логи сохраняются в:
- **Docker**: `docker-compose logs`
- **Systemd**: `journalctl -u restaurant-bot`
- **Прямой запуск**: консоль

## 🆘 Устранение неполадок

### Бот не отвечает:
1. Проверьте токен в .env
2. Убедитесь, что бот добавлен в группу
3. Проверьте логи на ошибки

### Ошибки базы данных:
1. Убедитесь, что файл `restaurant_bot.db` доступен для записи
2. Проверьте права доступа к файлу

### Проблемы с уведомлениями:
1. Проверьте, что все ID корректны
2. Убедитесь, что бот имеет права администратора в группе

## 📞 Поддержка

При возникновении проблем:
1. Проверьте логи
2. Убедитесь в корректности настроек
3. Проверьте статус сервиса
