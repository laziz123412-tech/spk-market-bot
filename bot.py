import os
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from flask import Flask, request

TOKEN = "8525377529:AAENNtX_FHfQ6v6Y_WgVrsIpe32nhKnhqfo"
PORT = int(os.environ.get("PORT", 8080))

app = Flask(__name__)
bot_app = Application.builder().token(TOKEN).build()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✅ Bot ishlayapti!")

bot_app.add_handler(CommandHandler("start", start))

@app.route("/", methods=["POST"])
def webhook():
    update = Update.de_json(request.get_json(force=True), bot_app.bot)
    bot_app.update_queue.put_nowait(update)
    return "ok"

if __name__ == "main":
    bot_app.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        webhook_url="https://SENING-PROJECT-NOMI.up.railway.app"
    )
