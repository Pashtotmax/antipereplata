from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
import asyncio
import os
from datetime import datetime, timedelta
import aiosqlite
import aiohttp
import traceback
from collections import defaultdict

TOKEN = os.getenv("TOKEN")
AI_API_KEY = os.getenv("AI_API_KEY")
ADMIN_ID = 123456789  # ←←← ИЗМЕНИ НА СВОЙ TELEGRAM ID !!!

bot = Bot(token=TOKEN)
dp = Dispatcher()

# Хранилище контекста и режима
user_context = defaultdict(list)
user_mode = defaultdict(lambda: "normal")  # "normal" или "roleplay"
roleplay_exit_counter = defaultdict(int)   # Счётчик просьб выйти из роли

# ===================== БАЗА =====================
async def init_db():
    async with aiosqlite.connect('psychology.db') as db:
        await db.execute('''CREATE TABLE IF NOT EXISTS users
                           (user_id INTEGER PRIMARY KEY,
                            subscribed_until TEXT,
                            messages_today INTEGER DEFAULT 0,
                            last_reset TEXT,
                            gender TEXT DEFAULT NULL)''')
        
        await db.execute('''CREATE TABLE IF NOT EXISTS history
                           (id INTEGER PRIMARY KEY AUTOINCREMENT,
                            user_id INTEGER,
                            date TEXT,
                            user_message TEXT,
                            bot_response TEXT)''')
        await db.commit()

main_menu = ReplyKeyboardMarkup(keyboard=[
    [KeyboardButton(text="💎 Купить подписку за 99⭐")],
    [KeyboardButton(text="📖 Разбор ситуации")],
    [KeyboardButton(text="🎭 Ролевая игра")],
    [KeyboardButton(text="📜 Моя история")],
    [KeyboardButton(text="🧪 Пройти тест")],
], resize_keyboard=True)

# ===================== AI =====================
async def ask_grok(prompt: str):
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api.x.ai/v1/chat/completions",
                headers={"Authorization": f"Bearer {AI_API_KEY}", "Content-Type": "application/json"},
                json={"model": "grok-4", "messages": [{"role": "user", "content": prompt}], "temperature": 0.85, "max_tokens": 950},
                timeout=45
            ) as resp:
                if resp.status != 200:
                    return "Давай чуть позже, сейчас немного тяжело."
                data = await resp.json()
                return data['choices'][0]['message']['content']
    except Exception as e:
        print("AI ERROR:", str(e))
        return "Извини, давай попробуем через минуту."

# ===================== ВСПОМОГАТЕЛЬНЫЕ =====================
async def save_to_history(user_id: int, user_msg: str, bot_msg: str):
    async with aiosqlite.connect('psychology.db') as db:
        await db.execute("INSERT INTO history (user_id, date, user_message, bot_response) VALUES (?, ?, ?, ?)",
                        (user_id, datetime.now().isoformat(), user_msg, bot_msg))
        await db.commit()

async def get_opposite_gender(user_id: int, message_text: str):
    async with aiosqlite.connect('psychology.db') as db:
        async with db.execute("SELECT gender FROM users WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            if row and row[0]:
                return row[0]

    text_lower = message_text.lower()
    if any(word in text_lower for word in ["я девушка", "я женщина", "я девочка", "подруга"]):
        gender = "male"
    elif any(word in text_lower for word in ["я парень", "я мужчина", "я мужик", "я юноша"]):
        gender = "female"
    else:
        gender = None

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
    user_id = message.from_user.id
    user_context[user_id].clear()
    user_mode[user_id] = "normal"
    roleplay_exit_counter[user_id] = 0
    await message.answer(
        "Привет! Я здесь, чтобы помочь тебе с отношениями и чувствами ❤️\n\n"
        "Пиши мне всё, что на душе.",
        reply_markup=main_menu
    )

# ===================== КРАСИВАЯ ПОДПИСКА (7 ДНЕЙ) =====================
@dp.message(F.text == "💎 Купить подписку за 99⭐")
async def buy_subscription(message: types.Message):
    await message.answer_photo(
        photo="https://i.imgur.com/OiaFA.jpg",
        caption="<b>❤️ Специальное предложение для тебя</b>\n\n"
                "Подписка <b>«Близкий Психолог»</b>\n\n"
                "• 150 сообщений каждый день\n"
                "• Я всегда на твоей стороне\n"
                "• Глубокие и честные разговоры\n"
                "• Автоматическое продление\n\n"
                "Всего за <b>99 Telegram Stars</b> в месяц — меньше, чем чашка кофе ☕\n\n"
                "Готов открыть сердце и получить настоящую поддержку?",
        parse_mode="HTML"
    )
    
    prices = [types.LabeledPrice(label="Подписка на 7 дней", amount=99)]
    await bot.send_invoice(
        chat_id=message.chat.id,
        title="❤️ Подписка «Близкий Психолог»",
        description="150 сообщений в сутки • Полная поддержка • Автопродление",
        payload="weekly_sub",
        provider_token="",           # Для Stars — пустой
        currency="XTR",
        prices=prices,
        start_parameter="sub"
    )

# ===================== УСПЕШНАЯ ОПЛАТА =====================
@dp.message(F.successful_payment)
async def successful_payment(message: types.Message):
    until = (datetime.now() + timedelta(days=7)).isoformat()
    async with aiosqlite.connect('psychology.db') as db:
        await db.execute("INSERT OR REPLACE INTO users (user_id, subscribed_until) VALUES (?, ?)",
                        (message.from_user.id, until))
        await db.commit()
    await message.answer("✅ Подписка успешно активирована!\nТеперь у тебя 150 сообщений в сутки на 7 дней ❤️")

# ===================== ОСТАЛЬНЫЕ КНОПКИ =====================
@dp.message(F.text == "📖 Разбор ситуации")
async def situation_analysis(message: types.Message):
    await message.answer("Хорошо, давай разберёмся ❤️\n\nОпиши ситуацию своими словами или пришли текст переписки.")

@dp.message(F.text == "🎭 Ролевая игра")
async def role_play(message: types.Message):
    user_mode[message.from_user.id] = "roleplay"
    roleplay_exit_counter[message.from_user.id] = 0
    await message.answer("Хорошо, давай поиграем ❤️\nНапиши, в какой роли ты хочешь меня видеть.")

@dp.message(F.text == "📜 Моя история")
async def show_history(message: types.Message):
    async with aiosqlite.connect('psychology.db') as db:
        async with db.execute("SELECT date, user_message, bot_response FROM history WHERE user_id = ? ORDER BY id DESC LIMIT 5",
                            (message.from_user.id,)) as cursor:
            rows = await cursor.fetchall()
    if not rows:
        await message.answer("Пока нет сохранённых разговоров.")
        return
    text = "📜 Последние 5 разговоров:\n\n"
    for date, user_msg, bot_msg in rows:
        text += f"📅 {date[:10]}\nТы: {user_msg[:80]}...\nЯ: {bot_msg[:80]}...\n\n"
    await message.answer(text)

@dp.message(F.text == "🧪 Пройти тест")
async def tests(message: types.Message):
    await message.answer(
        "🧪 Выбери тест, который хочешь пройти:\n\n"
        "1️⃣ **Стиль привязанности** (самый популярный)\n"
        "2️⃣ **Готовность к серьёзным отношениям**\n\n"
        "Напиши цифру 1 или 2."
    )

# ===================== ГОЛОСОВЫЕ =====================
@dp.message(F.voice)
async def voice_handler(message: types.Message):
    await message.answer("Я услышал твой голос ❤️\n\nЛучше пиши текстом — так я точнее тебя понимаю.")

# ===================== ОСНОВНОЙ ЧАТ =====================
@dp.message()
async def ai_psychologist(message: types.Message):
    user_id = message.from_user.id

    can_send, remaining = await can_send_message(user_id)
    if not can_send:
        await message.answer(
            "Сегодня ты уже использовал все бесплатные сообщения.\n\n"
            "Оформи подписку за 99⭐, чтобы продолжить общение (150 сообщений в сутки).",
            reply_markup=main_menu
        )
        return

    # Добавляем в контекст
    user_context[user_id].append(f"Пользователь: {message.text}")
    if len(user_context[user_id]) > 8:
        user_context[user_id].pop(0)

    context_str = "\n".join(user_context[user_id][-8:])

    user_gender = await get_opposite_gender(user_id, message.text)
    role = "мужчина" if user_gender == "female" else "женщина" if user_gender == "male" else "человек"

    async with aiosqlite.connect('psychology.db') as db:
        await db.execute("UPDATE users SET messages_today = messages_today + 1 WHERE user_id = ?", (user_id,))
        await db.commit()

    thinking = await message.answer("Пишу...")

    # ==================== РЕЖИМ РОЛЕВОЙ ИГРЫ ====================
    if user_mode[user_id] == "roleplay":
        prompt = f"""Ты — {role}, игривый, тёплый и немного страстный человек противоположного пола.
Говори живо, с лёгким флиртом и эмоциями, но не переигрывай, если тебя не просят.
Пользователь написал: "{message.text}"
Продолжай ролевую игру естественно."""

        # Проверка на выход из роли
        lower = message.text.lower()
        if any(word in lower for word in ["хватит", "стоп", "выходи", "обычный режим", "перестань", "достаточно", "нормально"]):
            roleplay_exit_counter[user_id] += 1
            if roleplay_exit_counter[user_id] >= 2:
                user_mode[user_id] = "normal"
                roleplay_exit_counter[user_id] = 0
                await message.answer("Хорошо, выходим из роли ❤️ Теперь я снова обычный поддерживающий собеседник.")
            else:
                await message.answer("Ты точно хочешь выйти из роли? Напиши ещё раз, если да.")
        else:
            roleplay_exit_counter[user_id] = 0

    else:
        # Обычный режим — мягкий и рассудительный
        prompt = f"""Ты — {role}, мягкий, внимательный и понимающий человек противоположного пола.
Говори спокойно, рассудительно, искренне и с теплом.
Хорошо помни контекст разговора.
Пользователь написал: "{message.text}"
Предыдущий контекст: {context_str}
Ответь мягко, рассудительно и поддерживающе."""

    response = await ask_grok(prompt)
 
    await thinking.delete()
    await message.answer(response)

    await save_to_history(user_id, message.text, response)

    # Обновляем контекст
    user_context[user_id].append(f"Ты: {response}")
    if len(user_context[user_id]) > 10:
        user_context[user_id].pop(0)

    # Авто-предложения
    lower_text = message.text.lower()
    if any(word in lower_text for word in ["поссори", "ругал", "конфликт", "проблема", "обидел", "ссора"]):
        await message.answer("Хочешь подробно разобрать эту ситуацию? Напиши «Разбор ситуации»")

    if any(word in lower_text for word in ["представь", "роль", "поиграем", "как будто", "давай сыграем"]):
        user_mode[user_id] = "roleplay"
        roleplay_exit_counter[user_id] = 0
        await message.answer("Хорошо, давай поиграем ❤️\nНапиши, в какой роли ты хочешь меня видеть.")

async def main():
    await init_db()
    print("🚀 AI Психолог Отношений запущен!")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
