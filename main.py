import logging
import random
import asyncio
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types
from aiogram.contrib.middlewares.logging import LoggingMiddleware
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.executor import start_webhook
import os

# --- НАСТРОЙКИ ---
TOKEN = os.getenv("BOT_TOKEN", "8432200353:AAEE-YdcvRKTnU0FbAcASbNiFIVdbFR_bC8")
CHANNEL_USERNAME = "@celebrityfunfacts"
CHANNEL_ID = "@celebrityfunfacts"

# Настройка логирования
logging.basicConfig(level=logging.INFO)

# Создаем объекты бота и диспетчера
bot = Bot(token=TOKEN)
dp = Dispatcher(bot)
dp.middleware.setup(LoggingMiddleware())

# Словарь для хранения активных задач пользователей
user_tasks = {}

# Словарь с интервалами для кнопок
INTERVALS = {
    "1h": 1,
    "5h": 5,
    "10h": 10,
    "15h": 15,
    "20h": 20,
    "24h": 24
}

# Список фраз для напоминаний
REMINDER_PHRASES = [
    "🧘 Выпрями спину!",
    "⚠️ Не горбись!",
    "🦐 Напоминаю, друг, ты прям креветка!",
    "📏 Сядь ровно, осанка — это важно!",
    "🏛️ Расправь плечи, как греческая колонна!",
    "💪 Держи спину, чемпион!",
    "🪑 Отлипни от стола, выпрямись!",
    "🎗️ Не сутулься, побереги позвоночник!"
]

# Функция проверки подписки
async def check_subscription(user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        if member['status'] in ['member', 'administrator', 'creator']:
            return True
        else:
            return False
    except Exception as e:
        print(f"Ошибка проверки подписки для {user_id}: {e}")
        return False

@dp.message_handler(commands=['start'])
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    user_name = message.from_user.first_name

    is_subscribed = await check_subscription(user_id)

    if is_subscribed:
        await show_timer_menu(message)
    else:
        keyboard = InlineKeyboardMarkup(row_width=1)
        keyboard.add(
            InlineKeyboardButton(text="📢 Подписаться на канал", url=f"https://t.me/celebrityfunfacts"),
            InlineKeyboardButton(text="✅ Я подписался", callback_data="check_sub")
        )
        await message.answer(
            f"Привет, {user_name}!\n\n"
            f"Для использования бота нужно подписаться на наш канал: {CHANNEL_USERNAME}\n\n"
            f"👉 После подписки нажми кнопку 'Я подписался'.",
            reply_markup=keyboard
        )

@dp.callback_query_handler(lambda c: c.data == 'check_sub')
async def process_sub_check(callback_query: types.CallbackQuery):
    user_id = callback_query.from_user.id
    is_subscribed = await check_subscription(user_id)

    if is_subscribed:
        await bot.edit_message_text(
            "✅ Спасибо! Подписка подтверждена. Выбирай интервал:",
            chat_id=callback_query.message.chat.id,
            message_id=callback_query.message.message_id
        )
        await show_timer_menu(callback_query.message)
    else:
        await bot.answer_callback_query(
            callback_query.id,
            text="❌ Вы еще не подписались на канал!",
            show_alert=True
        )

async def show_timer_menu(message: types.Message):
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton(text="1 час", callback_data="set_1h"),
        InlineKeyboardButton(text="5 часов", callback_data="set_5h"),
        InlineKeyboardButton(text="10 часов", callback_data="set_10h"),
        InlineKeyboardButton(text="15 часов", callback_data="set_15h"),
        InlineKeyboardButton(text="20 часов", callback_data="set_20h"),
        InlineKeyboardButton(text="24 часа", callback_data="set_24h"),
        InlineKeyboardButton(text="❌ Выключить напоминания", callback_data="stop_reminders")
    )
    await message.answer("⏰ Напомнить мне выпрямить спину каждые:", reply_markup=keyboard)

@dp.callback_query_handler(lambda c: c.data.startswith('set_'))
async def set_reminder(callback_query: types.CallbackQuery):
    user_id = callback_query.from_user.id
    interval_key = callback_query.data
    interval_hours = INTERVALS[interval_key.replace("set_", "")]

    next_time = datetime.now() + timedelta(hours=interval_hours)

    user_tasks[user_id] = {
        "chat_id": callback_query.message.chat.id,
        "next_time": next_time,
        "interval_hours": interval_hours
    }

    await bot.edit_message_text(
        f"✅ Напоминание установлено!\n"
        f"Я буду напоминать тебе каждые {interval_hours} час(ов).\n"
        f"Первое напоминание придет примерно в {next_time.strftime('%H:%M %d.%m')}.",
        chat_id=callback_query.message.chat.id,
        message_id=callback_query.message.message_id
    )
    await bot.answer_callback_query(callback_query.id)

@dp.callback_query_handler(lambda c: c.data == 'stop_reminders')
async def stop_reminders(callback_query: types.CallbackQuery):
    user_id = callback_query.from_user.id
    if user_id in user_tasks:
        del user_tasks[user_id]
        text = "🔕 Напоминания отключены. Чтобы включить заново, нажми /start"
    else:
        text = "🤷 У тебя не было активных напоминаний."

    await bot.edit_message_text(
        text,
        chat_id=callback_query.message.chat.id,
        message_id=callback_query.message.message_id
    )
    await bot.answer_callback_query(callback_query.id)

# --- Фоновая задача для рассылки напоминаний ---
async def reminder_scheduler():
    while True:
        now = datetime.now()
        to_remove = []

        for user_id, task_info in user_tasks.items():
            if now >= task_info["next_time"]:
                try:
                    phrase = random.choice(REMINDER_PHRASES)
                    await bot.send_message(chat_id=task_info["chat_id"], text=phrase)

                    new_next_time = now + timedelta(hours=task_info["interval_hours"])
                    user_tasks[user_id]["next_time"] = new_next_time
                    print(f"Отправлено напоминание пользователю {user_id}")

                except Exception as e:
                    print(f"Ошибка отправки пользователю {user_id}: {e}")
                    to_remove.append(user_id)

        for user_id in to_remove:
            if user_id in user_tasks:
                del user_tasks[user_id]

        await asyncio.sleep(30)

# --- Веб-сервер для Render ---
async def on_startup(dp):
    await bot.set_webhook(WEBHOOK_URL)
    asyncio.create_task(reminder_scheduler())

async def on_shutdown(dp):
    await bot.delete_webhook()

# Настройки вебхука
WEBHOOK_HOST = os.getenv("RENDER_EXTERNAL_URL", "https://spine-bot.onrender.com")
WEBHOOK_PATH = "/webhook"
WEBHOOK_URL = f"{WEBHOOK_HOST}{WEBHOOK_PATH}"

WEBAPP_HOST = "0.0.0.0"
WEBAPP_PORT = int(os.getenv("PORT", 10000))

if __name__ == "__main__":
    start_webhook(
        dispatcher=dp,
        webhook_path=WEBHOOK_PATH,
        on_startup=on_startup,
        on_shutdown=on_shutdown,
        skip_updates=True,
        host=WEBAPP_HOST,
        port=WEBAPP_PORT
    )
