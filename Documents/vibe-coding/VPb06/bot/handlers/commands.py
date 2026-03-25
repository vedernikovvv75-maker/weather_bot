from __future__ import annotations

import asyncio

from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, Message

from bot.config import DATABASE_PATH
from bot.db import add_task, get_tasks
from bot.states import AddStates
from bot.utils.csv_export import build_tasks_csv


router = Router()


@router.message(CommandStart())
async def command_start(message: Message) -> None:
    """
    Приветствует пользователя и кратко объясняет доступные команды.
    """

    await message.answer(
        "Привет! Я бот для задач.\n\n"
        "Команды:\n"
        "/add — добавить задачу\n"
        "/list — показать список\n"
        "/list_csv — выгрузить в CSV"
    )


@router.message(Command("add"))
async def command_add(message: Message, state: FSMContext) -> None:
    """
    Начинает сценарий добавления задачи:
    1) переключаем FSM в состояние ожидания текста
    2) просим пользователя отправить текст задачи отдельным сообщением
    """

    await state.set_state(AddStates.waiting_text)
    await message.answer("Отправьте текст задачи. Пример: 'Купить молоко'.")


@router.message(AddStates.waiting_text)
async def add_waiting_text(message: Message, state: FSMContext) -> None:
    """
    Обрабатывает следующее сообщение после `/add`:
    - сохраняет задачу в SQLite
    - очищает FSM state
    """

    if not message.text:
        await message.answer("Нужен текст задачи. Повторите команду /add и отправьте текст.")
        return

    # Если пользователь вдруг отправил новую команду вместо текста — попросим текст.
    if message.text.strip().startswith("/"):
        await message.answer("Сначала отправьте текст задачи. Команда /add уже активирована.")
        return

    task_text = message.text.strip()
    user_id = str(message.from_user.id)  # user=id — нам достаточно для 'общего списка'

    # SQLite — синхронная библиотека, чтобы не блокировать event loop,
    # запускаем её в отдельном потоке.
    task_id = await asyncio.to_thread(add_task, task_text, user_id, DATABASE_PATH)

    await state.clear()
    await message.answer(f"Добавил задачу #{task_id}: {task_text}")


@router.message(Command("list"))
async def command_list(message: Message) -> None:
    """
    Выводит все задачи, отсортированные по времени добавления.
    """

    tasks = await asyncio.to_thread(get_tasks, DATABASE_PATH)

    if not tasks:
        await message.answer("Пока нет задач. Добавьте задачу командой /add.")
        return

    lines: list[str] = []
    for i, task in enumerate(tasks, start=1):
        # task имеет поля: id, text, user, created_at
        lines.append(
            f"{i}. [{task['id']}] {task['text']} (user: {task['user']}, {task['created_at']})"
        )

    await message.answer("Список задач:\n" + "\n".join(lines))


@router.message(Command("list_csv"))
async def command_list_csv(message: Message) -> None:
    """
    Генерирует CSV-файл с задачами и отправляет пользователю как документ.
    """

    tasks = await asyncio.to_thread(get_tasks, DATABASE_PATH)

    csv_bytes = build_tasks_csv(tasks)
    csv_file = BufferedInputFile(csv_bytes, filename="tasks.csv")

    await message.answer_document(
        document=csv_file,
        caption="Вот CSV с задачами. Откройте его в Excel или LibreOffice.",
    )

