from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
import asyncio
import os
from datetime import datetime, timedelta
import aiosqlite
import aiohttp

TOKEN = os.getenv("TOKEN")
AI_API_KEY = os.getenv("AI_API_KEY")

bot = Bot(token=TOKEN)
dp = Dispatcher()

# ===================== БАЗА ДАННЫХ =====================
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
                headers={"Authorization": f"Bearer {AI_API_KEY}"},
                json={
                    "model": "grok-4.1-fast",
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.8,
                    "max_tokens": 900
                }
            ) as resp:
                data = await resp.json()
                return data['choices'][0]['message']['content']
    except:
        return "Извини, я сейчас перегружен. Попробуй позже."

# ===================== ПРОВЕРКА ЛИМИТА =====================
async def can_send_message(user_id: int):
    async with aiosqlite.connect('psychology.db') as db:
        async with db.execute("SELECT subscribed_until, messages_today, last_reset FROM users WHERE user_id = ?", 
                            (user_id,)) as cursor:
            row = await cursor.fetchone()
            
            if not row:
                await db.execute("INSERT INTO users (user_id, messages_today, last_reset) VALUES (?, 0, ?)", 
                               (user_id, datetime.now().date().isoformat()))
                await db.commit()
                return True, 5

            subscribed_until, messages_today, last_reset = row
            today = datetime.now().date().isoformat()

            # Сброс счётчика в новый день
            if last_reset != today:
                await db.execute("UPDATE users SET messages_today = 0, last_reset = ? WHERE user_id = ?", 
                               (today, user_id))
                await db.commit()
                messages_today = 0

            is_premium = subscribed_until and datetime.fromisoformat(subscribed_until) > datetime.now()
            
            if is_premium:
                return True, 200
            else:
                return messages_today < 5, 5 - messages_today

# ===================== ХЭНДЛЕРЫ =====================
@dp.message(Command("start"))
async def start(message: types.Message):
    await init_db()
    await message.answer(
        "👋 Добро пожаловать в <b>AI Психолог Отношений</b>\n\n"
        "Я помогу тебе разобраться в отношениях, любви, конфликтах и чувствах.\n\n"
        "Пиши мне всё, что тебя беспокоит.",
        reply_markup=main_menu, parse_mode="HTML"
    )

@dp.message()
async def ai_psychologist(message: types.Message):
    can_send, remaining = await can_send_message(message.from_user.id)
    
    if not can_send:
        await message.answer(
            "❌ Сегодня ты использовал все 5 бесплатных сообщений.\n\n"
            "Оформи подписку за 1$, чтобы общаться без ограничений (200 сообщений в день).",
            reply_markup=main_menu
        )
        return

    # Обновляем счётчик
    async with aiosqlite.connect('psychology.db') as db:
        await db.execute("UPDATE users SET messages_today = messages_today + 1 WHERE user_id = ?", 
                        (message.from_user.id,))
        await db.commit()

    thinking = await message.answer("🤔 Думаю над твоим вопросом...")

    prompt = f"""Ты — опытный психолог по отношениям, эмпатичный, честный и прямой.
Пользователь написал: "{message.text}"
Дай глубокий, полезный и поддерживающий ответ."""

    response = await ask_grok(prompt)
    
    await thinking.delete()
    await message.answer(response)

@dp.message(F.text == "💎 Купить подписку за 1$")
async def buy_subscription(message: types.Message):
    prices = [types.LabeledPrice(label="Подписка 30 дней", amount=99)]  # 0.99$
    await bot.send_invoice(
        chat_id=message.chat.id,
        title="Подписка AI Психолог Отношений",
        description="200 сообщений в день + приоритетные ответы",
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
    await message.answer("🎉 Подписка успешно активирована!\nТеперь у тебя 200 сообщений в день.")

async def main():
    await init_db()
    print("🚀 AI Психолог Отношений запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
