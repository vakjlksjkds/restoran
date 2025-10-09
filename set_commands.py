#!/usr/bin/env python3
"""
Утилита для регистрации команд бота в BotFather
"""

import os
import requests
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "8245055843:AAEpOGcGRbvy1TkfQx4Jj2rAqQB15CbxQp0")

def set_bot_commands():
    """Установка команд бота"""
    
    commands = [
        {
            "command": "start",
            "description": "Приветствие и инструкции"
        },
        {
            "command": "random", 
            "description": "Выбрать случайный ресторан"
        },
        {
            "command": "stats",
            "description": "Статистика посещений и отзывов"
        },
        {
            "command": "next_event",
            "description": "Ближайшее запланированное событие"
        },
        {
            "command": "cancel_event",
            "description": "Отменить событие (только админ)"
        },
        {
            "command": "clear_reviews",
            "description": "Очистить все отзывы (только админ)"
        }
    ]
    
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/setMyCommands"
    
    try:
        response = requests.post(url, json={"commands": commands})
        
        if response.status_code == 200:
            print("✅ Команды успешно зарегистрированы!")
            print("📱 Теперь команды будут отображаться при вводе / в чате")
        else:
            print(f"❌ Ошибка: {response.status_code}")
            print(f"Ответ: {response.text}")
            
    except Exception as e:
        print(f"❌ Ошибка при регистрации команд: {e}")

if __name__ == "__main__":
    print("🤖 Регистрация команд бота...")
    set_bot_commands()
