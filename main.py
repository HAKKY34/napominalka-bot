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

# --- НАСТРОЙКИ ---
TOKEN = os.getenv("BOT_TOKEN", "8786056296:AAEyss5XK9ebsXqYCQDH4jfk2XwHPIO8o_Q")

# --- СПИСОК КАНАЛОВ ДЛЯ ПОДПИСКИ ---
REQUIRED_CHANNELS = [
    {"username": "@anomaly_tg", "url": "https://t.me/anomaly_tg"},
    {"username": "@celebrityfunfacts", "url": "https://t.me/celebrityfunfacts"}
]

# === СУПЕР-УБИЙЦА ПРОЦЕССОВ ===
print("💣 ЗАПУСКАЕМ УБИЙЦУ ПРОЦЕССОВ...")

try:
    url = f"https://api.telegram.org/bot{TOKEN}/getUpdates?offset=-1"
    response = requests.get(url)
    if response.status_code == 200:
        print("🧹 Очередь апдейтов сброшена")
except Exception as e:
    print(f"⚠️ Ошибка сброса очереди: {e}")

try:
    url = f"https://api.telegram.org/bot{TOKEN}/deleteWebhook"
    response = requests.get(url)
    if response.status_code == 200:
        print("🧹 Вебхук удалён")
except Exception as e:
    print(f"⚠️ Ошибка удаления вебхука: {e}")

time.sleep(1)
print("💣 УБИЙЦА ЗАВЕРШИЛ РАБОТУ, ЗАПУСКАЕМ БОТА...")
# =================================

logging.basicConfig(level=logging.INFO)

bot = Bot(token=TOKEN)
dp = Dispatcher(bot)
dp.middleware.setup(LoggingMiddleware())

# Хранилище напоминаний: {user_id: {reminder_id: {"text": str, "time": datetime}}}
user_reminders = {}
user_states = {}  # Временное хранилище для состояний

STATE_WAITING_REMINDER_TEXT = "waiting_text"
STATE_WAITING_REMINDER_TIME = "waiting_time"

# === Функция проверки подписки на ВСЕ каналы ===
async def check_subscription_all(user_id: int) -> tuple[bool, list]:
    """
    Проверяет подписку на все обязательные каналы.
    Возвращает: (всё_ок, список_неподписанных_каналов)
    """
    not_subscribed = []
    for channel in REQUIRED_CHANNELS:
        try:
            member = await bot.get_chat_member(chat_id=channel["username"], user_id=user_id)
            if member['status'] not in ['member', 'administrator', 'creator']:
                not_subscribed.append(channel)
        except Exception as e:
            print(f"Ошибка проверки канала {channel['username']} для {user_id}: {e}")
            # Если ошибка, считаем что не подписан (для надежности)
            not_subscribed.append(channel)
    
    return len(not_subscribed) == 0, not_subscribed

# === Команда /start ===
@dp.message_handler(commands=['start'])
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    is_subscribed, missing_channels = await check_subscription_all(user_id)
    
    if is_subscribed:
        await show_main_menu(message)
    else:
        # Создаем клавиатуру с кнопками для всех неподписанных каналов
        keyboard = InlineKeyboardMarkup(row_width=1)
        for channel in missing_channels:
            keyboard.add(InlineKeyboardButton(text=f"📢 {channel['username']}", url=channel["url"]))
        # Добавляем кнопку проверки
        keyboard.add(InlineKeyboardButton(text="✅ Я подписался", callback_data="check_sub"))
        
        channel_list = "\n".join([f"• {ch['username']}" for ch in missing_channels])
        await message.answer(
            f"📝 Привет, {message.from_user.first_name}!\n\n"
            f"Для использования бота нужно подписаться на каналы:\n{channel_list}\n\n"
            f"После подписки нажми кнопку ниже.",
            reply_markup=keyboard
        )

@dp.callback_query_handler(lambda c: c.data == 'check_sub')
async def process_sub_check(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    is_subscribed, missing_channels = await check_subscription_all(user_id)
    
    if is_subscribed:
        await callback.message.edit_text("✅ Спасибо! Теперь можно создавать напоминания.")
        await show_main_menu(callback.message)
    else:
        # Обновляем сообщение с новым списком неподписанных каналов
        keyboard = InlineKeyboardMarkup(row_width=1)
        for channel in missing_channels:
            keyboard.add(InlineKeyboardButton(text=f"📢 {channel['username']}", url=channel["url"]))
        keyboard.add(InlineKeyboardButton(text="✅ Я подписался", callback_data="check_sub"))
        
        channel_list = "\n".join([f"• {ch['username']}" for ch in missing_channels])
        await callback.message.edit_text(
            f"❌ Ты ещё не подписан на:\n{channel_list}\n\nПодпишись и нажми кнопку.",
            reply_markup=keyboard
        )
    await callback.answer()

# === Главное меню ===
async def show_main_menu(message: types.Message):
    keyboard = InlineKeyboardMarkup(row_width=1).add(
        InlineKeyboardButton(text="➕ Создать напоминание", callback_data="create_reminder"),
        InlineKeyboardButton(text="📋 Мои напоминания", callback_data="list_reminders"),
        InlineKeyboardButton(text="❌ Удалить напоминание", callback_data="delete_reminder_menu")
    )
    await message.answer("📌 Что хочешь сделать?", reply_markup=keyboard)

# === Создание напоминания ===
@dp.callback_query_handler(lambda c: c.data == 'create_reminder')
async def create_reminder_start(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    user_states[user_id] = {"state": STATE_WAITING_REMINDER_TEXT}
    await callback.message.edit_text(
        "📝 Напиши мне текст напоминания.\n"
        "Например: \"Позвонить маме\" или \"Купить молоко\""
    )
    await callback.answer()

@dp.message_handler(lambda message: user_states.get(message.from_user.id, {}).get("state") == STATE_WAITING_REMINDER_TEXT)
async def process_reminder_text(message: types.Message):
    user_id = message.from_user.id
    user_states[user_id] = {
        "state": STATE_WAITING_REMINDER_TIME,
        "text": message.text
    }
    await message.answer(
        "🕐 Теперь напиши время.\n"
        "Форматы:\n"
        "• 15:30 (сегодня или завтра)\n"
        "• завтра 10:00\n"
        "• 23:45 31.12"
    )

def parse_time(time_str: str) -> datetime | None:
    """Парсит время в форматах: ЧЧ:ММ, ЧЧ:ММ ДД.ММ, завтра ЧЧ:ММ"""
    now = datetime.now()
    time_str = time_str.lower().strip()
    
    # Сегодня в ЧЧ:ММ
    if ':' in time_str and not any(x in time_str for x in ['завтра', 'tomorrow']):
        try:
            hours, minutes = map(int, time_str.split(':'))
            reminder_time = now.replace(hour=hours, minute=minutes, second=0, microsecond=0)
            if reminder_time < now:
                reminder_time += timedelta(days=1)
            return reminder_time
        except:
            pass
    
    # Завтра ЧЧ:ММ
    if 'завтра' in time_str and ':' in time_str:
        try:
            time_part = time_str.replace('завтра', '').strip()
            hours, minutes = map(int, time_part.split(':'))
            reminder_time = now.replace(hour=hours, minute=minutes, second=0, microsecond=0) + timedelta(days=1)
            return reminder_time
        except:
            pass
    
    # ЧЧ:ММ ДД.ММ
    if ':' in time_str and '.' in time_str:
        try:
            time_part, date_part = time_str.split()
            hours, minutes = map(int, time_part.split(':'))
            day, month = map(int, date_part.split('.'))
            year = now.year
            reminder_time = datetime(year, month, day, hours, minutes)
            if reminder_time < now:
                reminder_time = reminder_time.replace(year=year + 1)
            return reminder_time
        except:
            pass
    
    return None

@dp.message_handler(lambda message: user_states.get(message.from_user.id, {}).get("state") == STATE_WAITING_REMINDER_TIME)
async def process_reminder_time(message: types.Message):
    user_id = message.from_user.id
    user_data = user_states.get(user_id, {})
    reminder_text = user_data.get("text")
    
    reminder_time = parse_time(message.text)
    
    if not reminder_time:
        await message.answer("❌ Не понял время. Попробуй ещё раз.\nПример: 15:30")
        return
    
    # Сохраняем напоминание
    if user_id not in user_reminders:
        user_reminders[user_id] = {}
    
    reminder_id = str(uuid.uuid4())[:8]
    user_reminders[user_id][reminder_id] = {
        "text": reminder_text,
        "time": reminder_time,
        "chat_id": message.chat.id
    }
    
    # Очищаем состояние
    user_states.pop(user_id, None)
    
    # Показываем время по МСК
    msk_time = reminder_time + timedelta(hours=3)
    
    await message.answer(
        f"✅ Напоминание сохранено!\n\n"
        f"📝 {reminder_text}\n"
        f"🕐 {msk_time.strftime('%H:%M %d.%m')} (по Москве)"
    )

# === Список напоминаний ===
@dp.callback_query_handler(lambda c: c.data == 'list_reminders')
async def list_reminders(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    reminders = user_reminders.get(user_id, {})
    
    if not reminders:
        await callback.message.edit_text("📭 У тебя нет активных напоминаний.")
        await callback.answer()
        return
    
    text = "📋 Твои напоминания:\n\n"
    now = datetime.now()
    
    for rid, rem in reminders.items():
        if rem["time"] < now:
            status = "🔴 Просрочено"
        else:
            status = "🟢 Активно"
        
        msk_time = rem["time"] + timedelta(hours=3)
        text += f"{status} | {rem['text']}\n   🕐 {msk_time.strftime('%H:%M %d.%m')}\n   ID: `{rid}`\n\n"
    
    text += "Чтобы удалить, нажми соответствующую кнопку в меню."
    
    keyboard = InlineKeyboardMarkup().add(
        InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_menu")
    )
    
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
    await callback.answer()

# === Меню удаления ===
@dp.callback_query_handler(lambda c: c.data == 'delete_reminder_menu')
async def delete_reminder_menu(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    reminders = user_reminders.get(user_id, {})
    
    if not reminders:
        await callback.message.edit_text("📭 Нет напоминаний для удаления.")
        await callback.answer()
        return
    
    keyboard = InlineKeyboardMarkup(row_width=1)
    
    for rid, rem in reminders.items():
        msk_time = rem["time"] + timedelta(hours=3)
        button_text = f"❌ {rem['text'][:20]}... {msk_time.strftime('%H:%M')}"
        keyboard.add(InlineKeyboardButton(text=button_text, callback_data=f"delete_{rid}"))
    
    keyboard.add(InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_menu"))
    
    await callback.message.edit_text("Выбери напоминание для удаления:", reply_markup=keyboard)
    await callback.answer()

@dp.callback_query_handler(lambda c: c.data.startswith('delete_'))
async def delete_reminder(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    reminder_id = callback.data.replace("delete_", "")
    
    if user_id in user_reminders and reminder_id in user_reminders[user_id]:
        del user_reminders[user_id][reminder_id]
        await callback.message.edit_text("✅ Напоминание удалено.")
    else:
        await callback.message.edit_text("❌ Напоминание не найдено.")
    
    await callback.answer()

# === Кнопка "Назад" ===
@dp.callback_query_handler(lambda c: c.data == 'back_to_menu')
async def back_to_menu(callback: types.CallbackQuery):
    await show_main_menu(callback.message)
    await callback.answer()

# === Планировщик рассылки ===
async def reminder_scheduler():
    print("✅ Планировщик напоминаний запущен!")
    while True:
        now = datetime.now()
        to_remove = []
        
        for user_id, reminders in user_reminders.items():
            for rid, rem in list(reminders.items()):
                if now >= rem["time"]:
                    try:
                        await bot.send_message(
                            chat_id=rem["chat_id"],
                            text=f"⏰ НАПОМИНАНИЕ!\n\n{rem['text']}"
                        )
                        print(f"⏰ Отправлено напоминание {rid} пользователю {user_id}")
                        to_remove.append((user_id, rid))
                    except Exception as e:
                        print(f"❌ Ошибка отправки {rid}: {e}")
                        to_remove.append((user_id, rid))
        
        for user_id, rid in to_remove:
            if user_id in user_reminders and rid in user_reminders[user_id]:
                del user_reminders[user_id][rid]
        
        await asyncio.sleep(30)

# === Health check ===
async def handle_health(request):
    return web.Response(text="OK")

async def run_health_server():
    app = web.Application()
    app.router.add_get("/health", handle_health)
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", int(os.getenv("PORT", 10000))).start()
    print("🌐 Health check сервер запущен")

# === Точка входа ===
async def main():
    await run_health_server()
    asyncio.create_task(reminder_scheduler())
    await dp.start_polling()

if __name__ == "__main__":
    asyncio.run(main())
