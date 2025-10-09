#!/bin/bash

# Скрипт развертывания Restaurant Bot
# Использование: ./deploy.sh [docker|systemd]

set -e

DEPLOYMENT_TYPE=${1:-docker}
PROJECT_DIR="/opt/restaurant-bot"
SERVICE_NAME="restaurant-bot"

echo "🚀 Развертывание Restaurant Bot..."

# Проверяем права root для systemd
if [ "$DEPLOYMENT_TYPE" = "systemd" ] && [ "$EUID" -ne 0 ]; then
    echo "❌ Для развертывания systemd нужны права root. Используйте sudo."
    exit 1
fi

# Создаем директорию проекта
echo "📁 Создание директории проекта..."
mkdir -p $PROJECT_DIR
cd $PROJECT_DIR

# Копируем файлы проекта
echo "📋 Копирование файлов..."
cp -r /path/to/your/project/* $PROJECT_DIR/

# Создаем пользователя bot
if [ "$DEPLOYMENT_TYPE" = "systemd" ]; then
    echo "👤 Создание пользователя bot..."
    useradd -r -s /bin/false bot || true
    chown -R bot:bot $PROJECT_DIR
fi

# Устанавливаем зависимости
echo "📦 Установка зависимостей..."
if [ "$DEPLOYMENT_TYPE" = "systemd" ]; then
    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
    chown -R bot:bot venv/
else
    # Для Docker
    echo "🐳 Сборка Docker образа..."
    docker-compose build
fi

# Настройка systemd
if [ "$DEPLOYMENT_TYPE" = "systemd" ]; then
    echo "⚙️ Настройка systemd..."
    cp systemd/restaurant-bot.service /etc/systemd/system/
    systemctl daemon-reload
    systemctl enable $SERVICE_NAME
    systemctl start $SERVICE_NAME
    
    echo "✅ Сервис запущен!"
    echo "📊 Статус: systemctl status $SERVICE_NAME"
    echo "📝 Логи: journalctl -u $SERVICE_NAME -f"
fi

# Настройка Docker
if [ "$DEPLOYMENT_TYPE" = "docker" ]; then
    echo "🐳 Запуск Docker контейнера..."
    docker-compose up -d
    
    echo "✅ Контейнер запущен!"
    echo "📊 Статус: docker-compose ps"
    echo "📝 Логи: docker-compose logs -f"
fi

echo "🎉 Развертывание завершено!"
echo "📖 Проверьте README.md для дополнительной информации"
