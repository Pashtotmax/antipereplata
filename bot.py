from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
import asyncio
import os
from datetime import datetime, timedelta
import aiosqlite
import aiohttp

TOKEN = os.getenv("TOKEN")
AI_API_KEY = os.getenv("AI_API_KEY")  # Grok API

bot = Bot(token=TOKEN)
dp = Dispatcher()

# ===================== FSM =====================
class GoalForm(StatesGroup):
    name = State()
    category = State()
    description = State()

# ===================== БАЗА ДАННЫХ =====================
async def init_db():
    async with aiosqlite.connect('coach.db') as db:
        await db.execute('''CREATE TABLE IF NOT EXISTS users 
                           (user_id INTEGER PRIMARY KEY, 
                            subscribed_until TEXT)''')
        
        await db.execute('''CREATE TABLE IF NOT EXISTS goals 
                           (id INTEGER PRIMARY KEY AUTOINCREMENT,
                            user_id INTEGER,
                            name TEXT,
                            category TEXT,
                            description TEXT,
                            created TEXT,
                            last_done TEXT,
                            streak INTEGER DEFAULT 0)''')
        
        await db.execute('''CREATE TABLE IF NOT EXISTS daily_progress 
                           (id INTEGER PRIMARY KEY AUTOINCREMENT,
                            user_id INTEGER,
                            date TEXT,
                            goal_id INTEGER,
                            completed INTEGER DEFAULT 0,
                            note TEXT)''')
        await db.commit()

main_menu = ReplyKeyboardMarkup(keyboard=[
    [KeyboardButton(text="🎯 Мои цели")],
    [KeyboardButton(text="➕ Добавить цель")],
    [KeyboardButton(text="📅 Задание на сегодня")],
    [KeyboardButton(text="📊 Статистика")],
    [KeyboardButton(text="👤 Моя подписка")],
    [KeyboardButton(text="💎 Купить подписку 0.99$")],
], resize_keyboard=True)

# ===================== AI =====================
async def ask_ai(prompt: str):
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api.x.ai/v1/chat/completions",
                headers={"Authorization": f"Bearer {AI_API_KEY}"},
                json={
                    "model": "grok-4.1-fast",
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.75,
                    "max_tokens": 900
                }
            ) as resp:
                data = await resp.json()
                return data['choices'][0]['message']['content']
    except:
        return "Извини, я сейчас немного перегружен. Попробуй позже."

# ===================== ПРОВЕРКА ПОДПИСКИ =====================
async def is_premium(user_id: int):
    async with aiosqlite.connect('coach.db') as db:
        async with db.execute("SELECT subscribed_until FROM users WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            if row and row[0]:
                return datetime.fromisoformat(row[0]) > datetime.now()
    return False

async def get_goals_count(user_id: int):
    async with aiosqlite.connect('coach.db') as db:
        async with db.execute("SELECT COUNT(*) FROM goals WHERE user_id = ?", (user_id,)) as cursor:
            return (await cursor.fetchone())[0]

# ===================== ХЭНДЛЕРЫ =====================
@dp.message(Command("start"))
async def start(message: types.Message):
    await init_db()
    await message.answer(
        "👋 Добро пожаловать в <b>AI Личный Коуч</b>!\n\n"
        "Я буду твоим персональным тренером. Давай вместе достигать целей.",
        reply_markup=main_menu, parse_mode="HTML"
    )

@dp.message(F.text == "➕ Добавить цель")
async def add_goal_start(message: types.Message, state: FSMContext):
    premium = await is_premium(message.from_user.id)
    count = await get_goals_count(message.from_user.id)
    
    if not premium and count >= 2:
        await message.answer("❌ В бесплатной версии можно создать только 2 цели.\n\nОформи подписку для неограниченного количества целей.")
        return

    await message.answer("Напиши название цели:")
    await state.set_state(GoalForm.name)

@dp.message(GoalForm.name)
async def goal_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏋️ Здоровье", callback_data="cat_health")],
        [InlineKeyboardButton(text="📚 Продуктивность", callback_data="cat_productivity")],
        [InlineKeyboardButton(text="💰 Финансы", callback_data="cat_finance")],
        [InlineKeyboardButton(text="❤️ Отношения", callback_data="cat_relationships")],
        [InlineKeyboardButton(text="🧠 Саморазвитие", callback_data="cat_self")],
    ])
    await message.answer("Выбери категорию:", reply_markup=kb)

@dp.callback_query(F.data.startswith("cat_"))
async def goal_category(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    category = callback.data.split("_")[1]
    await state.update_data(category=category)
    await callback.message.edit_text("Напиши краткое описание цели:")
    await state.set_state(GoalForm.description)

@dp.message(GoalForm.description)
async def goal_description(message: types.Message, state: FSMContext):
    data = await state.get_data()
    async with aiosqlite.connect('coach.db') as db:
        await db.execute("INSERT INTO goals (user_id, name, category, description, created) VALUES (?, ?, ?, ?, ?)",
                        (message.from_user.id, data['name'], data['category'], message.text, datetime.now().isoformat()))
        await db.commit()
    await message.answer(f"✅ Цель «{data['name']}» успешно добавлена!")
    await state.clear()

@dp.message(F.text == "🎯 Мои цели")
async def my_goals(message: types.Message):
    async with aiosqlite.connect('coach.db') as db:
        async with db.execute("SELECT name, category, streak FROM goals WHERE user_id = ?", 
                            (message.from_user.id,)) as cursor:
            goals = await cursor.fetchall()
    
    if not goals:
        await message.answer("У тебя пока нет целей.")
        return

    text = "<b>🎯 Твои цели:</b>\n\n"
    for name, cat, streak in goals:
        text += f"• {name} ({cat}) — стрик: <b>{streak} дней</b>\n"
    await message.answer(text, parse_mode="HTML")

@dp.message(F.text == "📅 Задание на сегодня")
async def daily_task(message: types.Message):
    premium = await is_premium(message.from_user.id)
    
    async with aiosqlite.connect('coach.db') as db:
        async with db.execute("SELECT id, name, category FROM goals WHERE user_id = ?", 
                            (message.from_user.id,)) as cursor:
            goals = await cursor.fetchall()

    if not goals:
        await message.answer("Сначала добавь хотя бы одну цель.")
        return

    prompt = f"""Ты — строгий, но добрый личный коуч.
Пользователь имеет следующие цели: {goals}.
Придумай 1–2 конкретных, реалистичных и полезных задания на сегодня."""

    task = await ask_ai(prompt)
    
    await message.answer(f"📅 <b>Задание на сегодня:</b>\n\n{task}", parse_mode="HTML")

@dp.message(F.text == "📊 Статистика")
async def statistics(message: types.Message):
    async with aiosqlite.connect('coach.db') as db:
        async with db.execute("SELECT COUNT(*), SUM(streak) FROM goals WHERE user_id = ?", 
                            (message.from_user.id,)) as cursor:
            row = await cursor.fetchone()
            total = row[0] or 0
            streak = row[1] or 0

    premium = await is_premium(message.from_user.id)
    
    text = f"<b>📊 Твоя статистика</b>\n\n"
    text += f"Всего целей: <b>{total}</b>\n"
    text += f"Общий стрик: <b>{streak} дней</b>\n\n"
    
    if premium:
        text += "У тебя полный доступ. Продолжай в том же духе!"
    else:
        text += "Оформи подписку, чтобы получить персональные планы и глубокий анализ."
    
    await message.answer(text, parse_mode="HTML")

# ===================== ПОДПИСКА =====================
@dp.message(F.text == "💎 Купить подписку 0.99$")
async def buy_subscription(message: types.Message):
    prices = [types.LabeledPrice(label="Подписка 30 дней", amount=99)]
    await bot.send_invoice(
        chat_id=message.chat.id,
        title="Подписка AI Личный Коуч",
        description="Неограниченные цели + персональные ежедневные планы + глубокий анализ",
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
    async with aiosqlite.connect('coach.db') as db:
        await db.execute("INSERT OR REPLACE INTO users (user_id, subscribed_until) VALUES (?, ?)", 
                        (message.from_user.id, until))
        await db.commit()
    await message.answer("🎉 Подписка активирована!\nТеперь у тебя полный доступ ко всем функциям.")

@dp.message(F.text == "👤 Моя подписка")
async def my_sub(message: types.Message):
    async with aiosqlite.connect('coach.db') as db:
        async with db.execute("SELECT subscribed_until FROM users WHERE user_id = ?", 
                            (message.from_user.id,)) as cursor:
            row = await cursor.fetchone()
            if row and row[0]:
                days = (datetime.fromisoformat(row[0]) - datetime.now()).days
                await message.answer(f"✅ Подписка активна!\nОсталось: <b>{days} дней</b>", parse_mode="HTML")
            else:
                await message.answer("❌ У тебя нет активной подписки.")

async def main():
    await init_db()
    print("🚀 AI Личный Коуч запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
