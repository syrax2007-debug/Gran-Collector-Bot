import os
import logging
import dns.asyncresolver
from pymongo import AsyncMongoClient
from telegram import Update
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    ContextTypes, filters,
)

logging.basicConfig(level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)

resolver = dns.asyncresolver.Resolver(configure=False)
resolver.nameservers = ["8.8.8.8", "1.1.1.1"]
dns.asyncresolver.default_resolver = resolver

ADMIN_ID = 0  # 2-qadamda o'zingizning ID'ingizni yozasiz

client = AsyncMongoClient(os.environ["MONGO_URI"])
db = client["waifu"]
users = db["users"]
chars = db["characters"]


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    await users.update_one(
        {"_id": u.id}, {"$set": {"name": u.first_name}}, upsert=True
    )
    total = await users.count_documents({})
    await update.message.reply_text(
        f"Salom, {u.first_name}! Botda {total} ta foydalanuvchi bor 🌸"
    )


async def my_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"Sizning ID: {update.effective_user.id}")


async def upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if update.effective_user.id != ADMIN_ID:
        return
    text = (msg.caption or "").replace("/upload", "", 1).strip()
    parts = [p.strip() for p in text.split("|")]
    if len(parts) != 3 or not all(parts):
        await msg.reply_text(
            "Rasm yuboring, izohga yozing:\n/upload Ism | Anime | Nodirlik"
        )
        return
    name, anime, rarity = parts
    await chars.insert_one({
        "name": name, "anime": anime, "rarity": rarity,
        "file_id": msg.photo[-1].file_id,
    })
    total = await chars.count_documents({})
    await msg.reply_text(f"✅ {name} qo'shildi. Jami personaj: {total}")


app = ApplicationBuilder().token(os.environ["BOT_TOKEN"]).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("id", my_id))
app.add_handler(
    MessageHandler(filters.PHOTO & filters.CaptionRegex(r"^/upload"), upload)
)
app.run_polling()
