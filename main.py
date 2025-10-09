import os
import io
import csv
import json
import asyncio
import html
from typing import List, Optional
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from dotenv import load_dotenv
import logging

from telegram import (
	Update,
	InlineKeyboardButton,
	InlineKeyboardMarkup,
	constants,
	Document,
	BotCommand,
	ReplyKeyboardMarkup,
	KeyboardButton,
	ReplyKeyboardRemove,
)
from telegram.ext import (
	Application,
	ApplicationBuilder,
	CommandHandler,
	MessageHandler,
	CallbackQueryHandler,
	ContextTypes,
	filters,
)

from db import (
    init_db,
    migrate_schema,
    import_restaurants_from_json,
    import_restaurants_from_csv_rows,
    count_restaurants,
    get_random_restaurant,
    create_event,
    get_latest_event_for_chat,
    toggle_participation,
    list_participant_usernames,
    set_reminder,
    mark_reminder_sent,
    mark_feedback_prompt_sent,
    save_review,
    get_event_with_details,
    get_due_reminders,
    get_due_feedback_prompts,
    get_stats,
    get_stats_for_chat,
    get_all_feedback_to_schedule,
    get_event_by_feedback_message,
    get_reviews_for_event,
    cancel_participation,
    get_user_penalty,
    clear_user_penalty,
    get_participants_without_review,
    is_participant,
    is_event_completed,
    get_joined_participants_count,
    get_upcoming_events,
    delete_event_with_relations,
    mark_event_completed,
    count_distinct_reviews,
    clear_reviews_by_restaurant_name,
    ensure_demo_visit,
    cleanup_demo_data,
    get_random_restaurant_for_chat,
)

# ---- Helpers for reviews formatting/toggler ----
def _calc_reviews_stats(reviews: List[dict]) -> tuple[int, Optional[float], str]:
    count = len(reviews)
    ratings = [int(r["rating"]) for r in reviews if r["rating"] is not None]
    avg = round(sum(ratings) / len(ratings), 1) if ratings else None
    stars = ""
    if avg is not None:
        stars = "⭐" * int(round(avg))
    return count, avg, stars


def _format_event_text(event_row, reviews: List[dict], *, include_reviews: bool) -> str:
    name = event_row["r_name"] or "Без названия"
    address = event_row["r_address"] or "—"
    cuisine = event_row["r_cuisine"] or "—"
    count, avg, stars = _calc_reviews_stats(reviews)

    lines: List[str] = []
    lines.append(f"<b>{html.escape(name)}</b>")
    lines.append(f"📍 {html.escape(address)}")
    lines.append(f"🍴 {html.escape(cuisine)}")

    rating_line = f"Отзывы: {count}"
    if avg is not None:
        rating_line += f" — {avg:.1f} {stars}"
    lines.append(rating_line)

    if include_reviews:
        if reviews:
            lines.append("")
            for rev in reviews:
                username = rev["username"] or "Аноним"
                rating = int(rev["rating"]) if rev["rating"] is not None else None
                rating_stars = "⭐" * rating if rating else ""
                text = html.escape(rev["text"] or "")
                username_escaped = html.escape(username)
                entry = f"{username_escaped}: {rating_stars} {text}".strip()
                lines.append(entry)
        else:
            lines.append("Пока нет отзывов.")

    return "\n".join(lines)


def _build_reviews_keyboard(event_id: int, *, show_reviews: bool) -> InlineKeyboardMarkup:
    label = "Скрыть отзывы" if show_reviews else "Показать отзывы"
    action = "hide" if show_reviews else "show"
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(label, callback_data=f"reviews:{event_id}:{action}")]]
    )

# загрузка .env
load_dotenv()

# базовый логгер
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("bot")

BOT_TOKEN = os.getenv("BOT_TOKEN")
_tz_env = os.getenv("TIMEZONE", "Europe/Moscow")
try:
    ZoneInfo(_tz_env)
    TIMEZONE = _tz_env
except Exception:
    TIMEZONE = "Europe/Moscow"
    logger.warning("Invalid TIMEZONE env; fallback to Europe/Moscow")
# fallback к RENDER_EXTERNAL_URL, если WEBHOOK_BASE_URL не задан
WEBHOOK_BASE_URL = os.getenv("WEBHOOK_BASE_URL") or os.getenv("RENDER_EXTERNAL_URL")
WEBHOOK_PATH = os.getenv("WEBHOOK_PATH", "/webhook")
PORT = int(os.getenv("PORT", "8080"))


def _fmt_restaurant_card(row, participants: List[str]) -> str:
	name = row["name"]
	address = row["address"] or "—"
	cuisine = row["cuisine"] or "—"
	description = row["description"] or "—"
	avg_check = row["average_check"] or "—"
	participants_line = ", ".join(participants) if participants else "пока никого"
	
	return (
		f"🍽 <b>{name}</b>\n"
		f"{'─' * 30}\n"
		f"📍 <b>Адрес:</b> {address}\n"
		f"🍴 <b>Кухня:</b> {cuisine}\n"
		f"💰 <b>Средний чек:</b> {avg_check}\n\n"
		f"📝 <i>{description}</i>\n"
		f"{'─' * 30}\n"
		f"👥 <b>Идут ({len(participants)}/3):</b> {participants_line}"
	)


async def _send_random_for_chat(context: ContextTypes.DEFAULT_TYPE, chat_id: int) -> None:
    # блокировка при незавершённом событии
    latest = get_latest_event_for_chat(chat_id)
    if latest:
        event_id = int(latest["id"])
        if is_event_completed(event_id):
            delete_event_with_relations(event_id)
        else:
            await context.bot.send_message(
                chat_id=chat_id,
                text=(
                    "Сначала завершите текущий поход (нужны отзывы от всех 3 участников), "
                    "а затем можно выбрать новый ресторан."
                ),
            )
            return

    row = get_random_restaurant_for_chat(chat_id)
    if not row:
        await context.bot.send_message(chat_id=chat_id, text="Список ресторанов пуст. Загрузите файл JSON/CSV.")
        return

    participants: List[str] = []
    text = _fmt_restaurant_card(row, participants)
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("Я иду! ✅", callback_data="join:pending")]])
    msg = await context.bot.send_message(chat_id=chat_id, text=text, parse_mode=constants.ParseMode.HTML, reply_markup=keyboard)

    event_id = create_event(chat_id=chat_id, restaurant_id=int(row["id"]), message_id=msg.message_id)
    keyboard2 = InlineKeyboardMarkup([[InlineKeyboardButton("Я иду! ✅", callback_data=f"join:{event_id}")]])
    await context.bot.edit_message_reply_markup(chat_id=chat_id, message_id=msg.message_id, reply_markup=keyboard2)


async def _send_stats_for_chat(context: ContextTypes.DEFAULT_TYPE, chat_id: int) -> None:
    visited, upcoming = get_stats_for_chat(chat_id)
    total_cnt = count_restaurants()
    visited_cnt = len(visited)
    percent = (visited_cnt / total_cnt * 100) if total_cnt else 0

    lines: List[str] = []
    lines.append(f"<b>Всего ресторанов</b>: {total_cnt}")
    lines.append(f"<b>Посещено</b>: {visited_cnt} из {total_cnt} (≈{percent:.0f}%)")
    if upcoming:
        lines.append("")
        lines.append("<b>Предстоящие рестораны</b>:")
        for row in upcoming:
            name = row["name"]
            reminder = row["reminder_at_utc"]
            when = "дата не назначена"
            if reminder:
                try:
                    dt_local = datetime.fromisoformat(reminder).replace(tzinfo=timezone.utc).astimezone(ZoneInfo(TIMEZONE))
                    when = dt_local.strftime("%d.%m.%Y %H:%M")
                except Exception:
                    pass
            lines.append(f"• {name} — {when}")

    await context.bot.send_message(chat_id=chat_id, text="\n".join(lines), parse_mode=constants.ParseMode.HTML)

    if not visited:
        await context.bot.send_message(chat_id=chat_id, text="Посещённых ресторанов пока нет.")
        return

    await context.bot.send_message(chat_id=chat_id, text="<b>Посещённые рестораны</b> — нажмите, чтобы открыть отзывы.", parse_mode=constants.ParseMode.HTML)

    for row in visited:
        event_id = int(row["id"])
        event = get_event_with_details(event_id)
        if not event:
            continue
        reviews = get_reviews_for_event(event_id)
        text = _format_event_text(event, reviews, include_reviews=False)
        keyboard = _build_reviews_keyboard(event_id, show_reviews=False)
        await context.bot.send_message(chat_id=chat_id, text=text, parse_mode=constants.ParseMode.HTML, reply_markup=keyboard)


async def _send_upcoming_for_chat(context: ContextTypes.DEFAULT_TYPE, chat_id: int) -> None:
    rows = get_upcoming_events(chat_id)
    if not rows:
        await context.bot.send_message(chat_id=chat_id, text="Нет предстоящих событий.")
        return
    local_tz = ZoneInfo(TIMEZONE)
    lines: List[str] = ["<b>Предстоящие события</b>:"]
    for r in rows:
        when = "дата не назначена"
        if r["reminder_at_utc"]:
            try:
                dt_local = datetime.fromisoformat(r["reminder_at_utc"]).replace(tzinfo=timezone.utc).astimezone(local_tz)
                when = dt_local.strftime("%d.%m.%Y %H:%M")
            except Exception:
                pass
        lines.append(f"• {r['r_name']} — {when}")
    await context.bot.send_message(chat_id=chat_id, text="\n".join(lines), parse_mode=constants.ParseMode.HTML)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	await update.message.reply_text(
		"Привет! Я помогу выбрать ресторан. Доступные команды:\n"
		"/random_restaurant — выбрать случайный ресторан\n"
		"/set_reminder DD.MM.YYYY HH:MM — установить время встречи\n"
		"/stats — показать статистику\n\n"
		"Админ может загрузить JSON/CSV с ресторанами, отправив файл в чат.",
	)


async def random_restaurant(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	chat_id = update.effective_chat.id
	await _send_random_for_chat(context, chat_id)


async def on_join_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	query = update.callback_query
	data = query.data or ""
	if not data.startswith("join:"):
		await query.answer()
		return
	parts = data.split(":", 1)
	if len(parts) != 2:
		await query.answer()
		return
	try:
		event_id = int(parts[1])
	except ValueError:
		await query.answer()
		return

	user = query.from_user
	joined, error_msg = toggle_participation(
		event_id=event_id,
		user_id=user.id,
		username=user.username,
		first_name=user.first_name,
	)
	
	# Если ошибка (лимит участников), показываем и не обновляем карточку
	if error_msg:
		await query.answer(error_msg, show_alert=True)
		return
	
	# обновляем текст карточки
	event = get_event_with_details(event_id)
	if not event:
		await query.answer()
		return
	participants = list_participant_usernames(event_id)
	# Получить ресторан снова для актуального текста
	restaurant = {
		"name": event["r_name"],
		"address": event["r_address"],
		"cuisine": event["r_cuisine"],
		"description": event["r_description"],
		"average_check": event["r_avg_check"],
	}
	text = _fmt_restaurant_card(restaurant, participants)
	
	# Кнопка "Я иду" всегда есть
	buttons = [
		[InlineKeyboardButton("Я иду! ✅", callback_data=f"join:{event_id}")],
	]
	# Кнопка "Отменить" показывается только текущему пользователю, если он записан
	if is_participant(event_id, user.id):
		buttons.append([InlineKeyboardButton("Отменить поход ❌", callback_data=f"cancel:{event_id}")])
	
	keyboard = InlineKeyboardMarkup(buttons)
	try:
		await context.bot.edit_message_text(
			chat_id=event["chat_id"],
			message_id=event["message_id"],
			text=text,
			parse_mode=constants.ParseMode.HTML,
			reply_markup=keyboard,
		)
	except Exception as e:
		logger.error(f"Failed to update message: {e}")
	
	# показываем штраф если есть
	penalty = get_user_penalty(user.id)
	answer_text = "Вы записались!" if joined else "Вы передумали."
	if penalty > 0 and joined:
		answer_text += f" У вас штраф {penalty}₽ за отмену предыдущего похода."
	await query.answer(answer_text, show_alert=False)

	# если теперь ровно 3 участника и дата ещё не назначена, просим установить время
	if len(participants) == 3 and event["reminder_at_utc"] is None:
		await context.bot.send_message(
			chat_id=event["chat_id"],
			text="Все согласны! Отправьте дату и время похода в формате DD.MM.YYYY HH:MM",
		)


async def set_reminder_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	chat_id = update.effective_chat.id
	args_text = (update.message.text or "").strip()
	parts = args_text.split(maxsplit=1)
	if len(parts) < 2:
		await update.message.reply_text("Формат: /set_reminder DD.MM.YYYY HH:MM")
		return
	when_str = parts[1].strip()
	try:
		local_tz = ZoneInfo(TIMEZONE)
		dt_local = datetime.strptime(when_str, "%d.%m.%Y %H:%M").replace(tzinfo=local_tz)
		dt_utc = dt_local.astimezone(timezone.utc)
	except Exception as e:
		logger.error(f"Failed to parse date: {e}")
		await update.message.reply_text("Неверный формат. Используйте DD.MM.YYYY HH:MM")
		return

	# Проверка на дату в прошлом
	now_utc = datetime.now(timezone.utc)
	if dt_utc <= now_utc:
		await update.message.reply_text("Нельзя установить время в прошлом. Выберите будущую дату и время.")
		return
	# Максимум на 20 лет вперёд
	if dt_utc > now_utc + timedelta(days=365*20):
		await update.message.reply_text("Слишком далеко. Максимум на 20 лет вперёд.")
		return

	event = get_latest_event_for_chat(chat_id)
	if not event:
		await update.message.reply_text("Сначала выберите ресторан через /random_restaurant")
		return

	# Разрешать установку времени только когда 3 участника подтвердили
	cnt = get_joined_participants_count(int(event["id"]))
	if cnt < 3:
		await update.message.reply_text("Время можно выбрать только после подтверждения 3 участников.")
		return

	event_id = int(event["id"])
	set_reminder(event_id=event_id, dt_utc=dt_utc)
	# Снимаем возможные старые задачи на это событие
	for job_name in (f"reminder_{event_id}", f"feedback_{event_id}", f"daily_reviews_{event_id}"):
		for job in context.job_queue.get_jobs_by_name(job_name):
			job.schedule_removal()
	# Именованные задачи, чтобы можно было отменять/восстанавливать без дублей
	context.job_queue.run_once(send_reminder_job, when=dt_utc, data={"event_id": event_id}, name=f"reminder_{event_id}")
	context.job_queue.run_once(send_feedback_prompt_job, when=dt_utc + timedelta(hours=3), data={"event_id": event_id}, name=f"feedback_{event_id}")
	context.job_queue.run_repeating(
		remind_pending_reviews_job,
		interval=timedelta(days=1),
		first=dt_utc + timedelta(days=1),
		data={"event_id": event_id},
		name=f"daily_reviews_{event_id}",
	)

	await update.message.reply_text(
		f"✅ Событие подтверждено!\n🍽 Ресторан: {event['r_name']}\n📅 Дата: {dt_local.strftime('%d.%m.%Y %H:%M %Z')}"
	)


async def send_reminder_job(context: ContextTypes.DEFAULT_TYPE) -> None:
	data = context.job.data or {}
	event_id = int(data.get("event_id"))
	event = get_event_with_details(event_id)
	if not event:
		logger.warning(f"Event {event_id} not found for reminder")
		return
	participants = list_participant_usernames(event_id)
	participants_line = ", ".join(participants) if participants else "пока никого"
	# Время в локальном часовом поясе
	local_tz = ZoneInfo(TIMEZONE)
	rem_at_utc = event["reminder_at_utc"]
	desc_time = "время не указано"
	if rem_at_utc:
		try:
			dt_local = datetime.fromisoformat(rem_at_utc).replace(tzinfo=timezone.utc).astimezone(local_tz)
			desc_time = dt_local.strftime("%H:%M")
		except Exception as e:
			logger.error(f"Failed to parse reminder time: {e}")

	text = (
		f"Напоминание: сегодня в {desc_time} вы идёте в ресторан {event['r_name']}! "
		f"Адрес: {event['r_address']}. Список участников: {participants_line}"
	)
	try:
		await context.bot.send_message(chat_id=event["chat_id"], text=text)
		mark_reminder_sent(event_id)
		logger.info(f"Reminder sent for event {event_id}")
	except Exception as e:
		logger.error(f"Failed to send reminder for event {event_id}: {e}")


async def send_feedback_prompt_job(context: ContextTypes.DEFAULT_TYPE) -> None:
	data = context.job.data or {}
	event_id = int(data.get("event_id"))
	event = get_event_with_details(event_id)
	if not event:
		logger.warning(f"Event {event_id} not found for feedback prompt")
		return
	try:
		msg = await context.bot.send_message(
			chat_id=event["chat_id"],
			text=f"Как вам было в {event['r_name']}? Пожалуйста, оставьте свой отзыв, ответив на это сообщение!\n\nФормат: [Рейтинг 1-5 звёзд] Текст отзыва\nПример: 5 Отличное место, вернёмся!",
		)
		mark_feedback_prompt_sent(event_id, feedback_message_id=msg.message_id)
		logger.info(f"Feedback prompt sent for event {event_id}")
	except Exception as e:
		logger.error(f"Failed to send feedback prompt for event {event_id}: {e}")


async def remind_pending_reviews_job(context: ContextTypes.DEFAULT_TYPE) -> None:
	"""Напоминает участникам, не оставившим отзыв."""
	data = context.job.data or {}
	event_id = int(data.get("event_id"))
	event = get_event_with_details(event_id)
	if not event:
		logger.warning(f"Event {event_id} not found for pending review reminder")
		return
	
	pending = get_participants_without_review(event_id)
	if not pending:
		logger.info(f"No pending reviews for event {event_id}, stopping reminders")
		# Останавливаем повторяющееся задание если все оставили отзывы
		context.job.schedule_removal()
		return
	
	for p in pending:
		user_id = int(p["user_id"])
		username = p["username"] or p["first_name"] or "участник"
		try:
			await context.bot.send_message(
				chat_id=user_id,
				text=f"Напоминаем: вы ещё не оставили отзыв о ресторане {event['r_name']}. Пожалуйста, ответьте на сообщение в группе!",
			)
			logger.info(f"Sent review reminder to user {user_id} for event {event_id}")
		except Exception as e:
			# если личка закрыта, пишем в группу
			logger.warning(f"Failed to send DM to user {user_id}, sending to group: {e}")
			try:
				await context.bot.send_message(
					chat_id=event["chat_id"],
					text=f"@{username}, напоминаем оставить отзыв о {event['r_name']}!",
				)
			except Exception as e2:
				logger.error(f"Failed to send group reminder: {e2}")


async def stats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _send_stats_for_chat(context, update.effective_chat.id)


async def on_freeform_datetime(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Принимает дату/время формата DD.MM.YYYY HH:MM из обычного сообщения."""
    chat_id = update.effective_chat.id
    when_str = (update.message.text or "").strip()
    logger.info(f"Processing datetime input: '{when_str}' in chat {chat_id}")
    
    try:
        local_tz = ZoneInfo(TIMEZONE)
        # Пробуем разные форматы
        dt_local = None
        for fmt in ("%d.%m.%Y %H:%M", "%d.%m.%Y %H.%M", "%d.%m.%Y %H-%M"):
            try:
                dt_local = datetime.strptime(when_str, fmt).replace(tzinfo=local_tz)
                break
            except ValueError:
                continue
        
        if dt_local is None:
            raise ValueError("No matching format")
            
        dt_utc = dt_local.astimezone(timezone.utc)
    except Exception as e:
        logger.warning(f"Freeform datetime parse failed for '{when_str}': {e}")
        await update.message.reply_text("❌ Неверный формат. Используйте DD.MM.YYYY HH:MM\nПример: 25.12.2024 13:00")
        return

    now_utc = datetime.now(timezone.utc)
    if dt_utc <= now_utc:
        await update.message.reply_text("Нельзя установить время в прошлом. Выберите будущую дату и время.")
        return
    if dt_utc > now_utc + timedelta(days=365*20):
        await update.message.reply_text("Слишком далеко. Максимум на 20 лет вперёд.")
        return

    event = get_latest_event_for_chat(chat_id)
    if not event:
        await update.message.reply_text("Сначала выберите ресторан через /random_restaurant")
        return

    cnt = get_joined_participants_count(int(event["id"]))
    if cnt < 3:
        await update.message.reply_text("Время можно выбрать только после подтверждения 3 участников.")
        return

    event_id = int(event["id"])
    set_reminder(event_id=event_id, dt_utc=dt_utc)
    # снять возможные старые задачи
    for job_name in (f"reminder_{event_id}", f"feedback_{event_id}", f"daily_reviews_{event_id}"):
        for job in context.job_queue.get_jobs_by_name(job_name):
            job.schedule_removal()
    # назначить новые
    context.job_queue.run_once(send_reminder_job, when=dt_utc, data={"event_id": event_id}, name=f"reminder_{event_id}")
    context.job_queue.run_once(send_feedback_prompt_job, when=dt_utc + timedelta(hours=3), data={"event_id": event_id}, name=f"feedback_{event_id}")
    context.job_queue.run_repeating(
        remind_pending_reviews_job,
        interval=timedelta(days=1),
        first=dt_utc + timedelta(days=1),
        data={"event_id": event_id},
        name=f"daily_reviews_{event_id}",
    )

    await update.message.reply_text(
        f"✅ Событие подтверждено!\n🍽 Ресторан: {event['r_name']}\n📅 Дата: {dt_local.strftime('%d.%m.%Y %H:%M %Z')}"
    )


async def on_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	message = update.message
	if not message or not message.document:
		return
	chat = update.effective_chat
	user = update.effective_user

	is_admin = False
	try:
		member = await context.bot.get_chat_member(chat_id=chat.id, user_id=user.id)
		is_admin = member.status in ("creator", "administrator")
	except Exception:
		pass

	if not is_admin and chat.type in ("group", "supergroup"):
		await message.reply_text("Только администратор может импортировать список ресторанов.")
		return

	doc: Document = message.document
	file_name = (doc.file_name or "").lower()
	if not (file_name.endswith(".json") or file_name.endswith(".csv")):
		await message.reply_text("Поддерживаются только .json и .csv")
		return

	file = await context.bot.get_file(doc.file_id)
	file_bytes = await file.download_as_bytes()
	inserted = 0
	try:
		if file_name.endswith(".json"):
			data = json.loads(file_bytes.decode("utf-8"))
			inserted = import_restaurants_from_json(data)
		else:
			stream = io.StringIO(file_bytes.decode("utf-8"))
			reader = csv.DictReader(stream)
			rows = [row for row in reader]
			inserted = import_restaurants_from_csv_rows(rows)
		await message.reply_text(f"Импортировано ресторанов: {inserted}")
	except Exception as e:
		await message.reply_text(f"Ошибка импорта: {e}")


async def on_cancel_trip(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	"""Обрабатывает нажатие кнопку 'Отменить поход'."""
	query = update.callback_query
	await query.answer()
	data = query.data or ""
	if not data.startswith("cancel:"):
		return
	parts = data.split(":", 1)
	if len(parts) != 2:
		return
	try:
		event_id = int(parts[1])
	except ValueError:
		return
	
	user = query.from_user
	# отменяем участие и ставим штраф
	cancel_participation(event_id, user.id)
	
	# обновляем карточку
	event = get_event_with_details(event_id)
	if not event:
		return
	participants = list_participant_usernames(event_id)
	restaurant = {
		"name": event["r_name"],
		"address": event["r_address"],
		"cuisine": event["r_cuisine"],
		"description": event["r_description"],
		"average_check": event["r_avg_check"],
	}
	text = _fmt_restaurant_card(restaurant, participants)
	keyboard = InlineKeyboardMarkup(
		[[InlineKeyboardButton("Я иду! ✅", callback_data=f"join:{event_id}")]]
	)
	await context.bot.edit_message_text(
		chat_id=event["chat_id"],
		message_id=event["message_id"],
		text=text,
		parse_mode=constants.ParseMode.HTML,
		reply_markup=keyboard,
	)
	await query.answer("Поход отменён. Штраф 500₽ будет учтён в следующем походе.", show_alert=True)


# ---------------------------------------------------------------------------
# Сброс события админом (очищает участников и отзывы, даёт снова выбрать)
# ---------------------------------------------------------------------------


async def on_reset_event(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Кнопка ♻️ Сбросить — только администратор."""
    query = update.callback_query
    await query.answer()

    data = query.data or ""
    if not data.startswith("reset:"):
        return

    parts = data.split(":", 1)
    if len(parts) != 2:
        return

    try:
        event_id = int(parts[1])
    except ValueError:
        return

    user = query.from_user
    chat_id = query.message.chat_id if query.message else None

    # Проверяем, что пользователь админ
    is_admin = False
    try:
        member = await context.bot.get_chat_member(chat_id=chat_id, user_id=user.id)
        is_admin = member.status in ("creator", "administrator")
    except Exception:
        pass

    if not is_admin:
        await query.answer("Только администратор может сбросить событие.", show_alert=True)
        return

    # Отменяем задачи, затем удаляем событие
    for job_name in (f"reminder_{event_id}", f"feedback_{event_id}", f"daily_reviews_{event_id}"):
        for job in context.job_queue.get_jobs_by_name(job_name):
            job.schedule_removal()
    delete_event_with_relations(event_id)

    # удаляем сообщение с карточкой, чтобы не висело
    if query.message:
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=query.message.message_id)
        except Exception:
            pass

    await context.bot.send_message(
        chat_id=chat_id,
        text="Событие сброшено администратором. Можно выбрать новый ресторан через /random_restaurant",
    )


async def on_text_review(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	message = update.message
	if not message or not message.text:
		return
	if not message.reply_to_message:
		return
	chat_id = update.effective_chat.id
	reply_id = message.reply_to_message.message_id
	# ищем событие по feedback_message_id
	event = get_event_by_feedback_message(chat_id=chat_id, feedback_message_id=reply_id)
	if not event:
		return

	text = message.text.strip()
	rating: Optional[int] = None
	if text and text[0].isdigit():
		try:
			d = int(text[0])
			if 1 <= d <= 5:
				rating = d
		except Exception as e:
			logger.warning(f"Failed to parse rating: {e}")

	success, reply_msg = save_review(
		event_id=int(event["id"]),
		user_id=update.effective_user.id,
		username=update.effective_user.username,
		text=text,
		rating=rating,
	)
	
	if not success:
		await message.reply_text(reply_msg)
		return
	
	# сбрасываем штраф после оставления отзыва (человек «отработал» поход)
	clear_user_penalty(update.effective_user.id)
	# автозавершение события: если теперь 3 уникальных отзыва — помечаем завершённым, снимаем ежедневные job'ы и уведомляем чат
	ev_id = int(event["id"])
	if count_distinct_reviews(ev_id) >= 3:
		mark_event_completed(ev_id)
		# снять напоминания
		for job_name in (f"daily_reviews_{ev_id}",):
			for job in context.job_queue.get_jobs_by_name(job_name):
				job.schedule_removal()
		try:
			await context.bot.send_message(
				chat_id=event["chat_id"],
				text=f"Событие завершено: получено 3 отзыва по ресторану {event['r_name']}. Спасибо!",
			)
		except Exception:
			pass
	await message.reply_text(reply_msg)


async def cancel_event_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	"""Отменяет текущее событие (только для админов)."""
	chat = update.effective_chat
	user = update.effective_user
	
	# Проверка прав администратора
	is_admin = False
	try:
		member = await context.bot.get_chat_member(chat_id=chat.id, user_id=user.id)
		is_admin = member.status in ("creator", "administrator")
	except Exception as e:
		logger.error(f"Failed to check admin status: {e}")
	
	if not is_admin and chat.type in ("group", "supergroup"):
		await update.message.reply_text("Только администратор может отменить событие.")
		return
	
	event = get_latest_event_for_chat(chat.id)
	if not event:
		await update.message.reply_text("Нет активного события для отмены.")
		return
	
	event_id = int(event["id"])
	for job_name in (f"reminder_{event_id}", f"feedback_{event_id}", f"daily_reviews_{event_id}"):
		for job in context.job_queue.get_jobs_by_name(job_name):
			job.schedule_removal()
	delete_event_with_relations(event_id)

	# удаляем карточку ресторана, если сообщение существует
	message_id = event["message_id"]
	try:
		await context.bot.delete_message(chat_id=chat.id, message_id=message_id)
	except Exception as e:
		logger.debug(f"Failed to delete event message {message_id}: {e}")

	await update.message.reply_text("Событие отменено. Можно выбрать новый ресторан через /random_restaurant")
	logger.info(f"Event {event_id} deleted by admin {user.id}")


async def clear_reviews_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	"""Очищает отзывы по ресторану (только для админов). Формат: /clear_reviews Название ресторана"""
	logger.info(f"clear_reviews_cmd called by user {update.effective_user.id}")
	chat = update.effective_chat
	user = update.effective_user
	
	is_admin = False
	try:
		member = await context.bot.get_chat_member(chat_id=chat.id, user_id=user.id)
		is_admin = member.status in ("creator", "administrator")
		logger.info(f"User {user.id} admin status: {is_admin}, status: {member.status}")
	except Exception as e:
		logger.error(f"Failed to check admin status: {e}")
	
	if not is_admin and chat.type in ("group", "supergroup"):
		await update.message.reply_text("❌ Только администратор может очищать отзывы.")
		return
	
	args_text = (update.message.text or "").strip()
	parts = args_text.split(maxsplit=1)
	if len(parts) < 2:
		await update.message.reply_text("❌ Формат: /clear_reviews Название ресторана\nПример: /clear_reviews Twins Garden")
		return
	
	restaurant_name = parts[1].strip()
	logger.info(f"Clearing reviews for restaurant: '{restaurant_name}'")
	deleted_count = clear_reviews_by_restaurant_name(restaurant_name)
	
	if deleted_count > 0:
		await update.message.reply_text(f"✅ Удалено отзывов: {deleted_count} для ресторана '{restaurant_name}'")
		logger.info(f"Admin {user.id} cleared {deleted_count} reviews for '{restaurant_name}'")
	else:
		await update.message.reply_text(f"❌ Ресторан '{restaurant_name}' не найден или отзывов нет")


async def on_reviews_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    data = query.data or ""
    if not data.startswith("reviews:"):
        await query.answer()
        return

    parts = data.split(":", 2)
    if len(parts) != 3:
        await query.answer()
        return

    _, event_id_str, mode = parts
    try:
        event_id = int(event_id_str)
    except ValueError:
        await query.answer()
        return

    event = get_event_with_details(event_id)
    if not event:
        await query.answer("Событие не найдено", show_alert=True)
        return

    reviews = get_reviews_for_event(event_id)
    show_reviews = mode == "show"
    text = _format_event_text(event, reviews, include_reviews=show_reviews)
    keyboard = _build_reviews_keyboard(event_id, show_reviews=show_reviews)

    try:
        await context.bot.edit_message_text(
            chat_id=query.message.chat_id,
            message_id=query.message.message_id,
            text=text,
            parse_mode=constants.ParseMode.HTML,
            reply_markup=keyboard,
        )
    except Exception as e:
        logger.error(f"Failed to toggle reviews for event {event_id}: {e}")
    await query.answer()


## Удалён reviews_ команда: используем только toggler кнопки


async def menu_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	# нижняя клавиатура оставлена для удобства
	keyboard = ReplyKeyboardMarkup(
		[
			[KeyboardButton("🎲 Случайный ресторан")],
			[KeyboardButton("📊 Статистика")],
			[KeyboardButton("Предстоящие события")],
		],
		resize_keyboard=True,
		one_time_keyboard=False,
	)
	inline = InlineKeyboardMarkup(
		[
			[
				InlineKeyboardButton("🎲 Случайный ресторан", callback_data="menu:random"),
			],
			[
				InlineKeyboardButton("📊 Статистика", callback_data="menu:stats"),
			],
			[
				InlineKeyboardButton("Предстоящие события", callback_data="menu:upcoming"),
			],
		]
	)
	await update.message.reply_text("Выберите действие:", reply_markup=keyboard)
	await update.message.reply_text("Быстрые действия:", reply_markup=inline)


async def on_menu_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	text = (update.message.text or "").strip().lower()
	# алиасы без слеша (работают в группах при отключённом privacy у бота)
	if text in ("start", "старт", "help", "помощь"):
		await start(update, context)
		return
	if text in ("menu", "меню"):
		await menu_cmd(update, context)
		return
	if text in ("предстоящие события", "upcoming", "upcomming"):
		await upcoming_cmd(update, context)
		return
	# ТОЛЬКО точные пункты меню
	if text in ("🎲 случайный ресторан", "случайный ресторан"):
		await random_restaurant(update, context)
		return
	if text in ("📊 статистика", "статистика"):
		await stats_cmd(update, context)
		return
	# убираем обработку "установить время" кнопкой


async def upcoming_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	"""Показывает предстоящие события."""
	await _send_upcoming_for_chat(context, update.effective_chat.id)


async def on_menu_click(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    data = query.data or ""
    chat_id = query.message.chat_id if query.message else update.effective_chat.id
    if data == "menu:random":
        await _send_random_for_chat(context, chat_id)
        await query.answer()
        return
    if data == "menu:stats":
        await _send_stats_for_chat(context, chat_id)
        await query.answer()
        return
    if data == "menu:upcoming":
        await _send_upcoming_for_chat(context, chat_id)
        await query.answer()
        return
    await query.answer()


async def _startup(application: Application) -> None:
	# создаём схемы БД
	init_db()
	migrate_schema()
	await _ensure_initial_import(application)
	# убираем демо-данные (по просьбе) и не создаём новые
	cleanup_demo_data()
	# настроим список команд
	await application.bot.set_my_commands([
		BotCommand("menu", "Открыть меню"),
		BotCommand("random_restaurant", "Выбрать случайный ресторан"),
		BotCommand("stats", "Показать статистику"),
		BotCommand("upcoming", "Предстоящие события"),
		BotCommand("cancel_event", "Отменить текущее событие (только админы)"),
		BotCommand("clear_reviews", "Очистить отзывы ресторана (только админы)"),
	])
	# восстановим отложенные задачи из БД
	now = datetime.now(timezone.utc)
	restored_reminders = 0
	for ev in get_due_reminders(now + timedelta(days=365)):
		if ev["reminder_at_utc"] and int(ev["reminder_sent"]) == 0:
			try:
				dt = datetime.fromisoformat(ev["reminder_at_utc"]).replace(tzinfo=timezone.utc)
				when = max(dt, now)
				ev_id = int(ev["id"])
				for job in application.job_queue.get_jobs_by_name(f"reminder_{ev_id}"):
					job.schedule_removal()
				application.job_queue.run_once(send_reminder_job, when=when, data={"event_id": ev_id}, name=f"reminder_{ev_id}")
				restored_reminders += 1
			except Exception as e:
				logger.error(f"Failed to restore reminder for event {ev['id']}: {e}")
	logger.info(f"Restored {restored_reminders} reminders")
	
	restored_feedback = 0
	for ev in get_all_feedback_to_schedule():
		try:
			ev_id = int(ev["id"])
			dt = datetime.fromisoformat(ev["reminder_at_utc"]).replace(tzinfo=timezone.utc) + timedelta(hours=3)
			when = max(dt, now)
			for job in application.job_queue.get_jobs_by_name(f"feedback_{ev_id}"):
				job.schedule_removal()
			application.job_queue.run_once(send_feedback_prompt_job, when=when, data={"event_id": ev_id}, name=f"feedback_{ev_id}")
			# ежедневные персональные напоминания
			dt_remind = datetime.fromisoformat(ev["reminder_at_utc"]).replace(tzinfo=timezone.utc) + timedelta(days=1)
			when_remind = max(dt_remind, now)
			for job in application.job_queue.get_jobs_by_name(f"daily_reviews_{ev_id}"):
				job.schedule_removal()
			application.job_queue.run_repeating(
				remind_pending_reviews_job,
				interval=timedelta(days=1),
				first=when_remind,
				data={"event_id": ev_id},
				name=f"daily_reviews_{ev_id}",
			)
			restored_feedback += 1
		except Exception as e:
			logger.error(f"Failed to restore feedback job for event {ev['id']}: {e}")
	logger.info(f"Restored {restored_feedback} feedback jobs")


def build_app() -> Application:
	if not BOT_TOKEN:
		raise RuntimeError("Не задан BOT_TOKEN (переменная окружения)")
	application = ApplicationBuilder().token(BOT_TOKEN).post_init(_startup).build()
	application.bot_data["timezone"] = TIMEZONE
	application.add_handler(CommandHandler("start", start))
	application.add_handler(CommandHandler("menu", menu_cmd))
	application.add_handler(CommandHandler("random_restaurant", random_restaurant))
	application.add_handler(CommandHandler("set_reminder", set_reminder_cmd))
	application.add_handler(CommandHandler("stats", stats_cmd))
	application.add_handler(CommandHandler("upcoming", upcoming_cmd))
	application.add_handler(CommandHandler("cancel_event", cancel_event_cmd))
	application.add_handler(CommandHandler("clear_reviews", clear_reviews_cmd))
	application.add_handler(CallbackQueryHandler(on_join_toggle, pattern=r"^join:"))
	application.add_handler(CallbackQueryHandler(on_cancel_trip, pattern=r"^cancel:"))
	application.add_handler(CallbackQueryHandler(on_reset_event, pattern=r"^reset:"))
	application.add_handler(CallbackQueryHandler(on_reviews_toggle, pattern=r"^reviews:"))
	application.add_handler(CallbackQueryHandler(on_menu_click, pattern=r"^menu:"))
	application.add_handler(MessageHandler(filters.Document.ALL, on_document))
	# свободный ввод даты/времени DD.MM.YYYY HH:MM (более гибкий regex: поддержка : . - разделителей времени)
	application.add_handler(MessageHandler(filters.Regex(r"^\s*\d{1,2}\.\d{1,2}\.\d{4}\s+\d{1,2}[:\.\-]\d{2}\s*$") & ~filters.REPLY, on_freeform_datetime))
	# reviews_ команда удалена — используем toggler
	application.add_handler(MessageHandler(filters.TEXT & ~filters.REPLY, on_menu_text))
	application.add_handler(MessageHandler(filters.TEXT & filters.REPLY, on_text_review))
	return application


def main() -> None:
	application = build_app()
	# Глобальный error handler
	async def _on_error(update: object, context_: ContextTypes.DEFAULT_TYPE) -> None:
		logger.exception("Unhandled error", exc_info=context_.error)
	application.add_error_handler(_on_error)
	if WEBHOOK_BASE_URL:
		# webhook режим
		url_path = WEBHOOK_PATH.rstrip("/") + "/" + (os.getenv("WEBHOOK_SECRET", "tg") )
		webhook_url = WEBHOOK_BASE_URL.rstrip("/") + url_path
		application.run_webhook(
			listen="0.0.0.0",
			port=PORT,
			url_path=url_path,
			webhook_url=webhook_url,
		)
	else:
		# локальный режим — long polling
		application.run_polling()


if __name__ == "__main__":
	main()
