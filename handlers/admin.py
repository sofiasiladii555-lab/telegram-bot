from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from config import ADMIN_IDS
from utils.excel_parser import parse_and_save_excel_from_bytes, parse_and_save_duty_excel
from database import Session, Task, Duty, User
from datetime import datetime, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import os
from loguru import logger

router = Router()
scheduler = AsyncIOScheduler(timezone="Asia/Aqtobe")

class UploadState(StatesGroup):
    waiting_for_file = State()

class UploadDutyState(StatesGroup):
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
    await message.answer("📤 Отправь мне файл Excel с **выступлениями**\n\nСтолбцы: Дата | Время | Telegram_ID | Telegram_Username | Full_Name | Задание\n_(Время и идентификаторы — необязательны, но хотя бы один из Telegram_Username / Full_Name нужен)_", parse_mode="Markdown")


@router.message(Command("upload_translation"))
async def cmd_upload_translation(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("⛔ Только админ может загружать файлы")
        return
    await state.update_data(task_type="задание")
    await state.set_state(UploadState.waiting_for_file)
    await message.answer("📤 Отправь мне файл Excel с **заданиями**\n\nСтолбцы: Дата | Время | Telegram_ID | Telegram_Username | Full_Name | Задание\n_(Время и идентификаторы — необязательны, но хотя бы один из Telegram_Username / Full_Name нужен)_", parse_mode="Markdown")


@router.message(Command("upload_duty"))
async def cmd_upload_duty(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("⛔ Только админ может загружать файлы")
        return
    await state.set_state(UploadDutyState.waiting_for_file)
    await message.answer(
        "📤 Отправь мне файл Excel с **графиком дежурств группы**\n\n"
        "Столбцы: Дата, Время\n"
        "Пример: 20.06.2026 | 10:00"
    )


@router.message(UploadState.waiting_for_file, F.document)
async def handle_document(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    task_type = data.get("task_type", "задание")

    await message.answer("⏳ Скачиваю файл...")

    try:
        file_info = await bot.get_file(message.document.file_id)
        file_path = f"temp_{task_type}_{message.document.file_name or 'file.xlsx'}"
        await bot.download_file(file_info.file_path, destination=file_path)
        await message.answer("✅ Файл скачан. Обрабатываю Excel...")
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


@router.message(UploadDutyState.waiting_for_file, F.document)
async def handle_duty_document(message: Message, state: FSMContext, bot: Bot):
    await message.answer("⏳ Скачиваю файл дежурств...")

    try:
        file_info = await bot.get_file(message.document.file_id)
        file_path = f"temp_duty_{message.document.file_name or 'duty.xlsx'}"
        await bot.download_file(file_info.file_path, destination=file_path)
        await message.answer("✅ Файл скачан. Обрабатываю Excel...")
        await parse_and_save_duty_excel(file_path, bot, message.from_user.id)
        await schedule_all_duties(bot)
        await message.answer("🎉 График дежурств загружен и напоминания запланированы!")
    except Exception as e:
        logger.error(f"Ошибка при обработке файла дежурств: {e}")
        await message.answer(f"❌ Ошибка:\n{str(e)}")
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
        due_str = task.due_date.strftime('%d.%m.%Y')
        due_time_str = task.due_date.strftime('%H:%M')
        has_time = task.due_date.hour != 0 or task.due_date.minute != 0

        late_text = f"У ТЕБЯ ПРЕДСТОИТ ЗАДАНИЕ:\n{task.description}\nДата: {due_str}"

        reminders = [
            (task.reminder_sent_14, task.due_date - timedelta(days=14),
             f"У ТЕБЯ ПРЕДСТОИТ ЗАДАНИЕ:\n{task.description}\nДата: {due_str}\n\nДо задания осталось 2 недели!",
             'reminder_sent_14'),
            (task.reminder_sent_7, task.due_date - timedelta(days=7),
             f"У ТЕБЯ ПРЕДСТОИТ ЗАДАНИЕ:\n{task.description}\nДата: {due_str}\n\nДо задания осталась 1 неделя!",
             'reminder_sent_7'),
            (task.reminder_sent_1, task.due_date - timedelta(days=1),
             f"У ТЕБЯ ПРЕДСТОИТ ЗАДАНИЕ:\n{task.description}\nДата: {due_str}\n\nЗадание уже завтра!",
             'reminder_sent_1'),
        ]

        if has_time:
            reminders.append((
                task.reminder_sent_2h,
                task.due_date - timedelta(hours=2),
                f"⏰ ЧЕРЕЗ 2 ЧАСА У ТЕБЯ ЗАДАНИЕ:\n{task.description}\nНачало в {due_time_str}",
                'reminder_sent_2h'
            ))

        for already_sent, run_date, scheduled_text, flag in reminders:
            if already_sent:
                continue
            if run_date > now:
                scheduler.add_job(
                    send_reminder_and_mark, 'date', run_date=run_date,
                    misfire_grace_time=3600,
                    args=[bot, task.id, task.user_tg_id, scheduled_text, flag])
            else:
                asyncio.create_task(send_reminder_and_mark(bot, task.id, task.user_tg_id, late_text, flag))


async def schedule_all_duties(bot: Bot):
    import asyncio
    session = Session()
    duties = session.query(Duty).filter(
        Duty.duty_date > datetime.now(),
        Duty.reminder_sent == False
    ).all()
    session.close()

    now = datetime.now()

    for duty in duties:
        run_date = duty.duty_date - timedelta(hours=2)
        due_str = duty.duty_date.strftime('%d.%m.%Y')
        due_time_str = duty.duty_date.strftime('%H:%M')
        text = (
            f"🧹 СЕГОДНЯ ДЕЖУРСТВО НАШЕЙ ГРУППЫ!\n"
            f"Встреча в {due_time_str} ({due_str})\n"
            f"Не забудьте про уборку после встречи!"
        )

        if run_date > now:
            scheduler.add_job(
                send_duty_reminder, 'date', run_date=run_date,
                misfire_grace_time=3600,
                args=[bot, duty.id, text])
        else:
            asyncio.create_task(send_duty_reminder(bot, duty.id, text))


async def send_reminder_and_mark(bot: Bot, task_id: int, user_tg_id: int, text: str, flag: str):
    try:
        await bot.send_message(user_tg_id, text)
        logger.info(f"Напоминание отправлено пользователю {user_tg_id}, задание #{task_id}, флаг {flag}")
    except Exception as e:
        logger.error(f"Не удалось отправить напоминание {user_tg_id}: {e}")
        return
    try:
        session = Session()
        task = session.get(Task, task_id)
        if task:
            setattr(task, flag, True)
            session.commit()
        session.close()
    except Exception as e:
        logger.error(f"Не удалось обновить флаг {flag} для задания #{task_id}: {e}")


async def send_duty_reminder(bot: Bot, duty_id: int, text: str):
    session = Session()
    users = session.query(User).all()
    session.close()

    for user in users:
        try:
            await bot.send_message(user.tg_id, text)
            logger.info(f"Напоминание о дежурстве отправлено пользователю {user.tg_id}")
        except Exception as e:
            logger.error(f"Не удалось отправить напоминание о дежурстве {user.tg_id}: {e}")

    try:
        session = Session()
        duty = session.get(Duty, duty_id)
        if duty:
            duty.reminder_sent = True
            session.commit()
        session.close()
    except Exception as e:
        logger.error(f"Не удалось обновить флаг дежурства #{duty_id}: {e}")


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
            task_type_label = "Выступление" if task.task_type == "выступление" else "Задание"

            if days_left <= 1:
                urgency = "🔴"
            elif days_left <= 7:
                urgency = "🟠"
            elif days_left <= 14:
                urgency = "🟡"
            else:
                urgency = "🟢"

            sent_flags = []
            if task.reminder_sent_14:
                sent_flags.append("14д✓")
            if task.reminder_sent_7:
                sent_flags.append("7д✓")
            if task.reminder_sent_1:
                sent_flags.append("1д✓")
            if task.reminder_sent_2h:
                sent_flags.append("2ч✓")
            sent_str = f" `[{', '.join(sent_flags)}]`" if sent_flags else ""

            time_str = f" в {task.due_date.strftime('%H:%M')}" if (task.due_date.hour or task.due_date.minute) else ""

            lines.append(
                f"  {task_type_emoji} *{task_type_label}:* {task.description} — "
                f"{task.due_date.strftime('%d.%m.%Y')}{time_str} {urgency} {days_left}дн.{sent_str}"
            )

        lines.append("")

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
