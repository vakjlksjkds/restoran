import os
import sqlite3
import threading
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime, timedelta, timezone

_DB_LOCK = threading.Lock()


def _get_db_path() -> str:
	return os.getenv("DB_PATH", os.path.join(os.path.dirname(__file__), "bot.db"))


def _connect() -> sqlite3.Connection:
	conn = sqlite3.connect(_get_db_path(), check_same_thread=False)
	conn.row_factory = sqlite3.Row
	return conn


def init_db() -> None:
	with _DB_LOCK:
		conn = _connect()
		try:
			cur = conn.cursor()
			cur.execute(
				"""
				CREATE TABLE IF NOT EXISTS restaurants (
					id INTEGER PRIMARY KEY AUTOINCREMENT,
					source_id INTEGER,
					name TEXT NOT NULL,
					address TEXT,
					cuisine TEXT,
					description TEXT,
					average_check TEXT,
					UNIQUE(name, address)
				)
				"""
			)
			cur.execute(
				"""
				CREATE TABLE IF NOT EXISTS events (
					id INTEGER PRIMARY KEY AUTOINCREMENT,
					chat_id INTEGER NOT NULL,
					restaurant_id INTEGER NOT NULL,
					message_id INTEGER NOT NULL,
					reminder_at_utc TEXT,
					reminder_sent INTEGER DEFAULT 0,
					feedback_prompt_sent INTEGER DEFAULT 0,
					feedback_message_id INTEGER,
					created_at_utc TEXT NOT NULL
				)
				"""
			)
			cur.execute(
				"""
				CREATE TABLE IF NOT EXISTS participants (
					id INTEGER PRIMARY KEY AUTOINCREMENT,
					event_id INTEGER NOT NULL,
					user_id INTEGER NOT NULL,
					username TEXT,
					first_name TEXT,
					joined INTEGER NOT NULL DEFAULT 1,
					joined_at_utc TEXT,
					review_left INTEGER DEFAULT 0,
					cancelled INTEGER DEFAULT 0,
					penalty_amount INTEGER DEFAULT 0,
					UNIQUE(event_id, user_id)
				)
				"""
			)
			cur.execute(
				"""
				CREATE TABLE IF NOT EXISTS reviews (
					id INTEGER PRIMARY KEY AUTOINCREMENT,
					event_id INTEGER NOT NULL,
					user_id INTEGER NOT NULL,
					username TEXT,
					text TEXT NOT NULL,
					rating INTEGER,
					created_at_utc TEXT NOT NULL,
					UNIQUE(event_id, user_id)
				)
				"""
			)
			# Индексы для производительности
			cur.execute("CREATE INDEX IF NOT EXISTS idx_events_chat ON events(chat_id)")
			cur.execute("CREATE INDEX IF NOT EXISTS idx_participants_event_joined ON participants(event_id, joined)")
			cur.execute("CREATE INDEX IF NOT EXISTS idx_participants_event_user ON participants(event_id, user_id)")
			cur.execute("CREATE INDEX IF NOT EXISTS idx_reviews_event ON reviews(event_id)")
			cur.execute("CREATE INDEX IF NOT EXISTS idx_reviews_event_user ON reviews(event_id, user_id)")
			conn.commit()
		finally:
			conn.close()


def import_restaurants_from_json(data: Dict[str, Any]) -> int:
	inserted = 0
	restaurants = data.get("restaurants", [])
	with _DB_LOCK:
		conn = _connect()
		try:
			cur = conn.cursor()
			for item in restaurants:
				name = (item.get("name") or "").strip()
				address = (item.get("address") or "").strip()
				if not name:
					continue
				cur.execute(
					"""
					INSERT OR IGNORE INTO restaurants (source_id, name, address, cuisine, description, average_check)
					VALUES (?, ?, ?, ?, ?, ?)
					""",
					(
						item.get("id"),
						name,
						address,
						item.get("cuisine"),
						item.get("description"),
						item.get("average_check"),
					),
				)
				if cur.rowcount > 0:
					inserted += 1
			conn.commit()
		finally:
			conn.close()
	return inserted


def import_restaurants_from_csv_rows(rows: List[Dict[str, str]]) -> int:
	inserted = 0
	with _DB_LOCK:
		conn = _connect()
		try:
			cur = conn.cursor()
			for row in rows:
				name = (row.get("name") or "").strip()
				address = (row.get("address") or "").strip()
				if not name:
					continue
				cur.execute(
					"""
					INSERT OR IGNORE INTO restaurants (name, address, cuisine, description, average_check)
					VALUES (?, ?, ?, ?, ?)
					""",
					(
						name,
						address,
						row.get("cuisine"),
						row.get("description"),
						row.get("average_check"),
					),
				)
				if cur.rowcount > 0:
					inserted += 1
			conn.commit()
		finally:
			conn.close()
	return inserted


def count_restaurants() -> int:
	with _DB_LOCK:
		conn = _connect()
		try:
			cur = conn.cursor()
			cur.execute("SELECT COUNT(*) FROM restaurants")
			return int(cur.fetchone()[0])
		finally:
			conn.close()


def get_random_restaurant() -> Optional[sqlite3.Row]:
	"""Возвращает ресторан, который ещё не считается посещённым (>=3 уникальных отзывов)."""
	with _DB_LOCK:
		conn = _connect()
		try:
			cur = conn.cursor()
			cur.execute(
				"""
				SELECT r.id, r.name, r.address, r.cuisine, r.description, r.average_check
				FROM restaurants r
				WHERE r.id NOT IN (
				    SELECT e.restaurant_id
				    FROM events e
				    JOIN reviews rv ON rv.event_id = e.id
				    GROUP BY e.id
				    HAVING COUNT(DISTINCT rv.user_id) >= 3
				)
				ORDER BY RANDOM()
				LIMIT 1
				"""
			)
			return cur.fetchone()
		finally:
			conn.close()


def create_event(chat_id: int, restaurant_id: int, message_id: int) -> int:
	created_at = datetime.now(timezone.utc).isoformat()
	with _DB_LOCK:
		conn = _connect()
		try:
			cur = conn.cursor()
			cur.execute(
				"""
				INSERT INTO events (chat_id, restaurant_id, message_id, created_at_utc)
				VALUES (?, ?, ?, ?)
				""",
				(chat_id, restaurant_id, message_id, created_at),
			)
			conn.commit()
			return int(cur.lastrowid)
		finally:
			conn.close()


def get_latest_event_for_chat(chat_id: int) -> Optional[sqlite3.Row]:
	with _DB_LOCK:
		conn = _connect()
		try:
			cur = conn.cursor()
			cur.execute(
				"""
				SELECT * FROM events
				WHERE chat_id = ?
				ORDER BY id DESC
				LIMIT 1
				""",
				(chat_id,),
			)
			row = cur.fetchone()
			return row
		finally:
			conn.close()


def toggle_participation(event_id: int, user_id: int, username: Optional[str], first_name: Optional[str]) -> tuple[bool, Optional[str]]:
	"""
	Переключает участие пользователя.
	Возвращает (joined: bool, error_message: Optional[str])
	"""
	joined_at = datetime.now(timezone.utc).isoformat()
	with _DB_LOCK:
		conn = _connect()
		try:
			cur = conn.cursor()
			cur.execute(
				"SELECT id, joined FROM participants WHERE event_id = ? AND user_id = ?",
				(event_id, user_id),
			)
			existing = cur.fetchone()
			if existing is None:
				# Проверяем количество текущих участников (защита от race condition)
				cur.execute(
					"SELECT COUNT(*) FROM participants WHERE event_id = ? AND joined = 1",
					(event_id,)
				)
				current_count = int(cur.fetchone()[0])
				if current_count >= 3:
					return False, "Уже набрано максимум 3 участника"
				
				cur.execute(
					"""
					INSERT INTO participants (event_id, user_id, username, first_name, joined, joined_at_utc)
					VALUES (?, ?, ?, ?, 1, ?)
					""",
					(event_id, user_id, username, first_name, joined_at),
				)
				conn.commit()
				return True, None
			else:
				new_joined = 0 if int(existing["joined"]) == 1 else 1
				# Если пытается записаться снова, проверяем лимит
				if new_joined == 1:
					cur.execute(
						"SELECT COUNT(*) FROM participants WHERE event_id = ? AND joined = 1",
						(event_id,)
					)
					current_count = int(cur.fetchone()[0])
					if current_count >= 3:
						return False, "Уже набрано максимум 3 участника"
				
				cur.execute(
					"UPDATE participants SET joined = ?, joined_at_utc = ?, username = ?, first_name = ? WHERE id = ?",
					(new_joined, joined_at, username, first_name, int(existing["id"])),
				)
				conn.commit()
				return bool(new_joined), None
		finally:
			conn.close()


def list_participant_usernames(event_id: int) -> List[str]:
	with _DB_LOCK:
		conn = _connect()
		try:
			cur = conn.cursor()
			cur.execute(
				"SELECT username, first_name FROM participants WHERE event_id = ? AND joined = 1 ORDER BY joined_at_utc ASC",
				(event_id,),
			)
			result: List[str] = []
			for row in cur.fetchall():
				username = row["username"]
				first_name = row["first_name"]
				if username:
					result.append(f"@{username}")
				elif first_name:
					result.append(first_name)
				else:
					result.append("Без имени")
			return result
		finally:
			conn.close()


def set_reminder(event_id: int, dt_utc: datetime) -> None:
	with _DB_LOCK:
		conn = _connect()
		try:
			cur = conn.cursor()
			cur.execute(
				"UPDATE events SET reminder_at_utc = ?, reminder_sent = 0 WHERE id = ?",
				(dt_utc.isoformat(), event_id),
			)
			conn.commit()
		finally:
			conn.close()


def mark_reminder_sent(event_id: int) -> None:
	with _DB_LOCK:
		conn = _connect()
		try:
			cur = conn.cursor()
			cur.execute("UPDATE events SET reminder_sent = 1 WHERE id = ?", (event_id,))
			conn.commit()
		finally:
			conn.close()


def mark_feedback_prompt_sent(event_id: int, feedback_message_id: int) -> None:
	with _DB_LOCK:
		conn = _connect()
		try:
			cur = conn.cursor()
			cur.execute(
				"UPDATE events SET feedback_prompt_sent = 1, feedback_message_id = ? WHERE id = ?",
				(feedback_message_id, event_id),
			)
			conn.commit()
		finally:
			conn.close()


def is_participant(event_id: int, user_id: int) -> bool:
	"""Проверяет, является ли пользователь участником события."""
	with _DB_LOCK:
		conn = _connect()
		try:
			cur = conn.cursor()
			cur.execute(
				"SELECT id FROM participants WHERE event_id = ? AND user_id = ? AND joined = 1",
				(event_id, user_id),
			)
			return cur.fetchone() is not None
		finally:
			conn.close()


def save_review(event_id: int, user_id: int, username: Optional[str], text: str, rating: Optional[int] = None) -> tuple[bool, str]:
	"""
	Сохраняет или обновляет отзыв.
	Возвращает (success: bool, message: str)
	"""
	created_at = datetime.now(timezone.utc).isoformat()
	with _DB_LOCK:
		conn = _connect()
		try:
			cur = conn.cursor()
			# Проверяем участие
			if not is_participant(event_id, user_id):
				return False, "Вы не участвовали в этом походе"
			
			# Пытаемся вставить, если есть - обновляем
			try:
				cur.execute(
					"""
					INSERT INTO reviews (event_id, user_id, username, text, rating, created_at_utc)
					VALUES (?, ?, ?, ?, ?, ?)
					""",
					(event_id, user_id, username, text, rating, created_at),
				)
				message = "Спасибо за отзыв!"
			except sqlite3.IntegrityError:
				# Уже есть отзыв - обновляем
				cur.execute(
					"""
					UPDATE reviews
					SET text = ?, rating = ?, username = ?, created_at_utc = ?
					WHERE event_id = ? AND user_id = ?
					""",
					(text, rating, username, created_at, event_id, user_id),
				)
				message = "Ваш отзыв обновлён!"
			
			# отмечаем что участник оставил отзыв
			cur.execute(
				"UPDATE participants SET review_left = 1 WHERE event_id = ? AND user_id = ?",
				(event_id, user_id),
			)
			conn.commit()
			return True, message
		finally:
			conn.close()


def get_event_with_details(event_id: int) -> Optional[sqlite3.Row]:
	with _DB_LOCK:
		conn = _connect()
		try:
			cur = conn.cursor()
			cur.execute(
				"""
				SELECT e.*, r.name AS r_name, r.address AS r_address, r.cuisine AS r_cuisine,
				       r.description AS r_description, r.average_check AS r_avg_check
				FROM events e JOIN restaurants r ON r.id = e.restaurant_id
				WHERE e.id = ?
				""",
				(event_id,),
			)
			return cur.fetchone()
		finally:
			conn.close()


def get_event_by_feedback_message(chat_id: int, feedback_message_id: int) -> Optional[sqlite3.Row]:
	with _DB_LOCK:
		conn = _connect()
		try:
			cur = conn.cursor()
			cur.execute(
				"""
				SELECT e.*, r.name AS r_name, r.address AS r_address, r.cuisine AS r_cuisine,
				       r.description AS r_description, r.average_check AS r_avg_check
				FROM events e JOIN restaurants r ON r.id = e.restaurant_id
				WHERE e.chat_id = ? AND e.feedback_message_id = ?
				LIMIT 1
				""",
				(chat_id, feedback_message_id),
			)
			return cur.fetchone()
		finally:
			conn.close()


def get_due_reminders(now_utc: datetime) -> List[sqlite3.Row]:
	with _DB_LOCK:
		conn = _connect()
		try:
			cur = conn.cursor()
			cur.execute(
				"""
				SELECT * FROM events
				WHERE reminder_at_utc IS NOT NULL
					AND reminder_sent = 0
					AND datetime(reminder_at_utc) <= datetime(?)
				""",
				(now_utc.isoformat(),),
			)
			return cur.fetchall()
		finally:
			conn.close()


def get_due_feedback_prompts(now_utc: datetime) -> List[sqlite3.Row]:
	with _DB_LOCK:
		conn = _connect()
		try:
			cur = conn.cursor()
			cur.execute(
				"""
				SELECT * FROM events
				WHERE reminder_at_utc IS NOT NULL
					AND reminder_sent = 1
					AND feedback_prompt_sent = 0
					AND datetime(reminder_at_utc, '+24 hours') <= datetime(?)
				""",
				(now_utc.isoformat(),),
			)
			return cur.fetchall()
		finally:
			conn.close()


def get_all_feedback_to_schedule() -> List[sqlite3.Row]:
	"""Все события с назначенным reminder, для которых ещё не отправлен запрос фидбека."""
	with _DB_LOCK:
		conn = _connect()
		try:
			cur = conn.cursor()
			cur.execute(
				"""
				SELECT * FROM events
				WHERE reminder_at_utc IS NOT NULL
					AND feedback_prompt_sent = 0
				"""
			)
			return cur.fetchall()
		finally:
			conn.close()


def get_stats() -> Tuple[List[sqlite3.Row], List[sqlite3.Row]]:
	with _DB_LOCK:
		conn = _connect()
		try:
			cur = conn.cursor()
			# Visited: events with at least one review
			cur.execute(
				"""
				SELECT e.id, r.name, r.address, COUNT(rv.id) AS reviews_count,
					AVG(CASE WHEN rv.rating IS NOT NULL THEN rv.rating END) AS avg_rating
				FROM events e
				JOIN restaurants r ON r.id = e.restaurant_id
				LEFT JOIN reviews rv ON rv.event_id = e.id
				GROUP BY e.id
				HAVING COUNT(rv.id) > 0
				ORDER BY e.id DESC
				"""
			)
			visited = cur.fetchall()
			# Upcoming: events scheduled but no reviews yet
			cur.execute(
				"""
				SELECT e.id, r.name, r.address, e.reminder_at_utc
				FROM events e JOIN restaurants r ON r.id = e.restaurant_id
				LEFT JOIN reviews rv ON rv.event_id = e.id
				GROUP BY e.id
				HAVING COUNT(rv.id) = 0
				ORDER BY e.id DESC
				"""
			)
			upcoming = cur.fetchall()
			return visited, upcoming
		finally:
			conn.close()


def get_stats_for_chat(chat_id: int) -> Tuple[List[sqlite3.Row], List[sqlite3.Row]]:
    with _DB_LOCK:
        conn = _connect()
        try:
            cur = conn.cursor()
            # Visited for a chat: events with at least one review
            cur.execute(
                """
                SELECT e.id, r.name, r.address, COUNT(rv.id) AS reviews_count,
                    AVG(CASE WHEN rv.rating IS NOT NULL THEN rv.rating END) AS avg_rating
                FROM events e
                JOIN restaurants r ON r.id = e.restaurant_id
                LEFT JOIN reviews rv ON rv.event_id = e.id
                WHERE e.chat_id = ?
                GROUP BY e.id
                HAVING COUNT(rv.id) > 0
                ORDER BY e.id DESC
                """,
                (chat_id,),
            )
            visited = cur.fetchall()

            # Upcoming for a chat: >=3 joined and <3 distinct reviews
            cur.execute(
                """
                SELECT e.id, r.name, r.address, e.reminder_at_utc
                FROM events e
                JOIN restaurants r ON r.id = e.restaurant_id
                LEFT JOIN participants p ON p.event_id = e.id AND p.joined = 1
                LEFT JOIN reviews rv ON rv.event_id = e.id
                WHERE e.chat_id = ?
                GROUP BY e.id
                HAVING COUNT(DISTINCT p.user_id) >= 3 AND COUNT(DISTINCT rv.user_id) < 3
                ORDER BY e.id DESC
                """,
                (chat_id,),
            )
            upcoming = cur.fetchall()
            return visited, upcoming
        finally:
            conn.close()


def get_reviews_for_event(event_id: int) -> List[sqlite3.Row]:
	with _DB_LOCK:
		conn = _connect()
		try:
			cur = conn.cursor()
			cur.execute(
				"""
				SELECT username, text, rating, created_at_utc
				FROM reviews
				WHERE event_id = ?
				ORDER BY created_at_utc ASC
				""",
				(event_id,),
			)
			return cur.fetchall()
		finally:
			conn.close()


def cancel_participation(event_id: int, user_id: int) -> None:
	"""Отменяет участие с установкой штрафа 500₽."""
	with _DB_LOCK:
		conn = _connect()
		try:
			cur = conn.cursor()
			cur.execute(
				"UPDATE participants SET joined = 0, cancelled = 1, penalty_amount = 500 WHERE event_id = ? AND user_id = ?",
				(event_id, user_id),
			)
			conn.commit()
		finally:
			conn.close()


def get_user_penalty(user_id: int) -> int:
	"""Возвращает текущий штраф пользователя."""
	with _DB_LOCK:
		conn = _connect()
		try:
			cur = conn.cursor()
			# берём последний штраф (если есть cancelled=1 и penalty_amount > 0)
			cur.execute(
				"""
				SELECT penalty_amount
				FROM participants
				WHERE user_id = ? AND cancelled = 1 AND penalty_amount > 0
				ORDER BY id DESC
				LIMIT 1
				""",
				(user_id,),
			)
			row = cur.fetchone()
			return int(row["penalty_amount"]) if row else 0
		finally:
			conn.close()


def clear_user_penalty(user_id: int) -> None:
	"""Сбрасывает штраф после успешного похода."""
	with _DB_LOCK:
		conn = _connect()
		try:
			cur = conn.cursor()
			cur.execute(
				"UPDATE participants SET penalty_amount = 0 WHERE user_id = ? AND cancelled = 1",
				(user_id,),
			)
			conn.commit()
		finally:
			conn.close()


def get_participants_without_review(event_id: int) -> List[sqlite3.Row]:
	"""Возвращает участников события, не оставивших отзыв."""
	with _DB_LOCK:
		conn = _connect()
		try:
			cur = conn.cursor()
			cur.execute(
				"""
				SELECT user_id, username, first_name
				FROM participants
				WHERE event_id = ? AND joined = 1 AND review_left = 0
				""",
				(event_id,),
			)
			return cur.fetchall()
		finally:
			conn.close()


def cancel_event(event_id: int) -> bool:
	"""Отменяет событие полностью (удаляет напоминание)."""
	with _DB_LOCK:
		conn = _connect()
		try:
			cur = conn.cursor()
			cur.execute(
				"UPDATE events SET reminder_at_utc = NULL, reminder_sent = 1 WHERE id = ?",
				(event_id,),
			)
			conn.commit()
			return cur.rowcount > 0
		finally:
			conn.close()


def delete_event_with_relations(event_id: int) -> None:
	"""Удаляет событие вместе с участниками и отзывами."""
	with _DB_LOCK:
		conn = _connect()
		try:
			cur = conn.cursor()
			cur.execute("DELETE FROM participants WHERE event_id = ?", (event_id,))
			cur.execute("DELETE FROM reviews WHERE event_id = ?", (event_id,))
			cur.execute("DELETE FROM events WHERE id = ?", (event_id,))
			conn.commit()
		finally:
			conn.close()


# ---------------------------------------------------------------------------
# Counts and listings
# ---------------------------------------------------------------------------


def get_joined_participants_count(event_id: int) -> int:
    with _DB_LOCK:
        conn = _connect()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT COUNT(*) FROM participants WHERE event_id = ? AND joined = 1",
                (event_id,),
            )
            return int(cur.fetchone()[0])
        finally:
            conn.close()


def get_upcoming_events(chat_id: int) -> List[sqlite3.Row]:
    """События текущего чата с >=3 участниками и без отзывов (предстоящие)."""
    with _DB_LOCK:
        conn = _connect()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT e.id, e.chat_id, e.reminder_at_utc, r.name AS r_name
                FROM events e
                JOIN restaurants r ON r.id = e.restaurant_id
                LEFT JOIN participants p ON p.event_id = e.id AND p.joined = 1
                LEFT JOIN reviews rv ON rv.event_id = e.id
                WHERE e.chat_id = ?
                GROUP BY e.id
                HAVING COUNT(DISTINCT p.user_id) >= 3 AND COUNT(DISTINCT rv.user_id) < 3
                ORDER BY e.id DESC
                """,
                (chat_id,),
            )
            return cur.fetchall()
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# Demo data helpers
# ---------------------------------------------------------------------------


def ensure_demo_visit() -> None:
	"""Создаёт демо-событие с отзывами, если база пуста."""
	with _DB_LOCK:
		conn = _connect()
		try:
			cur = conn.cursor()
			cur.execute("SELECT COUNT(*) FROM reviews")
			if int(cur.fetchone()[0]) > 0:
				return

			cur.execute("SELECT id FROM restaurants ORDER BY id LIMIT 1")
			row = cur.fetchone()
			if not row:
				return

			# Обновляем схему participants, если в старой БД нет нужных колонок
			cur.execute("PRAGMA table_info(participants)")
			existing_cols = {r[1] for r in cur.fetchall()}
			if "review_left" not in existing_cols:
				cur.execute("ALTER TABLE participants ADD COLUMN review_left INTEGER DEFAULT 0")
			if "cancelled" not in existing_cols:
				cur.execute("ALTER TABLE participants ADD COLUMN cancelled INTEGER DEFAULT 0")
			if "penalty_amount" not in existing_cols:
				cur.execute("ALTER TABLE participants ADD COLUMN penalty_amount INTEGER DEFAULT 0")

			restaurant_id = int(row["id"])
			now = datetime.now(timezone.utc).isoformat()

			cur.execute(
				"""
				INSERT INTO events (chat_id, restaurant_id, message_id, reminder_at_utc,
									reminder_sent, feedback_prompt_sent, feedback_message_id, created_at_utc)
				VALUES (?, ?, ?, NULL, 1, 1, NULL, ?)
				""",
				(0, restaurant_id, 0, now),
			)
			event_id = int(cur.lastrowid)

			participants = [
				(100001, "demo_alex", "Алексей", 5, "5 Отличное место, вернёмся!"),
				(100002, "demo_maria", "Мария", 4, "4 Очень уютно, но можно быстрее подавать блюда."),
				(100003, "demo_ivan", "Иван", 5, "5 Великолепный сервис и кухня."),
			]

			for user_id, username, first_name, rating, review_text in participants:
				cur.execute(
					"""
					INSERT INTO participants (event_id, user_id, username, first_name,
											  joined, joined_at_utc, review_left, cancelled, penalty_amount)
					VALUES (?, ?, ?, ?, 1, ?, 1, 0, 0)
					""",
					(event_id, user_id, username, first_name, now),
				)
				cur.execute(
					"""
					INSERT INTO reviews (event_id, user_id, username, text, rating, created_at_utc)
					VALUES (?, ?, ?, ?, ?, ?)
					""",
					(event_id, user_id, username, review_text, rating, now),
				)

			conn.commit()
		finally:
			conn.close()


# Удаление демо-данных (если были добавлены ранее)
def cleanup_demo_data() -> None:
    with _DB_LOCK:
        conn = _connect()
        try:
            cur = conn.cursor()
            # Сначала находим события с chat_id=0 (наши демо)
            cur.execute("SELECT id FROM events WHERE chat_id = 0")
            ids = [int(r[0]) for r in cur.fetchall()]
            for eid in ids:
                cur.execute("DELETE FROM participants WHERE event_id = ?", (eid,))
                cur.execute("DELETE FROM reviews WHERE event_id = ?", (eid,))
                cur.execute("DELETE FROM events WHERE id = ?", (eid,))
            conn.commit()
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# New helper to determine completion status of an event
# ---------------------------------------------------------------------------


def is_event_completed(event_id: int) -> bool:
    """Возвращает True, если для события оставлено ≥3 отзывов."""
    with _DB_LOCK:
        conn = _connect()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT COUNT(*) FROM participants WHERE event_id = ? AND review_left = 1",
                (event_id,),
            )
            reviews_by_participants = int(cur.fetchone()[0])
            return reviews_by_participants >= 3
        finally:
            conn.close()
