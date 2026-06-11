from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from config import ADMIN_IDS
from utils.excel_parser import parse_and_save_excel_from_bytes   # ← исправленный импорт
from database import Session, Task, User
from datetime import datetime, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import os
from loguru import logger

router = Router()
scheduler = AsyncIOScheduler(timezone="Asia/Aqtobe")

class UploadState(StatesGroup):
    waiting_for_file = State()

class DeleteConfirmState(StatesGroup):
    waiting_confirm = State()

@router.message(Command("upload_performance"))
async def cmd_upload_performance(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("⛔ Только админ может загружать файлы")
        return
    await state.update_data(task_type="выступление")
    await state.set_state(UploadState.waiting_for_file)
    await message.answer("📤 Отправь мне файл Excel с **выступлениями**")

@router.message(Command("upload_translation"))
async def cmd_upload_translation(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("⛔ Только админ может загружать файлы")
        return
    await state.update_data(task_type="перевод")
    await state.set_state(UploadState.waiting_for_file)
    await message.answer("📤 Отправь мне файл Excel с **переводами**")

@router.message(UploadState.waiting_for_file, F.document)
async def handle_document(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    task_type = data.get("task_type", "задание")
    
    await message.answer("⏳ Скачиваю файл...")

    try:
        # Надёжный способ скачивания в aiogram 3.x
        file_info = await bot.get_file(message.document.file_id)
        file_path = f"temp_{task_type}_{message.document.file_name or 'file.xlsx'}"
        
        await bot.download_file(file_info.file_path, destination=file_path)

        await message.answer("✅ Файл скачан. Обрабатываю Excel...")

        # Используем новую функцию парсера
        await parse_and_save_excel_from_bytes(file_path, task_type, bot, message.from_user.id)

        await schedule_all_reminders(bot)

        await message.answer("🎉 Задания успешно загружены и напоминания запланированы!")

    except Exception as e:
        logger.error(f"Ошибка при обработке файла: {e}")
        await message.answer(f"❌ Ошибка при обработке файла:\n{str(e)}")
    finally:
        if 'file_path' in locals() and os.path.exists(file_path):
            try:
                os.remove(file_path)
            except:
                pass

    await state.clear()

async def schedule_all_reminders(bot: Bot):
    import asyncio
    session = Session()
    tasks = session.query(Task).filter(Task.due_date > datetime.now()).all()
    session.close()

    now = datetime.now()

    for task in tasks:
        task_type_text = "выступление" if task.task_type == "выступление" else "перевод"

        due_str = task.due_date.strftime('%d.%m.%Y')
        late_text = f"🔔 У тебя предстоит {task_type_text}:\n{task.description}\nДата: {due_str}"

        reminders = [
            (task.reminder_sent_14, task.due_date - timedelta(days=14),
             f"🔔 Через 2 недели у тебя {task_type_text}:\n{task.description}\nДата: {due_str}",
             'reminder_sent_14'),
            (task.reminder_sent_7, task.due_date - timedelta(days=7),
             f"🔔 Через 1 неделю у тебя {task_type_text}:\n{task.description}\nДата: {due_str}",
             'reminder_sent_7'),
            (task.reminder_sent_1, task.due_date - timedelta(days=1),
             f"🔔 Завтра у тебя {task_type_text}:\n{task.description}\nДата: {due_str}",
             'reminder_sent_1'),
        ]

        for already_sent, run_date, scheduled_text, flag in reminders:
            if already_sent:
                continue
            if run_date > now:
                # Запланировать на будущее — текст с точным сроком
                scheduler.add_job(
                    send_reminder_and_mark, 'date', run_date=run_date,
                    misfire_grace_time=3600,
                    args=[bot, task.id, task.user_tg_id, scheduled_text, flag])
            else:
                # Время уже прошло — отправить сразу, без упоминания срока
                asyncio.create_task(send_reminder_and_mark(bot, task.id, task.user_tg_id, late_text, flag))

async def send_reminder_and_mark(bot: Bot, task_id: int, user_tg_id: int, text: str, flag: str):
    try:
        await bot.send_message(user_tg_id, text)
        logger.info(f"Напоминание отправлено пользователю {user_tg_id}, задание #{task_id}, флаг {flag}")
    except Exception as e:
        logger.error(f"Не удалось отправить напоминание {user_tg_id}: {e}")
        return
    # Помечаем флаг в БД чтобы не отправить повторно
    try:
        session = Session()
        task = session.get(Task, task_id)
        if task:
            setattr(task, flag, True)
            session.commit()
        session.close()
    except Exception as e:
        logger.error(f"Не удалось обновить флаг {flag} для задания #{task_id}: {e}")


@router.message(Command("delete_tasks"))
async def cmd_delete_tasks(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("⛔ Только для администраторов")
        return
    await state.set_state(DeleteConfirmState.waiting_confirm)
    await message.answer(
        "⚠️ Ты собираешься удалить *все* задания из базы.\n\n"
        "Напиши *УДАЛИТЬ* для подтверждения или /cancel для отмены.",
        parse_mode="Markdown"
    )


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext):
    current = await state.get_state()
    if current:
        await state.clear()
        await message.answer("✅ Действие отменено.")


@router.message(DeleteConfirmState.waiting_confirm)
async def handle_delete_confirm(message: Message, state: FSMContext):
    if message.text and message.text.strip().upper() == "УДАЛИТЬ":
        session = Session()
        deleted = session.query(Task).delete()
        session.commit()
        session.close()
        await state.clear()
        await message.answer(f"🗑 Удалено {deleted} заданий. База очищена.")
    else:
        await message.answer("❌ Не подтверждено. Напиши *УДАЛИТЬ* или /cancel.", parse_mode="Markdown")


@router.message(Command("list_users"))
async def cmd_list_users(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("⛔ Только для администраторов")
        return

    session = Session()
    users = session.query(User).order_by(User.full_name).all()
    session.close()

    if not users:
        await message.answer("📭 Нет зарегистрированных пользователей.")
        return

    lines = [f"👥 *Зарегистрированные участники* ({len(users)} чел.):\n"]
    for i, user in enumerate(users, 1):
        username_str = f"@{user.username}" if user.username else "нет username"
        name_str = user.full_name or "—"
        lines.append(f"{i}. {name_str} — {username_str}\n   `ID: {user.tg_id}`")

    await message.answer("\n".join(lines), parse_mode="Markdown")


@router.message(Command("admin_tasks"))
async def cmd_admin_tasks(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("⛔ Только для администраторов")
        return

    session = Session()
    tasks = (
        session.query(Task)
        .filter(Task.due_date > datetime.now())
        .order_by(Task.due_date)
        .all()
    )
    users = {u.tg_id: u for u in session.query(User).all()}
    session.close()

    if not tasks:
        await message.answer("📭 Нет предстоящих заданий.")
        return

    now = datetime.now()
    # Группируем задания по пользователю
    by_user: dict = {}
    for task in tasks:
        by_user.setdefault(task.user_tg_id, []).append(task)

    lines = [f"📋 *Все предстоящие задания* ({len(tasks)} шт.):\n"]

    for tg_id, user_tasks in by_user.items():
        user = users.get(tg_id)
        if user and user.full_name:
            user_label = user.full_name
        elif user and user.username:
            user_label = f"@{user.username}"
        else:
            user_label = f"ID {tg_id}"

        lines.append(f"👤 *{user_label}*")

        for task in user_tasks:
            days_left = (task.due_date - now).days
            task_type_emoji = "🎤" if task.task_type == "выступление" else "📝"

            if days_left <= 1:
                urgency = "🔴"
            elif days_left <= 7:
                urgency = "🟠"
            elif days_left <= 14:
                urgency = "🟡"
            else:
                urgency = "🟢"

            # Статус уведомлений
            sent_flags = []
            if task.reminder_sent_14:
                sent_flags.append("14д✓")
            if task.reminder_sent_7:
                sent_flags.append("7д✓")
            if task.reminder_sent_1:
                sent_flags.append("1д✓")
            sent_str = f" `[{', '.join(sent_flags)}]`" if sent_flags else ""

            lines.append(
                f"  {task_type_emoji} {task.description} — "
                f"{task.due_date.strftime('%d.%m.%Y')} {urgency} {days_left}дн.{sent_str}"
            )

        lines.append("")

    # Telegram ограничивает сообщение ~4096 символов — разбиваем если нужно
    text = "\n".join(lines)
    if len(text) > 4000:
        chunks = []
        chunk = ""
        for line in lines:
            if len(chunk) + len(line) + 1 > 4000:
                chunks.append(chunk)
                chunk = line + "\n"
            else:
                chunk += line + "\n"
        if chunk:
            chunks.append(chunk)
        for chunk in chunks:
            await message.answer(chunk, parse_mode="Markdown")
    else:
        await message.answer(text, parse_mode="Markdown")