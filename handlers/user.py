from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from database import Session, Task
from datetime import datetime

router = Router()


@router.message(Command("mytasks"))
async def cmd_mytasks(message: Message):
    session = Session()
    tasks = (
        session.query(Task)
        .filter(Task.user_tg_id == message.from_user.id, Task.due_date > datetime.now())
        .order_by(Task.due_date)
        .all()
    )
    session.close()

    if not tasks:
        await message.answer("📭 У тебя нет предстоящих заданий.")
        return

    now = datetime.now()
    lines = ["📋 *Твои предстоящие задания:*\n"]

    for task in tasks:
        days_left = (task.due_date - now).days
        task_type_emoji = "🎤" if task.task_type == "выступление" else "📝"
        task_type_label = "Выступление" if task.task_type == "выступление" else "Задание"
        time_str = f" в {task.due_date.strftime('%H:%M')}" if (task.due_date.hour or task.due_date.minute) else ""

        if days_left == 0:
            days_str = "⚠️ *сегодня!*"
        elif days_left == 1:
            days_str = "⚠️ *завтра!*"
        elif days_left <= 7:
            days_str = f"🔴 через {days_left} дн."
        elif days_left <= 14:
            days_str = f"🟡 через {days_left} дн."
        else:
            days_str = f"🟢 через {days_left} дн."

        lines.append(
            f"{task_type_emoji} *{task_type_label}*\n"
            f"   📌 {task.description}\n"
            f"   📅 {task.due_date.strftime('%d.%m.%Y')}{time_str} — {days_str}\n"
        )

    await message.answer("\n".join(lines), parse_mode="Markdown")


@router.message(Command("nexttask"))
async def cmd_nexttask(message: Message):
    session = Session()
    tasks = (
        session.query(Task)
        .filter(Task.user_tg_id == message.from_user.id, Task.due_date > datetime.now())
        .order_by(Task.due_date)
        .all()
    )
    session.close()

    if not tasks:
        await message.answer("📭 У тебя нет предстоящих заданий.")
        return

    # Находим дату ближайшей встречи (только дата, без времени)
    nearest_date = tasks[0].due_date.date()

    # Все задания на ближайшую встречу
    nearest_tasks = [t for t in tasks if t.due_date.date() == nearest_date]

    now = datetime.now()
    days_left = (tasks[0].due_date - now).days

    if days_left == 0:
        days_str = "⚠️ *сегодня!*"
    elif days_left == 1:
        days_str = "⚠️ *завтра!*"
    else:
        days_str = f"через {days_left} дн."

    lines = [f"📅 *Задания на ближайшую встречу* ({nearest_date.strftime('%d.%m.%Y')}, {days_str}):\n"]

    for task in nearest_tasks:
        task_type_emoji = "🎤" if task.task_type == "выступление" else "📝"
        task_type_label = "Выступление" if task.task_type == "выступление" else "Задание"
        time_str = f" в {task.due_date.strftime('%H:%M')}" if (task.due_date.hour or task.due_date.minute) else ""

        lines.append(
            f"{task_type_emoji} *{task_type_label}*\n"
            f"   📌 {task.description}\n"
            f"   📅 {task.due_date.strftime('%d.%m.%Y')}{time_str}\n"
        )

    await message.answer("\n".join(lines), parse_mode="Markdown")
