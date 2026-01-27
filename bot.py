import random
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

TOKEN = "8357008524:AAHcEzn5gyBeMeaS5sPIoCR1ukPU2TUD9mA"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Assalomu alaykum!\n\n"
        "💰 Xarid summasini yozing, men cashbackni avtomatik hisoblayman."
    )

async def cashback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        summa = int(update.message.text)
        foiz = random.randint(1, 5)
        cashback_sum = summa * foiz // 100

        await update.message.reply_text(
            f"🧮 Xarid: {summa} so‘m\n"
            f"🎯 Cashback foizi: {foiz}%\n"
            f"💸 Cashback: {cashback_sum} so‘m"
        )
    except:
        await update.message.reply_text("❌ Iltimos, faqat raqam yozing.")

app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("cashback", cashback))

app.run_polling()