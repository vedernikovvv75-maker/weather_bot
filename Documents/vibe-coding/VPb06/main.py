import asyncio

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from bot.config import BOT_TOKEN, DATABASE_PATH
from bot.db import init_db
from bot.handlers.commands import router as commands_router


async def main() -> None:
    """
    Точка входа в приложение: создаём бота, подключаем роутеры, и запускаем polling.
    """
    bot = Bot(token=BOT_TOKEN)

    # Память для FSM (двухшаговые команды). Для минимального проекта хватает MemoryStorage.
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(commands_router)

    # Создаём таблицы в SQLite при старте.
    await asyncio.to_thread(init_db, DATABASE_PATH)

    # Запуск обработчиков сообщений.
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())

