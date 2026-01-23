from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

TOKEN = "8525377529:AAENNtX_FHfQ6v6Y_WgVrsIpe32nhKnhqfo"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Bot ishlayapti ✅")

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    print("Bot ishga tushdi")
    app.run_polling()

if __name__ == "main":
    main()
