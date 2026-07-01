import asyncio
import os
from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand, BotCommandScopeDefault, BotCommandScopeChat
from config import BOT_TOKEN, ADMIN_IDS
from database import init_db
from handlers.common import router as common_router
from handlers.admin import router as admin_router, scheduler, schedule_all_reminders, schedule_all_duties
from handlers.user import router as user_router
from loguru import logger

USER_COMMANDS = [
    BotCommand(command="start", description="Запустить бота"),
    BotCommand(command="mytasks", description="Все мои предстоящие задания"),
    BotCommand(command="nexttask", description="Задания на ближайшую встречу"),
]

ADMIN_COMMANDS = [
    BotCommand(command="start", description="Запустить бота"),
    BotCommand(command="mytasks", description="Все мои предстоящие задания"),
    BotCommand(command="nexttask", description="Задания на ближайшую встречу"),
    BotCommand(command="upload_performance", description="Загрузить график выступлений (Excel)"),
    BotCommand(command="upload_translation", description="Загрузить график заданий (Excel)"),
    BotCommand(command="upload_duty", description="Загрузить график дежурств группы (Excel)"),
    BotCommand(command="list_users", description="Список зарегистрированных участников"),
    BotCommand(command="admin_tasks", description="Все предстоящие задания участников"),
    BotCommand(command="delete_tasks", description="Очистить все задания из базы"),
    BotCommand(command="cancel", description="Отменить текущее действие"),
]

async def setup_commands(bot: Bot):
    await bot.set_my_commands(USER_COMMANDS, scope=BotCommandScopeDefault())
    for admin_id in ADMIN_IDS:
        try:
            await bot.set_my_commands(
                ADMIN_COMMANDS,
                scope=BotCommandScopeChat(chat_id=admin_id)
            )
        except Exception as e:
            logger.warning(f"Не удалось установить команды для админа {admin_id}: {e}")
    logger.info("📋 Меню команд установлено")

async def health_handler(request):
    return web.Response(text="OK")

async def run_health_server():
    app = web.Application()
    app.router.add_get("/", health_handler)
    app.router.add_get("/health", health_handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", 8080)
    await site.start()
    logger.info("🌐 Health-сервер запущен на порту 8080")

async def main():
    init_db()
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())

    dp.include_router(common_router)
    dp.include_router(admin_router)
    dp.include_router(user_router)

    if not scheduler.running:
        scheduler.start()
        logger.info("Планировщик напоминаний запущен")

    await setup_commands(bot)
    await schedule_all_reminders(bot)
    await schedule_all_duties(bot)
    logger.info("📅 Напоминания из БД перепланированы")

    await run_health_server()

    logger.info("✅ Бот успешно запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
