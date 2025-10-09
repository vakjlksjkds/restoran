#!/usr/bin/env python3
"""
Simple Restaurant Bot - Working Version for Hosting
Based on working project structure
"""

import os
import asyncio
import logging
import json
import sqlite3
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from dotenv import load_dotenv

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, 
    CommandHandler, 
    CallbackQueryHandler, 
    MessageHandler, 
    filters, 
    ContextTypes
)

# Загружаем переменные окружения
load_dotenv()

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Константы
BOT_TOKEN = os.getenv("BOT_TOKEN", "8245055843:AAEpOGcGRbvy1TkfQx4Jj2rAqQB15CbxQp0")
ADMIN_USER_ID = int(os.getenv("ADMIN_USER_ID", "800133246"))
GROUP_CHAT_ID = os.getenv("GROUP_CHAT_ID", "")
REQUIRED_CONFIRMATIONS = 3  # 3 человека + бот = 4 участника в группе

class SimpleRestaurantBot:
    def __init__(self):
        self.db_path = "restaurant_bot.db"
        self.restaurants = []
        self.init_database()
        self.load_restaurants()
        
    def init_database(self):
        """Инициализация базы данных"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Создаем таблицы
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS restaurants (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                address TEXT,
                cuisine TEXT,
                description TEXT,
                average_check TEXT
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                restaurant_name TEXT NOT NULL,
                datetime TEXT,
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS confirmations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                username TEXT,
                confirmed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (event_id) REFERENCES events (id)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS reviews (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                username TEXT,
                rating INTEGER NOT NULL,
                comment TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (event_id) REFERENCES events (id)
            )
        ''')
        
        conn.commit()
        conn.close()
        logger.info("✅ Database initialized")
        
    def load_restaurants(self):
        """Загрузка ресторанов из JSON"""
        try:
            with open('restaurants.json', 'r', encoding='utf-8') as f:
                data = json.load(f)
                
            # Обрабатываем разные форматы JSON
            if isinstance(data, list):
                self.restaurants = data
            elif isinstance(data, dict) and 'restaurants' in data:
                self.restaurants = data['restaurants']
            else:
                self.restaurants = []
                
            logger.info(f"✅ Loaded {len(self.restaurants)} restaurants")
        except Exception as e:
            logger.error(f"❌ Error loading restaurants: {e}")
            self.restaurants = []
            
    def get_active_event(self, chat_id: int) -> Optional[Dict]:
        """Получить активное событие"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT * FROM events 
            WHERE chat_id = ? AND status IN ('pending', 'scheduled', 'review_requested')
            ORDER BY created_at DESC LIMIT 1
        ''', (chat_id,))
        
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return {
                'id': row[0],
                'chat_id': row[1],
                'restaurant_name': row[2],
                'datetime': row[3],
                'status': row[4],
                'created_at': row[5]
            }
        return None
        
    def is_admin(self, user_id: int) -> bool:
        """Проверка, является ли пользователь админом"""
        return user_id == ADMIN_USER_ID

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /start"""
        welcome_text = """
🍽️ **Добро пожаловать в Perfect Restaurant Bot!**

Этот бот поможет вашей группе из 3 человек выбирать рестораны для совместных походов.

**Доступные команды:**
/random - Выбрать случайный ресторан
/stats - Статистика посещений
/next_event - Ближайшее событие
/cancel_event - Отменить событие (только админ)
/clear_reviews - Очистить отзывы (только админ)

**Как это работает:**
1. Используйте /random для выбора ресторана
2. Все 3 участника должны подтвердить участие
3. Выберите дату и время
4. Получите детали бронирования
5. Оставьте отзыв после посещения

Приятного аппетита! 🍴
        """
        await update.message.reply_text(welcome_text, parse_mode='Markdown')

    async def random_restaurant(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /random"""
        chat_id = update.effective_chat.id
        
        # Проверяем, есть ли активное событие
        active_event = self.get_active_event(chat_id)
        if active_event:
            keyboard = [
                [InlineKeyboardButton("❌ Отменить событие", callback_data=f"cancel_event_{active_event['id']}")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                f"⚠️ У вас уже есть активное событие:\n"
                f"🍽️ **{active_event['restaurant_name']}**\n"
                f"📅 Статус: {active_event['status']}\n\n"
                f"Сначала завершите или отмените текущее событие.",
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
            return
            
        if not self.restaurants:
            await update.message.reply_text("❌ Рестораны не загружены. Обратитесь к администратору.")
            return
            
        # Выбираем случайный ресторан
        import random
        restaurant = random.choice(self.restaurants)
        
        # Создаем событие
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO events (chat_id, restaurant_name, status)
            VALUES (?, ?, 'pending')
        ''', (chat_id, restaurant['name']))
        
        event_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        # Формируем карточку ресторана
        card_text = f"""
🍽️ **{restaurant['name']}**

📍 **Адрес:** {restaurant.get('address', 'Не указан')}
🍴 **Кухня:** {restaurant.get('cuisine', 'Не указана')}
💰 **Средний чек:** {restaurant.get('average_check', 'Не указан')}
📝 **Описание:** {restaurant.get('description', 'Нет описания')}

👥 **Подтверждения:** 0/{REQUIRED_CONFIRMATIONS}
        """
        
        keyboard = [
            [InlineKeyboardButton("✅ Я иду!", callback_data=f"confirm_{event_id}")],
            [InlineKeyboardButton("❌ Отменить событие", callback_data=f"cancel_event_{event_id}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            card_text, 
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )

    async def confirm_attendance(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка подтверждения участия"""
        query = update.callback_query
        await query.answer()
        
        event_id = int(query.data.split('_')[1])
        user_id = query.from_user.id
        username = query.from_user.username or query.from_user.first_name
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Проверяем, не подтверждал ли уже пользователь
        cursor.execute('''
            SELECT id FROM confirmations 
            WHERE event_id = ? AND user_id = ?
        ''', (event_id, user_id))
        
        if cursor.fetchone():
            await query.edit_message_text(
                "✅ Вы уже подтвердили участие в этом событии!"
            )
            conn.close()
            return
            
        # Добавляем подтверждение
        cursor.execute('''
            INSERT INTO confirmations (event_id, user_id, username)
            VALUES (?, ?, ?)
        ''', (event_id, user_id, username))
        
        # Считаем подтверждения
        cursor.execute('''
            SELECT COUNT(*) FROM confirmations WHERE event_id = ?
        ''', (event_id,))
        
        confirmations_count = cursor.fetchone()[0]
        
        # Получаем информацию о ресторане
        cursor.execute('''
            SELECT restaurant_name FROM events WHERE id = ?
        ''', (event_id,))
        
        restaurant_name = cursor.fetchone()[0]
        
        conn.commit()
        conn.close()
        
        # Обновляем сообщение
        card_text = f"""
🍽️ **{restaurant_name}**

👥 **Подтверждения:** {confirmations_count}/{REQUIRED_CONFIRMATIONS}

✅ **Участники:**
        """
        
        # Получаем список участников
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT username FROM confirmations WHERE event_id = ? ORDER BY confirmed_at
        ''', (event_id,))
        
        participants = [row[0] for row in cursor.fetchall()]
        conn.close()
        
        for i, participant in enumerate(participants, 1):
            card_text += f"\n{i}. {participant}"
            
        keyboard = [
            [InlineKeyboardButton("✅ Я иду!", callback_data=f"confirm_{event_id}")],
            [InlineKeyboardButton("❌ Отменить событие", callback_data=f"cancel_event_{event_id}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            card_text,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        
        # Если все подтвердили, запрашиваем дату и время
        if confirmations_count >= REQUIRED_CONFIRMATIONS:
            await query.message.reply_text(
                "🎉 Все участники подтвердили участие!\n\n"
                "📅 Пожалуйста, выберите дату и время в формате:\n"
                "**ДД.ММ.ГГГГ ЧЧ:ММ**\n\n"
                "Например: 15.12.2025 19:00"
            )
            
            # Обновляем статус события
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE events SET status = 'scheduled' WHERE id = ?
            ''', (event_id,))
            conn.commit()
            conn.close()

    async def cancel_event_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Отмена события"""
        query = update.callback_query
        await query.answer()
        
        event_id = int(query.data.split('_')[2])
        user_id = query.from_user.id
        
        # Проверяем права админа
        if not self.is_admin(user_id):
            await query.edit_message_text("❌ Только администратор может отменить событие.")
            return
            
        # Удаляем событие и связанные данные
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('DELETE FROM confirmations WHERE event_id = ?', (event_id,))
        cursor.execute('DELETE FROM reviews WHERE event_id = ?', (event_id,))
        cursor.execute('DELETE FROM events WHERE id = ?', (event_id,))
        
        conn.commit()
        conn.close()
        
        await query.edit_message_text("❌ Событие отменено.")

    async def stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /stats"""
        chat_id = update.effective_chat.id
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Общая статистика
        cursor.execute('SELECT COUNT(*) FROM restaurants')
        total_restaurants = cursor.fetchone()[0]
        
        cursor.execute('''
            SELECT COUNT(DISTINCT restaurant_name) FROM events 
            WHERE chat_id = ? AND status = 'completed'
        ''', (chat_id,))
        visited_restaurants = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM events WHERE chat_id = ?', (chat_id,))
        total_events = cursor.fetchone()[0]
        
        cursor.execute('''
            SELECT COUNT(*) FROM events 
            WHERE chat_id = ? AND status = 'completed'
        ''', (chat_id,))
        completed_events = cursor.fetchone()[0]
        
        # Процент посещенных ресторанов
        visited_percentage = (visited_restaurants / total_restaurants * 100) if total_restaurants > 0 else 0
        completed_percentage = (completed_events / total_events * 100) if total_events > 0 else 0
        
        stats_text = f"""
📊 **Статистика ресторанов**

🍽️ **Всего ресторанов:** {total_restaurants}
✅ **Посещено:** {visited_restaurants} ({visited_percentage:.1f}%)
📅 **Всего событий:** {total_events}
🎯 **Завершено:** {completed_events} ({completed_percentage:.1f}%)

📝 **Последние отзывы:**
        """
        
        # Последние отзывы
        cursor.execute('''
            SELECT r.restaurant_name, r.rating, r.comment, r.username, r.created_at
            FROM reviews r
            JOIN events e ON r.event_id = e.id
            WHERE e.chat_id = ?
            ORDER BY r.created_at DESC
            LIMIT 5
        ''', (chat_id,))
        
        reviews = cursor.fetchall()
        conn.close()
        
        if reviews:
            for review in reviews:
                restaurant_name, rating, comment, username, created_at = review
                stars = "⭐" * rating
                stats_text += f"\n🍽️ **{restaurant_name}** {stars}\n👤 {username}: {comment}\n"
        else:
            stats_text += "\nПока нет отзывов."
            
        await update.message.reply_text(stats_text, parse_mode='Markdown')

    async def next_event(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /next_event"""
        chat_id = update.effective_chat.id
        active_event = self.get_active_event(chat_id)
        
        if not active_event:
            await update.message.reply_text("📅 Нет запланированных событий.")
            return
            
        status_text = {
            'pending': '⏳ Ожидает подтверждений',
            'scheduled': '📅 Запланировано',
            'review_requested': '📝 Ожидает отзывов'
        }
        
        event_text = f"""
📅 **Ближайшее событие:**

🍽️ **Ресторан:** {active_event['restaurant_name']}
📊 **Статус:** {status_text.get(active_event['status'], active_event['status'])}
        """
        
        if active_event['datetime']:
            event_text += f"\n🕐 **Время:** {active_event['datetime']}"
            
        await update.message.reply_text(event_text, parse_mode='Markdown')

    async def cancel_event_admin(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /cancel_event (только админ)"""
        user_id = update.effective_user.id
        
        if not self.is_admin(user_id):
            await update.message.reply_text("❌ Только администратор может использовать эту команду.")
            return
            
        chat_id = update.effective_chat.id
        active_event = self.get_active_event(chat_id)
        
        if not active_event:
            await update.message.reply_text("📅 Нет активных событий для отмены.")
            return
            
        # Удаляем событие
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('DELETE FROM confirmations WHERE event_id = ?', (active_event['id'],))
        cursor.execute('DELETE FROM reviews WHERE event_id = ?', (active_event['id'],))
        cursor.execute('DELETE FROM events WHERE id = ?', (active_event['id'],))
        
        conn.commit()
        conn.close()
        
        await update.message.reply_text("❌ Событие отменено администратором.")

    async def clear_reviews_admin(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /clear_reviews (только админ)"""
        user_id = update.effective_user.id
        
        if not self.is_admin(user_id):
            await update.message.reply_text("❌ Только администратор может использовать эту команду.")
            return
            
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('DELETE FROM reviews')
        conn.commit()
        conn.close()
        
        await update.message.reply_text("🗑️ Все отзывы удалены.")

    async def handle_datetime_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка сообщений с датой и временем"""
        chat_id = update.effective_chat.id
        text = update.message.text.strip()
        
        # Проверяем, есть ли активное событие
        active_event = self.get_active_event(chat_id)
        if not active_event or active_event['status'] != 'scheduled':
            return
            
        # Простая проверка формата даты
        try:
            # Пытаемся распарсить дату
            datetime.strptime(text, "%d.%m.%Y %H:%M")
            
            # Обновляем событие
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE events SET datetime = ? WHERE id = ?
            ''', (text, active_event['id']))
            conn.commit()
            conn.close()
            
            await update.message.reply_text(
                f"✅ Время установлено: **{text}**\n\n"
                f"🍽️ **{active_event['restaurant_name']}**\n"
                f"📅 **Дата и время:** {text}\n\n"
                f"Приятного аппетита! 🍴",
                parse_mode='Markdown'
            )
            
        except ValueError:
            await update.message.reply_text(
                "❌ Неверный формат даты.\n"
                "Используйте формат: **ДД.ММ.ГГГГ ЧЧ:ММ**\n"
                "Например: 15.12.2025 19:00",
                parse_mode='Markdown'
            )

def main():
    """Запуск бота"""
    print("🍽️ Starting Simple Restaurant Bot...")
    
    bot = SimpleRestaurantBot()
    
    # Создаем приложение
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Добавляем обработчики
    application.add_handler(CommandHandler("start", bot.start))
    application.add_handler(CommandHandler("random", bot.random_restaurant))
    application.add_handler(CommandHandler("stats", bot.stats))
    application.add_handler(CommandHandler("next_event", bot.next_event))
    application.add_handler(CommandHandler("cancel_event", bot.cancel_event_admin))
    application.add_handler(CommandHandler("clear_reviews", bot.clear_reviews_admin))
    
    application.add_handler(CallbackQueryHandler(bot.confirm_attendance, pattern="^confirm_"))
    application.add_handler(CallbackQueryHandler(bot.cancel_event_callback, pattern="^cancel_event_"))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, bot.handle_datetime_message))
    
    print("🤖 Bot started successfully!")
    print("📱 Add bot to your group and use /start command")
    print("🛑 Press Ctrl+C to stop")
    
    # Запускаем бота
    try:
        application.run_polling()
    except KeyboardInterrupt:
        print("\n👋 Bot stopped by user")

if __name__ == "__main__":
    main()
