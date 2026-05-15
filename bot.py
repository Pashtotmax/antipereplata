from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
import asyncio
import os
from datetime import datetime, timedelta
import aiosqlite

TOKEN = os.getenv("TOKEN")
bot = Bot(token=TOKEN)
dp = Dispatcher()

async def init_db():
    async with aiosqlite.connect('users.db') as db:
        await db.execute('''CREATE TABLE IF NOT EXISTS users 
                           (user_id INTEGER PRIMARY KEY, 
                            subscribed_until TEXT)''')
        await db.commit()

main_menu = ReplyKeyboardMarkup(keyboard=[
    [KeyboardButton(text="🔥 Выгодные покупки сегодня")],
    [KeyboardButton(text="🔍 Поиск товара")],
    [KeyboardButton(text="👤 Моя подписка")],
    [KeyboardButton(text="💎 Купить подписку 0.99$")],
], resize_keyboard=True)

@dp.message(Command("start"))
async def start(message: types.Message):
    await init_db()
    await message.answer("👋 Добро пожаловать в <b>Антипереплата</b>!", reply_markup=main_menu, parse_mode="HTML")

@dp.message(F.text == "🔍 Поиск товара")
async def search_request(message: types.Message):
    await message.answer("Напиши, что хочешь купить:")

@dp.message()
async def handle_search(message: types.Message):
    await message.answer("🔍 Ищу лучшие предложения...\n\n1️⃣ Хороший вариант найден\n2️⃣ |||||||||||||||||| (заблюрено)\n3️⃣ |||||||||||||||||| (заблюрено)")

async def main():
    await init_db()
    print("🚀 Бот запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
