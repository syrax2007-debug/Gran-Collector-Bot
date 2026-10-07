import os
import logging
import dns.asyncresolver
from pymongo import AsyncMongoClient
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

logging.basicConfig(level=logging.INFO)

resolver = dns.asyncresolver.Resolver(configure=False)
resolver.nameservers = ["8.8.8.8", "1.1.1.1"]
dns.asyncresolver.default_resolver = resolver

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
