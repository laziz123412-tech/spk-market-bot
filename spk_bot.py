import random
from aiogram import Bot, Dispatcher, executor, types

TOKEN = "KEYIN_QO'YAMIZ"
ADMIN_ID = 0

bot = Bot(token=TOKEN)
dp = Dispatcher(bot)

@dp.message_handler(commands=['start'])
async def start(message: types.Message):
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("🇺🇿 O‘zbekcha", "🇷🇺 Русский")
    await message.answer(
        "Tilni tanlang / Выберите язык",
        reply_markup=kb
    )

@dp.message_handler(lambda m: m.text in ["🇺🇿 O‘zbekcha", "🇷🇺 Русский"])
async def lang(message: types.Message):
    await message.answer(
        "SPK Market Cashback Bot\n\n"
        "Xarid summasini yozing:",
        reply_markup=types.ReplyKeyboardRemove()
    )

@dp.message_handler()
async def cashback(message: types.Message):
    if not message.text.isdigit():
        return

    summa = int(message.text)
    foiz = random.randint(1, 10)
    cashback = summa * foiz // 100

    await message.answer(
        f"Xarid: {summa} so‘m\n"
        f"Cashback: {foiz}%\n"
        f"Qaytadi: {cashback} so‘m"
    )

if __name__ == "__main__":
    executor.start_polling(dp)
