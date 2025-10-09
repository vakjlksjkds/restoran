#!/usr/bin/env python3
"""
Perfect Restaurant Bot - Final Working Version
"""

import asyncio
import logging
import json
import sqlite3
import random
import os
from datetime import datetime
from pathlib import Path

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from telegram.constants import ParseMode
from dotenv import load_dotenv

from notifications import NotificationSystem

# Загружаем переменные окружения
load_dotenv()

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Configuration
BOT_TOKEN = os.getenv("BOT_TOKEN", "8245055843:AAEpOGcGRbvy1TkfQx4Jj2rAqQB15CbxQp0")
REQUIRED_CONFIRMATIONS = 3  # 3 человека + бот = 4 участника в группе
ADMIN_USER_ID = int(os.getenv("ADMIN_USER_ID", "800133246"))  # ID администратора
GROUP_CHAT_ID = int(os.getenv("GROUP_CHAT_ID", "-1001234567890"))  # ID группы

class PerfectRestaurantBot:
    def __init__(self):
        self.db_path = "restaurant_bot.db"
        self.restaurants = []
        self.init_database()
        self.load_restaurants()
        self.notification_system = None
        self.application = None
    
    def init_database(self):
        """Initialize database with correct schema"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Drop existing tables to ensure clean start
            cursor.execute('DROP TABLE IF EXISTS reviews')
            cursor.execute('DROP TABLE IF EXISTS confirmations')
            cursor.execute('DROP TABLE IF EXISTS events')
            cursor.execute('DROP TABLE IF EXISTS restaurants')
            
            # Restaurants table
            cursor.execute('''
                CREATE TABLE restaurants (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    description TEXT,
                    address TEXT,
                    phone TEXT,
                    rating REAL,
                    cuisine_type TEXT,
                    price_range TEXT,
                    data TEXT
                )
            ''')
            
            # Events table
            cursor.execute('''
                CREATE TABLE events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    restaurant_name TEXT NOT NULL,
                    restaurant_data TEXT NOT NULL,
                    status TEXT DEFAULT 'pending',
                    datetime TEXT,
                    created_at TEXT NOT NULL
                )
            ''')
            
            # Confirmations table
            cursor.execute('''
                CREATE TABLE confirmations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    confirmed_at TEXT NOT NULL,
                    FOREIGN KEY (event_id) REFERENCES events (id)
                )
            ''')
            
            # Reviews table
            cursor.execute('''
                CREATE TABLE reviews (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    rating INTEGER,
                    comment TEXT,
                    submitted_at TEXT NOT NULL,
                    FOREIGN KEY (event_id) REFERENCES events (id)
                )
            ''')
            
            conn.commit()
            print("✅ Database initialized with correct schema")
    
    def load_restaurants(self):
        """Load restaurants from JSON"""
        try:
            with open('restaurants.json', 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            if isinstance(data, dict) and 'restaurants' in data:
                self.restaurants = data['restaurants']
            elif isinstance(data, list):
                self.restaurants = data
            else:
                self.restaurants = []
            
            print(f"✅ Loaded {len(self.restaurants)} restaurants")
            
            # Load restaurants into database
            self.load_restaurants_to_db()
        except Exception as e:
            print(f"❌ Error loading restaurants: {e}")
            self.restaurants = []
    
    def load_restaurants_to_db(self):
        """Load restaurants into database"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                for restaurant in self.restaurants:
                    # Map fields to database schema
                    name = restaurant.get('name', '')
                    description = restaurant.get('description', '')
                    address = restaurant.get('address', '')
                    phone = restaurant.get('phone', '')
                    rating = restaurant.get('rating', 0.0)
                    cuisine_type = restaurant.get('cuisine_type', restaurant.get('cuisine', ''))
                    price_range = restaurant.get('price_range', restaurant.get('average_check', ''))
                    data = json.dumps(restaurant, ensure_ascii=False)
                    
                    cursor.execute('''
                        INSERT OR REPLACE INTO restaurants 
                        (name, description, address, phone, rating, cuisine_type, price_range, data)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (name, description, address, phone, rating, cuisine_type, price_range, data))
                
                conn.commit()
                print(f"✅ Loaded {len(self.restaurants)} restaurants into database")
        except Exception as e:
            print(f"❌ Error loading restaurants to database: {e}")
    
    def get_random_restaurant(self):
        """Get random restaurant"""
        if self.restaurants:
            return random.choice(self.restaurants)
        return None
    
    def create_event(self, restaurant):
        """Create new event"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO events (restaurant_name, restaurant_data, created_at)
                VALUES (?, ?, ?)
            ''', (restaurant['name'], json.dumps(restaurant), datetime.now().isoformat()))
            
            conn.commit()
            event_id = cursor.lastrowid
            print(f"✅ Created event {event_id} for restaurant {restaurant['name']}")
            return event_id
    
    def get_active_event(self):
        """Get active event"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM events 
                WHERE status IN ('pending', 'confirmed', 'scheduled', 'review_requested')
                ORDER BY created_at DESC
                LIMIT 1
            ''')
            
            row = cursor.fetchone()
            if row:
                columns = [description[0] for description in cursor.description]
                event = dict(zip(columns, row))
                event['restaurant_data'] = json.loads(event['restaurant_data'])
                return event
            return None
    
    def confirm_event(self, event_id, user_id):
        """Confirm user participation"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Check if already confirmed
            cursor.execute('''
                SELECT id FROM confirmations 
                WHERE event_id = ? AND user_id = ?
            ''', (event_id, user_id))
            
            if cursor.fetchone():
                return False, "already_confirmed"
            
            # Add confirmation
            cursor.execute('''
                INSERT INTO confirmations (event_id, user_id, confirmed_at)
                VALUES (?, ?, ?)
            ''', (event_id, user_id, datetime.now().isoformat()))
            
            # Check if all confirmed
            cursor.execute('''
                SELECT COUNT(*) FROM confirmations WHERE event_id = ?
            ''', (event_id,))
            count = cursor.fetchone()[0]
            
            print(f"✅ User {user_id} confirmed event {event_id}. Total confirmations: {count}/{REQUIRED_CONFIRMATIONS}")
            
            if count >= REQUIRED_CONFIRMATIONS:
                cursor.execute('''
                    UPDATE events SET status = 'confirmed' WHERE id = ?
                ''', (event_id,))
                conn.commit()
                return True, "all_confirmed"
            
            conn.commit()
            return True, "confirmed"
    
    def get_confirmations(self, event_id):
        """Get event confirmations"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT user_id FROM confirmations WHERE event_id = ?
            ''', (event_id,))
            
            return [row[0] for row in cursor.fetchall()]
    
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Start command"""
        welcome_text = """
🍽️ Добро пожаловать в бот выбора ресторанов!

Этот бот предназначен для группы из 3 человек + бот.

Доступные команды:
/random - Выбрать случайный ресторан
/next_event - Проверить ближайшее событие
/stats - Статистика посещений и отзывы

Для начала выберите случайный ресторан командой /random
        """
        await update.message.reply_text(welcome_text)
    
    async def stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Statistics command"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Get total restaurants count
                cursor.execute("SELECT COUNT(*) FROM restaurants")
                total_restaurants = cursor.fetchone()[0]
                
                # Get completed events (with all reviews)
                cursor.execute("""
                    SELECT e.restaurant_name, e.datetime, COUNT(r.id) as review_count
                    FROM events e
                    LEFT JOIN reviews r ON e.id = r.event_id
                    WHERE e.status = 'completed'
                    GROUP BY e.id, e.restaurant_name, e.datetime
                    HAVING review_count >= 3
                    ORDER BY e.datetime DESC
                """)
                completed_events = cursor.fetchall()
                
                # Get all events for percentage calculation
                cursor.execute("SELECT COUNT(*) FROM events WHERE status IN ('completed', 'scheduled')")
                total_events = cursor.fetchone()[0]
                
                # Calculate statistics
                visited_restaurants = len(set([event[0] for event in completed_events]))
                completion_percentage = (len(completed_events) / total_events * 100) if total_events > 0 else 0
                restaurant_visit_percentage = (visited_restaurants / total_restaurants * 100) if total_restaurants > 0 else 0
                
                # Build statistics message
                stats_text = f"""
📊 <b>СТАТИСТИКА РЕСТОРАНОВ</b>

🍽️ <b>Общая информация:</b>
• Всего ресторанов: {total_restaurants}
• Посещено ресторанов: {visited_restaurants} ({restaurant_visit_percentage:.1f}%)
• Всего событий: {total_events}
• Завершено событий: {len(completed_events)} ({completion_percentage:.1f}%)

📅 <b>Посещенные рестораны:</b>
"""
                
                if completed_events:
                    for restaurant_name, datetime_str, review_count in completed_events:
                        stats_text += f"• {restaurant_name} ({datetime_str}) - {review_count}/3 отзывов\n"
                else:
                    stats_text += "• Пока нет завершенных событий\n"
                
                # Get recent reviews
                cursor.execute("""
                    SELECT r.rating, r.comment, e.restaurant_name, r.submitted_at
                    FROM reviews r
                    JOIN events e ON r.event_id = e.id
                    ORDER BY r.submitted_at DESC
                    LIMIT 5
                """)
                recent_reviews = cursor.fetchall()
                
                if recent_reviews:
                    stats_text += f"\n⭐ <b>Последние отзывы:</b>\n"
                    for rating, comment, restaurant_name, submitted_at in recent_reviews:
                        stars = "⭐" * rating if rating else "❓"
                        stats_text += f"{stars} <b>{restaurant_name}</b>\n"
                        if comment:
                            stats_text += f"   💬 {comment[:50]}{'...' if len(comment) > 50 else ''}\n"
                        stats_text += f"   📅 {submitted_at}\n\n"
                
                await update.message.reply_text(stats_text, parse_mode=ParseMode.HTML)
                
        except Exception as e:
            logger.error(f"Error getting statistics: {e}")
            await update.message.reply_text("❌ Ошибка при получении статистики")
    
    def is_admin(self, user_id):
        """Check if user is admin"""
        return ADMIN_USER_ID and user_id == ADMIN_USER_ID
    
    async def cancel_event_admin(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Cancel event (admin only)"""
        if not self.is_admin(update.effective_user.id):
            await update.message.reply_text("❌ Только администратор может отменить событие")
            return
        
        active_event = self.get_active_event()
        if not active_event:
            await update.message.reply_text("❌ Нет активных событий для отмены")
            return
        
        # Cancel the event
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE events SET status = 'cancelled' WHERE id = ?
            ''', (active_event['id'],))
            conn.commit()
        
        await update.message.reply_text(
            f"✅ Событие отменено администратором!\n\n"
            f"🍽️ <b>Ресторан:</b> {active_event['restaurant_name']}\n"
            f"📅 <b>Дата:</b> {active_event.get('datetime', 'Не указана')}",
            parse_mode=ParseMode.HTML
        )
    
    async def clear_reviews_admin(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Clear all reviews (admin only)"""
        if not self.is_admin(update.effective_user.id):
            await update.message.reply_text("❌ Только администратор может удалить отзывы")
            return
        
        # Clear all reviews
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM reviews')
            conn.commit()
        
        await update.message.reply_text("✅ Все отзывы удалены администратором!")
    
    async def start_notifications(self):
        """Start notification system"""
        if GROUP_CHAT_ID and not self.notification_system:
            self.notification_system = NotificationSystem(
                BOT_TOKEN, self.db_path, GROUP_CHAT_ID
            )
            asyncio.create_task(self.notification_system.start())
            logger.info("🔔 Notification system started")
    
    async def random_restaurant(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Random restaurant command"""
        # Check for active event
        active_event = self.get_active_event()
        if active_event:
            keyboard = [
                [InlineKeyboardButton("❌ Отменить событие", callback_data=f"cancel_event_{active_event['id']}")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                f"❌ У вас уже есть активное событие!\n\n"
                f"🍽️ <b>Ресторан:</b> {active_event['restaurant_name']}\n"
                f"📊 <b>Статус:</b> {active_event['status']}\n"
                f"📅 <b>Время:</b> {active_event.get('datetime', 'Не указано')}\n\n"
                f"Чтобы создать новое событие, сначала отмените текущее.",
                parse_mode=ParseMode.HTML,
                reply_markup=reply_markup
            )
            return
        
        # Get random restaurant
        restaurant = self.get_random_restaurant()
        if not restaurant:
            await update.message.reply_text("❌ Рестораны не загружены.")
            return
        
        # Create event
        event_id = self.create_event(restaurant)
        
        # Create message
        text = f"""
🍽️ <b>{restaurant['name']}</b>

📍 <b>Адрес:</b> {restaurant.get('address', 'Не указан')}
🍴 <b>Кухня:</b> {restaurant.get('cuisine', 'Не указана')}
💰 <b>Средний чек:</b> {restaurant.get('average_check', 'Не указан')}

📝 <b>Описание:</b>
{restaurant.get('description', 'Описание не указано')}

👥 <b>Подтверждения:</b> 0/{REQUIRED_CONFIRMATIONS}
        """
        
        keyboard = [
            [InlineKeyboardButton("✅ Я иду!", callback_data=f"confirm_{event_id}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            text, 
            parse_mode=ParseMode.HTML, 
            reply_markup=reply_markup
        )
    
    async def confirm_restaurant(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle confirmation"""
        query = update.callback_query
        await query.answer()
        
        event_id = int(query.data.split('_')[1])
        user_id = query.from_user.id
        
        success, status = self.confirm_event(event_id, user_id)
        
        if not success:
            await query.answer("Вы уже подтвердили участие!", show_alert=True)
            return
        
        confirmations = self.get_confirmations(event_id)
        count = len(confirmations)
        
        if status == "all_confirmed":
            await query.edit_message_text(
                "🎉 Все подтвердили участие!\n\n📅 Теперь выберите дату и время для бронирования:",
                parse_mode=ParseMode.HTML
            )
            
            # Add date/time selection buttons
            keyboard = [
                [InlineKeyboardButton("📅 Выбрать дату и время", callback_data=f"select_datetime_{event_id}")],
                [InlineKeyboardButton("⏰ Сейчас", callback_data=f"datetime_now_{event_id}")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.message.reply_text(
                "Выберите когда вы хотите пойти в ресторан:",
                reply_markup=reply_markup
            )
        else:
            # Update the message with new confirmation count
            active_event = self.get_active_event()
            if active_event:
                restaurant = active_event['restaurant_data']
                text = f"""
🍽️ <b>{restaurant['name']}</b>

📍 <b>Адрес:</b> {restaurant.get('address', 'Не указан')}
🍴 <b>Кухня:</b> {restaurant.get('cuisine', 'Не указана')}
💰 <b>Средний чек:</b> {restaurant.get('average_check', 'Не указан')}

📝 <b>Описание:</b>
{restaurant.get('description', 'Описание не указано')}

👥 <b>Подтверждения:</b> {count}/{REQUIRED_CONFIRMATIONS}
                """
                
                keyboard = [
                    [InlineKeyboardButton("✅ Я иду!", callback_data=f"confirm_{event_id}")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await query.edit_message_text(
                    text, 
                    parse_mode=ParseMode.HTML, 
                    reply_markup=reply_markup
                )
            
            await query.answer(f"Подтверждено! ({count}/{REQUIRED_CONFIRMATIONS})")
    
    async def next_event(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Check next event"""
        active_event = self.get_active_event()
        if not active_event:
            await update.message.reply_text("📅 Нет запланированных событий.")
            return
        
        confirmations = self.get_confirmations(active_event['id'])
        
        text = f"""
📅 <b>Ближайшее событие:</b>

🍽️ <b>Ресторан:</b> {active_event['restaurant_name']}
📍 <b>Адрес:</b> {active_event['restaurant_data'].get('address', 'Не указан')}
📊 <b>Статус:</b> {active_event['status']}

👥 <b>Подтверждения:</b> {len(confirmations)}/{REQUIRED_CONFIRMATIONS}
        """
        
        await update.message.reply_text(text, parse_mode=ParseMode.HTML)
    
    async def select_datetime(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle datetime selection"""
        query = update.callback_query
        await query.answer()
        
        data = query.data.split('_')
        event_id = int(data[2])
        
        await query.edit_message_text(
            "📅 Выберите дату и время для бронирования:\n\n"
            "Отправьте дату и время в формате:\n"
            "📅 <b>ДД.ММ.ГГГГ ЧЧ:ММ</b>\n\n"
            "Например: <code>15.12.2024 19:30</code>",
            parse_mode=ParseMode.HTML
        )
        
        # Store event_id in context for the next message
        context.user_data['waiting_for_datetime'] = event_id
    
    async def datetime_now(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle 'now' datetime selection"""
        query = update.callback_query
        await query.answer()
        
        data = query.data.split('_')
        event_id = int(data[2])
        
        # Set datetime to now + 1 hour
        from datetime import datetime, timedelta
        now = datetime.now() + timedelta(hours=1)
        datetime_str = now.strftime("%d.%m.%Y %H:%M")
        
        # Update event with datetime
        self.update_event_datetime(event_id, datetime_str)
        
        # Add complete event button
        keyboard = [
            [InlineKeyboardButton("✅ Завершить событие", callback_data=f"complete_event_{event_id}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            f"✅ Событие запланировано на <b>{datetime_str}</b>!\n\n"
            f"📱 Детали бронирования отправлены участникам.\n\n"
            f"После посещения нажмите 'Завершить событие' для сбора отзывов.",
            reply_markup=reply_markup,
            parse_mode=ParseMode.HTML
        )
        
        # Send booking details to participants
        await self.send_booking_details(event_id, datetime_str)
    
    async def send_booking_details(self, event_id, datetime_str):
        """Send booking details to all participants"""
        try:
            event = self.get_event(event_id)
            if not event:
                return
            
            # Get all participants
            participants = self.get_event_participants(event_id)
            
            booking_message = f"""
🍽️ <b>Детали бронирования</b>

📅 <b>Дата и время:</b> {datetime_str}
🏪 <b>Ресторан:</b> {event['restaurant_name']}

📍 <b>Адрес:</b> {event['restaurant_data'].get('address', 'Не указан')}
📞 <b>Телефон:</b> {event['restaurant_data'].get('phone', 'Не указан')}

Приятного аппетита! 🍴
            """
            
            # Send to each participant
            for user_id in participants:
                try:
                    await self.application.bot.send_message(
                        chat_id=user_id,
                        text=booking_message,
                        parse_mode=ParseMode.HTML
                    )
                except Exception as e:
                    logger.error(f"Error sending booking details to user {user_id}: {e}")
                    
        except Exception as e:
            logger.error(f"Error sending booking details: {e}")
    
    def update_event_datetime(self, event_id, datetime_str):
        """Update event with datetime"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE events SET status = 'scheduled', datetime = ? WHERE id = ?
            ''', (datetime_str, event_id))
            conn.commit()
    
    async def handle_datetime_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle datetime input from user"""
        if 'waiting_for_datetime' not in context.user_data:
            return
        
        event_id = context.user_data['waiting_for_datetime']
        datetime_text = update.message.text.strip()
        
        # Simple datetime validation
        try:
            from datetime import datetime
            datetime.strptime(datetime_text, "%d.%m.%Y %H:%M")
            
            # Update event with datetime
            self.update_event_datetime(event_id, datetime_text)
            
            # Add complete event button
            keyboard = [
                [InlineKeyboardButton("✅ Завершить событие", callback_data=f"complete_event_{event_id}")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                f"✅ Событие запланировано на <b>{datetime_text}</b>!\n\n"
                f"📱 Детали бронирования отправлены участникам.\n\n"
                f"После посещения нажмите 'Завершить событие' для сбора отзывов.",
                reply_markup=reply_markup,
                parse_mode=ParseMode.HTML
            )
            
            # Send booking details to participants
            await self.send_booking_details(event_id, datetime_text)
            
            # Clear waiting state
            del context.user_data['waiting_for_datetime']
            
        except ValueError:
            await update.message.reply_text(
                "❌ Неверный формат даты!\n\n"
                "Используйте формат: <b>ДД.ММ.ГГГГ ЧЧ:ММ</b>\n"
                "Например: <code>15.12.2024 19:30</code>",
                parse_mode=ParseMode.HTML
            )
    
    async def cancel_event(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Cancel active event"""
        query = update.callback_query
        await query.answer()
        
        data = query.data.split('_')
        event_id = int(data[2])
        
        # Update event status to cancelled
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE events SET status = 'cancelled' WHERE id = ?
            ''', (event_id,))
            conn.commit()
        
        await query.edit_message_text(
            "✅ Событие отменено!\n\n"
            "Теперь вы можете создать новое событие командой /random",
            parse_mode=ParseMode.HTML
        )
    
    async def complete_event(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Complete event and request reviews"""
        query = update.callback_query
        await query.answer()
        
        data = query.data.split('_')
        event_id = int(data[2])
        
        # Update event status to completed
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE events SET status = 'completed' WHERE id = ?
            ''', (event_id,))
            conn.commit()
        
        # Get event details
        event = self.get_event(event_id)
        if event:
            await query.edit_message_text(
                f"🎉 Событие завершено!\n\n"
                f"🍽️ <b>Ресторан:</b> {event['restaurant_name']}\n"
                f"📅 <b>Дата:</b> {event.get('datetime', 'Не указана')}\n\n"
                f"⭐ Теперь оставьте отзыв о ресторане!",
                parse_mode=ParseMode.HTML
            )
            
            # Request first review
            keyboard = [
                [InlineKeyboardButton("⭐ Отзыв Участник 1", callback_data=f"review_{event_id}_1")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.message.reply_text(
                "📝 <b>Оставьте отзыв о ресторане:</b>\n\n"
                "Оцените ресторан от 1 до 5 звезд и напишите комментарий.",
                reply_markup=reply_markup,
                parse_mode=ParseMode.HTML
            )
    
    async def request_review(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Request review from user"""
        query = update.callback_query
        await query.answer()
        
        data = query.data.split('_')
        event_id = int(data[1])
        participant_id = int(data[2]) if len(data) > 2 else 1
        
        # Store event_id and participant_id for review
        context.user_data['reviewing_event'] = event_id
        context.user_data['participant_id'] = participant_id
        
        participant_name = f"Участник {participant_id}"
        
        await query.edit_message_text(
            f"⭐ <b>Оцените ресторан ({participant_name}):</b>\n\n"
            "Выберите оценку от 1 до 5 звезд:",
            parse_mode=ParseMode.HTML
        )
        
        # Rating buttons with participant_id
        keyboard = [
            [
                InlineKeyboardButton("⭐", callback_data=f"rating_{event_id}_{participant_id}_1"),
                InlineKeyboardButton("⭐⭐", callback_data=f"rating_{event_id}_{participant_id}_2"),
                InlineKeyboardButton("⭐⭐⭐", callback_data=f"rating_{event_id}_{participant_id}_3"),
                InlineKeyboardButton("⭐⭐⭐⭐", callback_data=f"rating_{event_id}_{participant_id}_4"),
                InlineKeyboardButton("⭐⭐⭐⭐⭐", callback_data=f"rating_{event_id}_{participant_id}_5")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.message.reply_text(
            f"Выберите оценку ({participant_name}):",
            reply_markup=reply_markup
        )
    
    async def handle_rating(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle rating selection"""
        query = update.callback_query
        await query.answer()
        
        data = query.data.split('_')
        event_id = int(data[1])
        participant_id = int(data[2])
        rating = int(data[3])
        
        participant_name = f"Участник {participant_id}"
        
        # Store rating and participant info
        context.user_data['selected_rating'] = rating
        context.user_data['participant_id'] = participant_id
        
        await query.edit_message_text(
            f"⭐ Оценка ({participant_name}): {rating} звезд\n\n"
            f"💬 Теперь напишите комментарий (или отправьте 'пропустить'):"
        )
        
        # Set waiting for comment
        context.user_data['waiting_for_comment'] = event_id
    
    async def handle_comment(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle comment input"""
        if 'waiting_for_comment' not in context.user_data:
            return
        
        event_id = context.user_data['waiting_for_comment']
        comment = update.message.text.strip()
        rating = context.user_data.get('selected_rating', 0)
        participant_id = context.user_data.get('participant_id', 1)
        
        participant_name = f"Участник {participant_id}"
        
        # Save review with participant info in comment
        full_comment = f"[{participant_name}] {comment}"
        
        # Save review
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO reviews (event_id, user_id, rating, comment, submitted_at)
                VALUES (?, ?, ?, ?, ?)
            ''', (event_id, update.effective_user.id, rating, full_comment, datetime.now().isoformat()))
            conn.commit()
            
            # Check if all reviews are submitted
            cursor.execute('''
                SELECT COUNT(*) FROM reviews WHERE event_id = ?
            ''', (event_id,))
            review_count = cursor.fetchone()[0]
        
        # Clear user data
        del context.user_data['waiting_for_comment']
        del context.user_data['selected_rating']
        del context.user_data['reviewing_event']
        del context.user_data['participant_id']
        
        await update.message.reply_text(
            f"✅ Отзыв сохранен! ({participant_name})\n\n"
            f"⭐ Оценка: {rating} звезд\n"
            f"💬 Комментарий: {comment if comment != 'пропустить' else 'Не указан'}\n\n"
            f"📊 Отзывов получено: {review_count}/3 (от 3 участников)"
        )
        
        # Check if all reviews are submitted
        if review_count >= 3:
            # Update event status to completed
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    UPDATE events SET status = 'completed' WHERE id = ?
                ''', (event_id,))
                conn.commit()
            
            # Get event details
            event = self.get_event(event_id)
            if event:
                await update.message.reply_text(
                    f"🎉 <b>Поздравляем!</b>\n\n"
                    f"Все 3 участника оставили отзывы о ресторане!\n\n"
                    f"🍽️ <b>Ресторан:</b> {event['restaurant_name']}\n"
                    f"📅 <b>Дата:</b> {event.get('datetime', 'Не указана')}\n\n"
                    f"✅ Ресторан успешно пройден!\n"
                    f"🎯 Запланируйте следующее событие командой /random",
                    parse_mode=ParseMode.HTML
                )
        else:
            # Send next review form
            next_participant_id = review_count + 1
            next_participant_name = f"Участник {next_participant_id}"
            
            # Get event details for next form
            event = self.get_event(event_id)
            if event:
                message = f"""
⭐ <b>Следующий отзыв!</b>

🍽️ <b>Ресторан:</b> {event['restaurant_name']}
📅 <b>Дата:</b> {event.get('datetime', 'Не указана')}
👤 <b>Участник:</b> {next_participant_name}

Пожалуйста, оставьте отзыв о посещении ресторана.
                """
                
                # Add review button for next participant
                keyboard = [
                    [InlineKeyboardButton(f"⭐ Отзыв {next_participant_name}", callback_data=f"review_{event_id}_{next_participant_id}")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                # Send to the group
                await update.message.reply_text(
                    text=message,
                    reply_markup=reply_markup,
                    parse_mode='HTML'
                )

def main():
    """Main function"""
    print("🍽️ Starting Perfect Restaurant Bot...")
    
    if not Path('restaurants.json').exists():
        print("❌ restaurants.json file not found!")
        return
    
    bot = PerfectRestaurantBot()
    
    # Create application
    application = Application.builder().token(BOT_TOKEN).build()
    bot.application = application
    
    # Add handlers
    application.add_handler(CommandHandler("start", bot.start))
    application.add_handler(CommandHandler("random", bot.random_restaurant))
    application.add_handler(CommandHandler("next_event", bot.next_event))
    application.add_handler(CommandHandler("stats", bot.stats))
    application.add_handler(CommandHandler("cancel_event", bot.cancel_event_admin))
    application.add_handler(CommandHandler("clear_reviews", bot.clear_reviews_admin))
    application.add_handler(CallbackQueryHandler(bot.confirm_restaurant, pattern="^confirm_"))
    application.add_handler(CallbackQueryHandler(bot.select_datetime, pattern="^select_datetime_"))
    application.add_handler(CallbackQueryHandler(bot.datetime_now, pattern="^datetime_now_"))
    application.add_handler(CallbackQueryHandler(bot.cancel_event, pattern="^cancel_event_"))
    application.add_handler(CallbackQueryHandler(bot.complete_event, pattern="^complete_event_"))
    application.add_handler(CallbackQueryHandler(bot.request_review, pattern="^review_"))
    application.add_handler(CallbackQueryHandler(bot.handle_rating, pattern="^rating_"))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, bot.handle_datetime_message))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, bot.handle_comment))
    
    print("🤖 Bot started successfully!")
    print("📱 Add bot to your group and use /start command")
    print("🛑 Press Ctrl+C to stop")
    
    # Run the bot
    try:
        application.run_polling()
    except KeyboardInterrupt:
        print("\n👋 Bot stopped by user")
        if bot.notification_system:
            bot.notification_system.stop()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n👋 Goodbye!")
    except Exception as e:
        print(f"❌ Error: {e}")
        logger.error(f"Error: {e}")
