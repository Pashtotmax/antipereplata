from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
import asyncio
import os
from datetime import datetime, timedelta
import aiosqlite
import aiohttp
import traceback

TOKEN = os.getenv("TOKEN")
AI_API_KEY = os.getenv("AI_API_KEY")

bot = Bot(token=TOKEN)
dp = Dispatcher()

# ===================== БАЗА =====================
async def init_db():
    async with aiosqlite.connect('psychology.db') as db:
        await db.execute('''CREATE TABLE IF NOT EXISTS users
                           (user_id INTEGER PRIMARY KEY,
                            subscribed_until TEXT,
                            messages_today INTEGER DEFAULT 0,
                            last_reset TEXT,
                            gender TEXT DEFAULT NULL)''')  # Новое поле
        await db.commit()

main_menu = ReplyKeyboardMarkup(keyboard=[
    [KeyboardButton(text="💎 Купить подписку за 0.99$")],
], resize_keyboard=True)

# ===================== AI =====================
async def ask_grok(prompt: str):
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api.x.ai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {AI_API_KEY}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "grok-4",
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.85,
                    "max_tokens": 850
                },
                timeout=35
            ) as resp:
                if resp.status != 200:
                    return "Давай чуть позже, сейчас немного тяжело."
               
                data = await resp.json()
                return data['choices'][0]['message']['content']
               
    except Exception as e:
        print("AI ERROR:", str(e))
        return "Извини, давай попробуем через минуту."

# ===================== ОПРЕДЕЛЕНИЕ И СОХРАНЕНИЕ ПОЛА =====================
async def get_opposite_gender(user_id: int, message_text: str):
    async with aiosqlite.connect('psychology.db') as db:
        async with db.execute("SELECT gender FROM users WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            if row and row[0]:
                return row[0]

    # Простое определение по тексту (можно улучшить позже)
    text_lower = message_text.lower()
    if any(word in text_lower for word in ["я девушка", "я женщина", "я девочка", "мне 18", "подруга"]):
        gender = "male"
    elif any(word in text_lower for word in ["я парень", "я мужчина", "я мужик", "я юноша"]):
        gender = "female"
    else:
        gender = None  # Не определён

    if gender:
        async with aiosqlite.connect('psychology.db') as db:
            await db.execute("UPDATE users SET gender = ? WHERE user_id = ?", (gender, user_id))
            await db.commit()
    
    return gender

# ===================== ЛИМИТЫ =====================
async def can_send_message(user_id: int):
    async with aiosqlite.connect('psychology.db') as db:
        async with db.execute("SELECT subscribed_until, messages_today, last_reset FROM users WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
           
            if not row:
                await db.execute("INSERT INTO users (user_id, messages_today, last_reset) VALUES (?, 0, ?)",
                               (user_id, datetime.now().date().isoformat()))
                await db.commit()
                return True, 5

            subscribed_until, messages_today, last_reset = row
            today = datetime.now().date().isoformat()
            if last_reset != today:
                await db.execute("UPDATE users SET messages_today = 0, last_reset = ? WHERE user_id = ?",
                               (today, user_id))
                await db.commit()
                messages_today = 0

            is_premium = subscribed_until and datetime.fromisoformat(subscribed_until) > datetime.now()
            limit = 150 if is_premium else 5
            return messages_today < limit, limit - messages_today

# ===================== ХЭНДЛЕРЫ =====================
@dp.message(Command("start"))
async def start(message: types.Message):
    await init_db()
    await message.answer(
        "Привет! Я здесь, чтобы помочь тебе с отношениями и чувствами.\n\n"
        "Пиши мне всё, что на душе.",
        reply_markup=main_menu
    )

@dp.message(F.text == "💎 Купить подписку за 0.99$")
async def buy_subscription(message: types.Message):
    prices = [types.LabeledPrice(label="Подписка на 30 дней", amount=99)]
    await bot.send_invoice(
        chat_id=message.chat.id,
        title="Подписка AI Психолог Отношений",
        description="150 сообщений в сутки • Автоматическое продление каждый месяц",
        payload="monthly_sub",
        provider_token="",
        currency="XTR",
        prices=prices,
        start_parameter="sub"
    )

@dp.pre_checkout_query()
async def pre_checkout(query: types.PreCheckoutQuery):
    await query.answer(ok=True)

@dp.message(F.successful_payment)
async def successful_payment(message: types.Message):
    until = (datetime.now() + timedelta(days=30)).isoformat()
    async with aiosqlite.connect('psychology.db') as db:
        await db.execute("INSERT OR REPLACE INTO users (user_id, subscribed_until) VALUES (?, ?)",
                        (message.from_user.id, until))
        await db.commit()
    await message.answer("✅ Подписка успешно активирована!\nТеперь у тебя 150 сообщений в сутки.")

@dp.message()
async def ai_psychologist(message: types.Message):
    can_send, remaining = await can_send_message(message.from_user.id)
   
    if not can_send:
        await message.answer(
            "Сегодня ты уже использовал все бесплатные сообщения.\n\n"
            "Оформи подписку за 0.99$, чтобы продолжить общение (150 сообщений в сутки).",
            reply_markup=main_menu
        )
        return

    # Определяем пол и выбираем роль
    user_gender = await get_opposite_gender(message.from_user.id, message.text)
    role = "мужчина" if user_gender == "female" else "женщина" if user_gender == "male" else "человек"

    async with aiosqlite.connect('psychology.db') as db:
        await db.execute("UPDATE users SET messages_today = messages_today + 1 WHERE user_id = ?", (message.from_user.id,))
        await db.commit()

    thinking = await message.answer("Пишу...")

    prompt = f"""Ты — {role}, тёплый, понимающий и прямой психолог по отношениям. 
Разговаривай естественно, как живой человек противоположного пола пользователю.
Пользователь написал: "{message.text}"
Дай ему честный, эмпатичный и полезный ответ."""

    response = await ask_grok(prompt)
   
    await thinking.delete()
    await message.answer(response)

async def main():
    await init_db()
    print("🚀 AI Психолог Отношений запущен!")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
