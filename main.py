import logging
import asyncio
import os
import requests
import time
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types
from aiogram.contrib.middlewares.logging import LoggingMiddleware
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiohttp import web
import uuid
import re

# --- НАСТРОЙКИ ---
TOKEN = os.getenv("BOT_TOKEN", "8786056296:AAEyss5XK9ebsXqYCQDH4jfk2XwHPIO8o_Q")

REQUIRED_CHANNELS = [
    {"username": "@anomaly_tg", "url": "https://t.me/anomaly_tg"},
    {"username": "@celebrityfunfacts", "url": "https://t.me/celebrityfunfacts"}
]

# === УБИЙЦА ПРОЦЕССОВ ===
print("💣 ЗАПУСКАЕМ УБИЙЦУ ПРОЦЕССОВ...")
try:
    requests.get(f"https://api.telegram.org/bot{TOKEN}/getUpdates?offset=-1")
    requests.get(f"https://api.telegram.org/bot{TOKEN}/deleteWebhook")
    print("🧹 Вебхуки и очередь сброшены")
except Exception as e:
    print(f"⚠️ Ошибка: {e}")
time.sleep(1)
print("💣 УБИЙЦА ЗАВЕРШИЛ РАБОТУ")
# =================================

logging.basicConfig(level=logging.INFO)

bot = Bot(token=TOKEN)
dp = Dispatcher(bot)
dp.middleware.setup(LoggingMiddleware())

# Хранилище напоминаний
user_reminders = {}
user_states = {}

STATE_WAITING_REMINDER_TEXT = "waiting_text"
STATE_WAITING_REMINDER_TIME = "waiting_time"

# === ПРОВЕРКА ПОДПИСКИ ===
async def check_subscription_all(user_id: int) -> tuple[bool, list]:
    not_subscribed = []
    for channel in REQUIRED_CHANNELS:
        try:
            member = await bot.get_chat_member(chat_id=channel["username"], user_id=user_id)
            if member['status'] not in ['member', 'administrator', 'creator']:
                not_subscribed.append(channel)
        except:
            not_subscribed.append(channel)
    return len(not_subscribed) == 0, not_subscribed

# === ПАРСИНГ ВРЕМЕНИ ===
def parse_time(time_str: str) -> datetime | None:
    """
    Понимает:
    - 15:30         -> сегодня в 15:30 (если прошло, то завтра)
    - завтра 10:00  -> завтра в 10:00
    - 15:30 12.03   -> 12 марта в 15:30
    ВСЕГДА считаем, что время введено по Москве (UTC+3)
    """
    now = datetime.now()
    time_str = time_str.lower().strip()

    # 1. Формат "завтра 10:00"
    if time_str.startswith("завтра"):
        match = re.search(r"(\d{1,2}):(\d{1,2})", time_str)
        if match:
            h, m = map(int, match.groups())
            target = now.replace(hour=h, minute=m, second=0, microsecond=0) + timedelta(days=1)
            return target

    # 2. Формат "15:30 12.03"
    if ":" in time_str and "." in time_str:
        match = re.search(r"(\d{1,2}):(\d{1,2})\s+(\d{1,2})\.(\d{1,2})", time_str)
        if match:
            h, m, d, mo = map(int, match.groups())
            year = now.year
            target = datetime(year, mo, d, h, m)
            if target < now:
                target = target.replace(year=year + 1)
            return target

    # 3. Просто "15:30"
    if ":" in time_str and len(time_str.split()) == 1:
        match = re.search(r"(\d{1,2}):(\d{1,2})", time_str)
        if match:
            h, m = map(int, match.groups())
            target = now.replace(hour=h, minute=m, second=0, microsecond=0)
            if target < now:
                target += timedelta(days=1)
            return target

    return None

# === /start ===
@dp.message_handler(commands=['start'])
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    ok, missing = await check_subscription_all(user_id)
    if ok:
        await show_main_menu(message)
    else:
        kb = InlineKeyboardMarkup(row_width=1)
        for ch in missing:
            kb.add(InlineKeyboardButton(text=f"📢 {ch['username']}", url=ch["url"]))
        kb.add(InlineKeyboardButton(text="✅ Я подписался", callback_data="check_sub"))
        await message.answer(
            f"📝 Привет! Подпишись на каналы:\n" + "\n".join(f"• {ch['username']}" for ch in missing),
            reply_markup=kb
        )

@dp.callback_query_handler(lambda c: c.data == 'check_sub')
async def process_sub_check(callback: types.CallbackQuery):
    ok, missing = await check_subscription_all(callback.from_user.id)
    if ok:
        await callback.message.edit_text("✅ Спасибо! Теперь можно создавать напоминания.")
        await show_main_menu(callback.message)
    else:
        kb = InlineKeyboardMarkup(row_width=1)
        for ch in missing:
            kb.add(InlineKeyboardButton(text=f"📢 {ch['username']}", url=ch["url"]))
        kb.add(InlineKeyboardButton(text="✅ Я подписался", callback_data="check_sub"))
        await callback.message.edit_text(
            "❌ Не хватает подписок:\n" + "\n".join(f"• {ch['username']}" for ch in missing),
            reply_markup=kb
        )
    await callback.answer()

# === ГЛАВНОЕ МЕНЮ ===
async def show_main_menu(message: types.Message):
    kb = InlineKeyboardMarkup(row_width=1).add(
        InlineKeyboardButton("➕ Создать напоминание", callback_data="create_reminder"),
        InlineKeyboardButton("📋 Мои напоминания", callback_data="list_reminders"),
        InlineKeyboardButton("❌ Удалить напоминание", callback_data="delete_reminder_menu")
    )
    await message.answer("📌 Что хочешь сделать?", reply_markup=kb)

# === СОЗДАНИЕ НАПОМИНАНИЯ ===
@dp.callback_query_handler(lambda c: c.data == 'create_reminder')
async def create_reminder_start(callback: types.CallbackQuery):
    user_states[callback.from_user.id] = {"state": STATE_WAITING_REMINDER_TEXT}
    await callback.message.edit_text("📝 Напиши текст напоминания")
    await callback.answer()

@dp.message_handler(lambda msg: user_states.get(msg.from_user.id, {}).get("state") == STATE_WAITING_REMINDER_TEXT)
async def process_reminder_text(message: types.Message):
    user_states[message.from_user.id] = {
        "state": STATE_WAITING_REMINDER_TIME,
        "text": message.text
    }
    await message.answer(
        "🕐 Теперь напиши время (по Москве):\n"
        "Примеры:\n"
        "• 15:30\n"
        "• завтра 10:00\n"
        "• 23:45 31.12"
    )

@dp.message_handler(lambda msg: user_states.get(msg.from_user.id, {}).get("state") == STATE_WAITING_REMINDER_TIME)
async def process_reminder_time(message: types.Message):
    user_id = message.from_user.id
    data = user_states.get(user_id)
    if not data or "text" not in data:
        user_states.pop(user_id, None)
        return

    reminder_time = parse_time(message.text)
    if not reminder_time:
        await message.answer("❌ Не понял время. Попробуй ещё раз.\nПример: 15:30")
        return

    # Сохраняем напоминание (время уже московское!)
    if user_id not in user_reminders:
        user_reminders[user_id] = {}
    rid = str(uuid.uuid4())[:6]
    user_reminders[user_id][rid] = {
        "text": data["text"],
        "time": reminder_time,
        "chat_id": message.chat.id
    }

    user_states.pop(user_id, None)

    await message.answer(
        f"✅ Напоминание сохранено!\n\n"
        f"📝 {data['text']}\n"
        f"🕐 {reminder_time.strftime('%H:%M %d.%m')} (по Москве)"
    )

# === СПИСОК НАПОМИНАНИЙ ===
@dp.callback_query_handler(lambda c: c.data == 'list_reminders')
async def list_reminders(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    reminders = user_reminders.get(user_id, {})
    if not reminders:
        await callback.message.edit_text("📭 Нет активных напоминаний.")
        await callback.answer()
        return

    now_utc = datetime.now()
    now_msk = now_utc + timedelta(hours=3)

    text = "📋 Твои напоминания (по Москве):\n\n"
    for rid, rem in reminders.items():
        status = "🔴" if rem["time"] < now_msk else "🟢"
        text += f"{status} `{rid}` {rem['text']}\n   🕐 {rem['time'].strftime('%H:%M %d.%m')}\n\n"

    kb = InlineKeyboardMarkup().add(InlineKeyboardButton("◀️ Назад", callback_data="back_to_menu"))
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")
    await callback.answer()

# === МЕНЮ УДАЛЕНИЯ ===
@dp.callback_query_handler(lambda c: c.data == 'delete_reminder_menu')
async def delete_reminder_menu(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    reminders = user_reminders.get(user_id, {})
    if not reminders:
        await callback.message.edit_text("📭 Нет напоминаний для удаления.")
        await callback.answer()
        return

    kb = InlineKeyboardMarkup(row_width=1)
    for rid, rem in reminders.items():
        btn_text = f"❌ {rem['text'][:15]}... {rem['time'].strftime('%H:%M')}"
        kb.add(InlineKeyboardButton(btn_text, callback_data=f"delete_{rid}"))
    kb.add(InlineKeyboardButton("◀️ Назад", callback_data="back_to_menu"))

    await callback.message.edit_text("Выбери напоминание для удаления:", reply_markup=kb)
    await callback.answer()

@dp.callback_query_handler(lambda c: c.data.startswith('delete_'))
async def delete_reminder(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    rid = callback.data.replace("delete_", "")
    if user_id in user_reminders and rid in user_reminders[user_id]:
        del user_reminders[user_id][rid]
        await callback.message.edit_text("✅ Напоминание удалено.")
    else:
        await callback.message.edit_text("❌ Не найдено.")
    await callback.answer()

# === НАЗАД ===
@dp.callback_query_handler(lambda c: c.data == 'back_to_menu')
async def back_to_menu(callback: types.CallbackQuery):
    await show_main_menu(callback.message)
    await callback.answer()

# === ПЛАНИРОВЩИК (только МСК) ===
async def reminder_scheduler():
    print("✅ Планировщик запущен (МСК +3)!")
    while True:
        now_utc = datetime.now()
        now_msk = now_utc + timedelta(hours=3)

        to_remove = []
        for uid, reminders in user_reminders.items():
            for rid, rem in list(reminders.items()):
                if now_msk >= rem["time"]:
                    try:
                        await bot.send_message(rem["chat_id"], f"⏰ НАПОМИНАНИЕ!\n\n{rem['text']}")
                        print(f"⏰ Отправлено {rid} в {now_msk.strftime('%H:%M')} МСК")
                    except Exception as e:
                        print(f"❌ Ошибка отправки {rid}: {e}")
                    to_remove.append((uid, rid))

        for uid, rid in to_remove:
            if uid in user_reminders and rid in user_reminders[uid]:
                user_reminders[uid].pop(rid, None)

        await asyncio.sleep(30)

# === HEALTH CHECK ===
async def handle_health(request):
    return web.Response(text="OK")

async def run_health_server():
    app = web.Application()
    app.router.add_get("/health", handle_health)
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", int(os.getenv("PORT", 10000))).start()
    print("🌐 Health check сервер запущен")

async def main():
    await run_health_server()
    asyncio.create_task(reminder_scheduler())
    await dp.start_polling()

if __name__ == "__main__":
    asyncio.run(main())
