import os
from pymongo import AsyncMongoClient
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

client = AsyncMongoClient(os.environ["MONGO_URI"])
users = client["waifu"]["users"]

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    await users.update_one(
        {"_id": u.id}, {"$set": {"name": u.first_name}}, upsert=True
    )
    total = await users.count_documents({})
    await update.message.reply_text(
        f"Salom, {u.first_name}! Botda {total} ta foydalanuvchi bor 🌸"
    )

app = ApplicationBuilder().token(os.environ["BOT_TOKEN"]).build()
app.add_handler(CommandHandler("start", start))
app.run_polling()
