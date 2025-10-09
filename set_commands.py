#!/usr/bin/env python3
"""
Script to set bot commands in Telegram
Run this script to register all bot commands with BotFather
"""

import requests
import json

# Bot token
BOT_TOKEN = "8245055843:AAEpOGcGRbvy1TkfQx4Jj2rAqQB15CbxQp0"

# Commands to register
commands = [
    {
        "command": "start",
        "description": "🚀 Запустить бота и получить помощь"
    },
    {
        "command": "random", 
        "description": "🎲 Выбрать случайный ресторан"
    },
    {
        "command": "stats",
        "description": "📊 Статистика по ресторанам"
    },
    {
        "command": "cancel_event",
        "description": "❌ Отменить событие (только админ)"
    },
    {
        "command": "clear_reviews",
        "description": "🗑️ Удалить все отзывы (только админ)"
    },
    {
        "command": "next_event",
        "description": "📅 Проверить ближайшее событие"
    }
]

def set_bot_commands():
    """Set bot commands via Telegram API"""
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/setMyCommands"
    
    payload = {
        "commands": commands
    }
    
    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
        
        result = response.json()
        if result.get("ok"):
            print("✅ Команды бота успешно зарегистрированы!")
            print("\n📋 Зарегистрированные команды:")
            for cmd in commands:
                print(f"  /{cmd['command']} - {cmd['description']}")
            print("\n🎉 Теперь команды будут отображаться при вводе '/' в чате!")
        else:
            print(f"❌ Ошибка: {result.get('description', 'Неизвестная ошибка')}")
            
    except requests.exceptions.RequestException as e:
        print(f"❌ Ошибка сети: {e}")
    except Exception as e:
        print(f"❌ Ошибка: {e}")

if __name__ == "__main__":
    print("🤖 Регистрация команд бота...")
    set_bot_commands()
