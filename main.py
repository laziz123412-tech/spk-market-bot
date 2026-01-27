from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
import os

TOKEN = os.getenv("8357008524:AAHcEzn5gyBeMeaS5sPIoCR1ukPU2TUD9mA")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Assalomu alaykum!\n\n"
        "🤖 SPK Market bot ishga tushdi.\n"
        "💰 Cashback tizimi tayyorlanmoqda."
    )

def main():
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.run_polling()

if name == "__main__":
    main()