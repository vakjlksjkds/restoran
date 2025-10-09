#!/usr/bin/env python3
"""
Notification System for Restaurant Bot
"""

import asyncio
import sqlite3
import json
from datetime import datetime, timedelta
from telegram import Bot
import logging

logger = logging.getLogger(__name__)

class NotificationSystem:
    def __init__(self, bot_token, db_path, group_chat_id):
        self.bot = Bot(token=bot_token)
        self.db_path = db_path
        self.group_chat_id = group_chat_id
        self.running = False
    
    async def start(self):
        """Start notification system"""
        self.running = True
        logger.info("🔔 Notification system started")
        
        while self.running:
            try:
                await self.check_and_send_notifications()
                await asyncio.sleep(3600)  # Check every hour
            except Exception as e:
                logger.error(f"Error in notification system: {e}")
                await asyncio.sleep(3600)
    
    def stop(self):
        """Stop notification system"""
        self.running = False
        logger.info("🔔 Notification system stopped")
    
    async def check_and_send_notifications(self):
        """Check for events that need notifications"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Get scheduled events
                cursor.execute('''
                    SELECT * FROM events 
                    WHERE status = 'scheduled' AND datetime IS NOT NULL
                ''')
                
                events = cursor.fetchall()
                columns = [description[0] for description in cursor.description]
                
                for event_row in events:
                    event = dict(zip(columns, event_row))
                    await self.check_event_notifications(event)
                
                # Get events waiting for reviews
                cursor.execute('''
                    SELECT * FROM events 
                    WHERE status = 'review_requested'
                ''')
                
                review_events = cursor.fetchall()
                
                for event_row in review_events:
                    event = dict(zip(columns, event_row))
                    await self.check_review_reminders(event)
                    
        except Exception as e:
            logger.error(f"Error checking notifications: {e}")
    
    async def check_event_notifications(self, event):
        """Check if event needs notifications"""
        try:
            event_datetime = datetime.strptime(event['datetime'], "%d.%m.%Y %H:%M")
            now = datetime.now()
            
            # Check for 5 days before notification
            five_days_before = event_datetime - timedelta(days=5)
            if five_days_before.date() == now.date() and now.hour == 9:
                await self.send_five_days_notification(event)
            
            # Check for day of event notifications (2 times)
            if event_datetime.date() == now.date():
                if now.hour == 9:  # Morning notification
                    await self.send_morning_notification(event)
                elif now.hour == 18:  # Evening notification
                    await self.send_evening_notification(event)
            
            # Check for review request (3 hours after event)
            three_hours_after = event_datetime + timedelta(hours=3)
            # Check if we're within 1 hour of the 3-hour mark
            if (three_hours_after.date() == now.date() and 
                three_hours_after.hour == now.hour and 
                abs(three_hours_after.minute - now.minute) <= 30):
                await self.send_review_request(event)
                
        except Exception as e:
            logger.error(f"Error checking event notifications: {e}")
    
    async def check_review_reminders(self, event):
        """Check if review reminders need to be sent"""
        try:
            now = datetime.now()
            
            # Send daily reminder at 10:00 AM
            if now.hour == 10 and now.minute < 30:
                await self.send_review_reminder(event)
                
        except Exception as e:
            logger.error(f"Error checking review reminders: {e}")
    
    async def send_five_days_notification(self, event):
        """Send 5 days before notification"""
        try:
            message = f"""
🔔 <b>Напоминание о событии</b>

🍽️ <b>Ресторан:</b> {event['restaurant_name']}
📅 <b>Дата:</b> {event['datetime']}
⏰ <b>До события:</b> 5 дней

Не забудьте о предстоящем походе в ресторан!
            """
            
            await self.bot.send_message(
                chat_id=self.group_chat_id,
                text=message,
                parse_mode='HTML'
            )
            logger.info(f"Sent 5 days notification for event {event['id']}")
            
        except Exception as e:
            logger.error(f"Error sending 5 days notification: {e}")
    
    async def send_morning_notification(self, event):
        """Send morning notification on event day"""
        try:
            message = f"""
🌅 <b>Доброе утро!</b>

Сегодня у вас запланирован поход в ресторан!

🍽️ <b>Ресторан:</b> {event['restaurant_name']}
📅 <b>Время:</b> {event['datetime']}

Приятного аппетита! 🍴
            """
            
            await self.bot.send_message(
                chat_id=self.group_chat_id,
                text=message,
                parse_mode='HTML'
            )
            logger.info(f"Sent morning notification for event {event['id']}")
            
        except Exception as e:
            logger.error(f"Error sending morning notification: {e}")
    
    async def send_evening_notification(self, event):
        """Send evening notification on event day"""
        try:
            message = f"""
🌆 <b>Вечернее напоминание</b>

Не забудьте о походе в ресторан!

🍽️ <b>Ресторан:</b> {event['restaurant_name']}
📅 <b>Время:</b> {event['datetime']}

Удачного вечера! 🌟
            """
            
            await self.bot.send_message(
                chat_id=self.group_chat_id,
                text=message,
                parse_mode='HTML'
            )
            logger.info(f"Sent evening notification for event {event['id']}")
            
        except Exception as e:
            logger.error(f"Error sending evening notification: {e}")
    
    async def send_review_request(self, event):
        """Send review request 3 hours after event"""
        try:
            # Check if reviews already requested
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT COUNT(*) FROM reviews WHERE event_id = ?
                ''', (event['id'],))
                review_count = cursor.fetchone()[0]
                
                if review_count > 0:
                    return  # Reviews already requested
                
                # Check if review request already sent (by checking if status is 'review_requested')
                cursor.execute('''
                    SELECT status FROM events WHERE id = ?
                ''', (event['id'],))
                status = cursor.fetchone()[0]
                
                if status == 'review_requested':
                    return  # Review request already sent
            
            # Update event status to review_requested
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    UPDATE events SET status = 'review_requested' WHERE id = ?
                ''', (event['id'],))
                conn.commit()
            
            # Get all participants
            participants = self.get_event_participants(event['id'])
            
            # Send first review form to first participant only
            if participants:
                first_participant = participants[0]
                message = f"""
⭐ <b>Время оставить отзыв!</b>

Надеемся, вам понравилось в ресторане!

🍽️ <b>Ресторан:</b> {event['restaurant_name']}
📅 <b>Дата:</b> {event['datetime']}

Пожалуйста, оставьте отзыв о посещении ресторана.
                """
                
                # Add review button for first participant
                from telegram import InlineKeyboardButton, InlineKeyboardMarkup
                keyboard = [
                    [InlineKeyboardButton("⭐ Отзыв Участник 1", callback_data=f"review_{event['id']}_1")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                # Send to first participant
                try:
                    await self.bot.send_message(
                        chat_id=first_participant,
                        text=message,
                        reply_markup=reply_markup,
                        parse_mode='HTML'
                    )
                except Exception as e:
                    logger.error(f"Error sending review request to user {first_participant}: {e}")
            logger.info(f"Sent first review request for event {event['id']}")
            
        except Exception as e:
            logger.error(f"Error sending review request: {e}")
    
    def get_event_participants(self, event_id):
        """Get all participants of an event"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT user_id FROM confirmations WHERE event_id = ?
                ''', (event_id,))
                
                return [row[0] for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Error getting event participants: {e}")
            return []
    
    async def send_review_reminder(self, event):
        """Send daily reminder for missing reviews"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT COUNT(*) FROM reviews WHERE event_id = ?
                ''', (event['id'],))
                review_count = cursor.fetchone()[0]
                
                if review_count >= 3:
                    return  # All reviews submitted
                
                # Get participants who haven't left reviews
                cursor.execute('''
                    SELECT c.user_id FROM confirmations c
                    LEFT JOIN reviews r ON c.user_id = r.user_id AND c.event_id = r.event_id
                    WHERE c.event_id = ? AND r.user_id IS NULL
                ''', (event['id'],))
                missing_reviews = [row[0] for row in cursor.fetchall()]
            
            if not missing_reviews:
                return  # All participants have left reviews
            
            message = f"""
⏰ <b>Напоминание об отзыве</b>

Вы еще не оставили отзыв о ресторане!

🍽️ <b>Ресторан:</b> {event['restaurant_name']}
📅 <b>Дата:</b> {event['datetime']}
📊 <b>Отзывов получено:</b> {review_count}/3

Пожалуйста, оставьте отзыв!
            """
            
            from telegram import InlineKeyboardButton, InlineKeyboardMarkup
            keyboard = [
                [InlineKeyboardButton("⭐ Оставить отзыв", callback_data=f"review_{event['id']}")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            # Send reminder to each participant who hasn't left a review
            for user_id in missing_reviews:
                try:
                    await self.bot.send_message(
                        chat_id=user_id,
                        text=message,
                        reply_markup=reply_markup,
                        parse_mode='HTML'
                    )
                except Exception as e:
                    logger.error(f"Error sending review reminder to user {user_id}: {e}")
            
            logger.info(f"Sent review reminders for event {event['id']} to {len(missing_reviews)} users")
            
        except Exception as e:
            logger.error(f"Error sending review reminder: {e}")
