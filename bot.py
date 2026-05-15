from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
import asyncio
import os
from datetime import datetime, timedelta
import aiosqlite
import json

TOKEN = os.getenv("TOKEN")
bot = Bot(token=TOKEN)
dp = Dispatcher()

# ===================== СОСТОЯНИЯ =====================
class GoalStates(StatesGroup):
    waiting_name = State()
    waiting_category = State()
    waiting_description = State()

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
                            streak INTEGER DEFAULT 0,
                            completed INTEGER DEFAULT 0)''')
        await db.commit()

main_menu = ReplyKeyboardMarkup(keyboard=[
    [KeyboardButton(text="🎯 Мои цели")],
    [KeyboardButton(text="➕ Добавить цель")],
    [KeyboardButton(text="📊 Статистика")],
    [KeyboardButton(text="👤 Моя подписка")],
    [KeyboardButton(text="💎 Купить подписку 0.99$")],
], resize_keyboard=True)

# ===================== ФУНКЦИИ =====================
async def get_user_goals(user_id: int):
    async with aiosqlite.connect('coach.db') as db:
        async with db.execute("SELECT * FROM goals WHERE user_id = ? ORDER BY streak DESC", (user_id,)) as cursor:
            return await cursor.fetchall()

async def add_goal(user_id: int, name: str, category: str, description: str):
    async with aiosqlite.connect('coach.db') as db:
        await db.execute("INSERT INTO goals (user_id, name, category, description, created) VALUES (?, ?, ?, ?, ?)",
                        (user_id, name, category, description, datetime.now().isoformat()))
        await db.commit()

# ===================== ХЭНДЛЕРЫ =====================
@dp.message(Command("start"))
async def start(message: types.Message):
    await init_db()
    await message.answer(
        "👋 Добро пожаловать в <b>AI Коуч</b>!\n\n"
        "Я помогу тебе изменить жизнь: формировать привычки, достигать целей и становиться лучше каждый день.",
        reply_markup=main_menu, parse_mode="HTML"
    )

@dp.message(F.text == "➕ Добавить цель")
async def add_goal_start(message: types.Message, state: FSMContext):
    await message.answer("Напиши название цели (например: «Заниматься спортом 5 раз в неделю», «Читать 20 страниц каждый день»):")
    await state.set_state(GoalStates.waiting_name)

@dp.message(GoalStates.waiting_name)
async def goal_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏋️ Здоровье", callback_data="cat_health")],
        [InlineKeyboardButton(text="📚 Продуктивность", callback_data="cat_productivity")],
        [InlineKeyboardButton(text="💰 Финансы", callback_data="cat_finance")],
        [InlineKeyboardButton(text="❤️ Отношения", callback_data="cat_relationships")],
        [InlineKeyboardButton(text="🧠 Саморазвитие", callback_data="cat_self")],
    ])
    await message.answer("Выбери категорию цели:", reply_markup=kb)

@dp.callback_query(F.data.startswith("cat_"))
async def goal_category(callback: types.CallbackQuery, state: FSMContext):
    category = callback.data.split("_")[1]
    await state.update_data(category=category)
    await callback.message.edit_text("Напиши краткое описание цели (что именно ты хочешь достичь):")
    await state.set_state(GoalStates.waiting_description)

@dp.message(GoalStates.waiting_description)
async def goal_description(message: types.Message, state: FSMContext):
    data = await state.get_data()
    await add_goal(message.from_user.id, data['name'], data['category'], message.text)
    await message.answer(f"✅ Цель «{data['name']}» успешно добавлена!")
    await state.clear()

@dp.message(F.text == "🎯 Мои цели")
async def my_goals(message: types.Message):
    goals = await get_user_goals(message.from_user.id)
    if not goals:
        await message.answer("У тебя пока нет целей. Добавь первую!")
        return

    text = "<b>🎯 Твои цели:</b>\n\n"
    for g in goals:
        text += f"• {g[2]} ({g[3]}) — стрик: <b>{g[7]} дней</b>\n"
    await message.answer(text, parse_mode="HTML")

@dp.message(F.text == "📊 Статистика")
async def statistics(message: types.Message):
    goals = await get_user_goals(message.from_user.id)
    total = len(goals)
    active = sum(1 for g in goals if g[7] > 0)
    
    text = f"<b>📊 Твоя статистика</b>\n\n"
    text += f"Всего целей: <b>{total}</b>\n"
    text += f"Активных целей: <b>{active}</b>\n"
    text += f"Общий стрик по всем целям: <b>{sum(g[7] for g in goals)}</b> дней\n\n"
    text += "Продолжай в том же духе! 🔥"
    await message.answer(text, parse_mode="HTML")

# ===================== ПОДПИСКА =====================
@dp.message(F.text == "💎 Купить подписку 0.99$")
async def buy_subscription(message: types.Message):
    prices = [types.LabeledPrice(label="Подписка 30 дней", amount=99)]
    await bot.send_invoice(
        chat_id=message.chat.id,
        title="Подписка «AI Коуч»",
        description="Неограниченное количество целей + продвинутые рекомендации",
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
    await message.answer("🎉 Подписка активирована!\nТеперь ты можешь иметь неограниченное количество целей.")

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
    print("🚀 AI Коуч успешно запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
