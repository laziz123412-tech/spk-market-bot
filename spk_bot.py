import os
import random
from aiogram import Bot, Dispatcher, executor, types

TOKEN = os.getenv("BOT_TOKEN")

bot = Bot(token=TOKEN)
dp = Dispatcher(bot)

@dp.message_handler(commands=["start"])
async def start_cmd(message: types.Message):
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("🇺🇿 O‘zbekcha", "🇷🇺 Русский")
    await message.answer(
        "Tilni tanlang / Выберите язык",
        reply_markup=kb
    )

@dp.message_handler(lambda m: m.text in ["🇺🇿 O‘zbekcha", "🇷🇺 Русский"])
async def lang_select(message: types.Message):
    await message.answer("Xarid summasini yozing:")

@dp.message_handler(lambda m: m.text.isdigit())
async def cashback_calc(message: types.Message):
    summa = int(message.text)
    percent = random.randint(1, 10)
    cashback = summa * percent // 100
    await message.answer(
        f"Cashback: {percent}%\nQaytadi: {cashback} so‘m"
    )

if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)
