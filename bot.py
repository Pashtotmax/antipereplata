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
                            last_reset TEXT)''')
        await db.commit()

main_menu = ReplyKeyboardMarkup(keyboard=[
    [KeyboardButton(text="💎 Купить подписку за 1$")],
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
                    "model": "grok-4",          # ← Исправлено
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.8,
                    "max_tokens": 800
                },
                timeout=30
            ) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    print(f"API Error {resp.status}: {text}")
                    return f"Ошибка API ({resp.status}). Попробуй позже."
                
                data = await resp.json()
                return data['choices'][0]['message']['content']
                
    except Exception as e:
        error_text = traceback.format_exc()
        print("AI ERROR:", error_text)
        return "Извини, сейчас проблемы с соединением. Попробуй через минуту."

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
            limit = 200 if is_premium else 5
            return messages_today < limit, limit - messages_today

# ===================== ХЭНДЛЕРЫ =====================
@dp.message(Command("start"))
async def start(message: types.Message):
    await init_db()
    await message.answer(
        "👋 Добро пожаловать в <b>AI Психолог Отношений</b>\n\n"
        "Пиши мне всё, что у тебя на душе.",
        reply_markup=main_menu, parse_mode="HTML"
    )

@dp.message()
async def ai_psychologist(message: types.Message):
    can_send, remaining = await can_send_message(message.from_user.id)
    
    if not can_send:
        await message.answer("❌ Лимит бесплатных сообщений исчерпан.\nОформи подписку за 1$.", reply_markup=main_menu)
        return

    async with aiosqlite.connect('psychology.db') as db:
        await db.execute("UPDATE users SET messages_today = messages_today + 1 WHERE user_id = ?", (message.from_user.id,))
        await db.commit()

    thinking = await message.answer("🤔 Думаю...")

    prompt = f"""Ты — эмпатичный и честный психолог по отношениям.
Пользователь: "{message.text}"
Дай полезный, глубокий ответ."""

    response = await ask_grok(prompt)
    
    await thinking.delete()
    await message.answer(response)

@dp.message(F.text == "💎 Купить подписку за 1$")
async def buy_subscription(message: types.Message):
    prices = [types.LabeledPrice(label="Подписка 30 дней", amount=99)]
    await bot.send_invoice(
        chat_id=message.chat.id,
        title="Подписка AI Психолог Отношений",
        description="200 сообщений в день",
        payload="monthly_sub",
        provider_token="",
        currency="XTR",
        prices=prices
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
    await message.answer("🎉 Подписка активирована! Теперь у тебя 200 сообщений в день.")

async def main():
    await init_db()
    print("🚀 AI Психолог Отношений запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
