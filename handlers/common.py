from aiogram import Router, F
from aiogram.types import Message
from database import Session, User

router = Router()

@router.message(F.text == "/start")
async def cmd_start(message: Message):
    session = Session()
    user = session.query(User).filter(User.tg_id == message.from_user.id).first()
    if not user:
        new_user = User(
            tg_id=message.from_user.id,
            username=message.from_user.username.lower() if message.from_user.username else None,
            full_name=message.from_user.full_name
        )
        session.add(new_user)
        session.commit()
    session.close()

    await message.answer(
        f"👋 Привет! Я бот-напоминалка о твоих обязанностях.\n\n"
        f"Ты автоматически зарегистрирован. Админ скоро загрузит расписание.\n\n"
        f"🆔 Твой Telegram ID: <code>{message.from_user.id}</code>\n"
        f"(сообщи его администратору если у тебя нет username)\n\n"
        f"📋 /mytasks — все предстоящие задания\n"
        f"📅 /nexttask — задания только на ближайшую встречу",
        parse_mode="HTML"
    )
