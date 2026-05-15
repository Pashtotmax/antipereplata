from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
import asyncio
import os
from datetime import datetime, timedelta
import aiosqlite
import aiohttp

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

# Реальный поиск Wildberries
async def search_products(query: str):
    results = []
    try:
        async with aiohttp.ClientSession() as session:
            url = f"https://search.wb.ru/exactmatch/ru/common/v4/search?query={query.replace(' ', '+')}&limit=10"
            async with session.get(url, timeout=10) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    products = data.get('data', {}).get('products', [])[:6]
                    for p in products:
                        name = p.get('name', 'Товар')
                        price = p.get('salePriceU', 0) // 100
                        if price > 0:
                            results.append(f"{name[:70]}...\n💰 {price} ₽")
    except:
        pass
    
    if not results:
        results = ["Ничего не найдено. Попробуй другой запрос (айфон 15, пуховик, power bank)"]
    return results

@dp.message(Command("start"))
async def start(message: types.Message):
    await init_db()
    await message.answer("👋 Добро пожаловать в <b>Антипереплата</b>!\n\nИщем реальные выгодные цены.", 
                        reply_markup=main_menu, parse_mode="HTML")

@dp.message(F.text == "🔍 Поиск товара")
async def search_request(message: types.Message):
    await message.answer("Напиши, что хочешь купить:\nПример: айфон 15, пуховик, power bank, зимние сапоги")

@dp.message()
async def handle_search(message: types.Message):
    if len(message.text) < 3:
        return

    await message.answer("🔍 Ищу лучшие предложения...")

    results = await search_products(message.text)

    async with aiosqlite.connect('users.db') as db:
        async with db.execute("SELECT subscribed_until FROM users WHERE user_id = ?", 
                            (message.from_user.id,)) as cursor:
            row = await cursor.fetchone()
    
    is_premium = row and row[0] and datetime.fromisoformat(row[0]) > datetime.now() if row and row[0] else False

    text = f"<b>🔍 Результаты по запросу:</b> {message.text}\n\n"

    for i, item in enumerate(results[:3], 1):
        if is_premium or i == 1:
            text += f"{i}️⃣ {item}\n\n"
        else:
            text += f"{i}️⃣ |||||||||||||||||| (заблюрено)\n\n"

    if not is_premium:
        text += "🔒 Полные результаты — только по подписке 0.99$/мес"

    await message.answer(text, parse_mode="HTML")

# Подписка
@dp.message(F.text == "💎 Купить подписку 0.99$")
async def buy_subscription(message: types.Message):
    prices = [types.LabeledPrice(label="Подписка 30 дней", amount=99)]
    await bot.send_invoice(
        chat_id=message.chat.id,
        title="Подписка «Антипереплата»",
        description="Неограниченный поиск + все цены",
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
    async with aiosqlite.connect('users.db') as db:
        await db.execute("INSERT OR REPLACE INTO users (user_id, subscribed_until) VALUES (?, ?)", 
                        (message.from_user.id, until))
        await db.commit()
    await message.answer("🎉 Подписка активирована!")

async def main():
    await init_db()
    print("🚀 Бот успешно запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
