import os
import random
import logging
from collections import Counter
import dns.asyncresolver
from pymongo import AsyncMongoClient
from telegram import Update, InlineQueryResultCachedPhoto
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    InlineQueryHandler, ContextTypes, filters,
)

logging.basicConfig(level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)

resolver = dns.asyncresolver.Resolver(configure=False)
resolver.nameservers = ["8.8.8.8", "1.1.1.1"]
dns.asyncresolver.default_resolver = resolver

ADMIN_ID = 8288620037  # o'zingizning ID raqamingiz
SPAWN_EVERY = 10  # nechta xabardan keyin personaj chiqadi

client = AsyncMongoClient(os.environ["MONGO_URI"])
db = client["waifu"]
users = db["users"]
chars = db["characters"]
spawns = db["spawns"]
collection = db["collection"]
counters = {}


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    await users.update_one(
        {"_id": u.id}, {"$set": {"name": u.first_name}}, upsert=True
    )
    total = await users.count_documents({})
    await update.message.reply_text(
        f"Salom, {u.first_name}! Botda {total} ta foydalanuvchi bor 🌸"
    )


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


async def count_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    counters[chat_id] = counters.get(chat_id, 0) + 1
    if counters[chat_id] < SPAWN_EVERY:
        return
    counters[chat_id] = 0
    total = await chars.count_documents({})
    if total == 0:
        return
    c = await chars.find_one({}, skip=random.randrange(total))
    await spawns.update_one(
        {"_id": chat_id}, {"$set": {"char_id": c["_id"]}}, upsert=True
    )
    await context.bot.send_photo(
        chat_id, c["file_id"],
        caption="🌸 Yangi personaj chiqdi!\nIsmini topish uchun: /guess ism",
    )


async def guess(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if not context.args:
        await update.message.reply_text("Ism yozing: /guess ism")
        return
    sp = await spawns.find_one({"_id": chat_id})
    if not sp:
        await update.message.reply_text("Hozir topiladigan personaj yo'q.")
        return
    c = await chars.find_one({"_id": sp["char_id"]})
    answer = " ".join(context.args).lower().strip()
    full = c["name"].lower()
    if answer == full or answer in full.split():
        await spawns.delete_one({"_id": chat_id})
        u = update.effective_user
        await collection.insert_one({"user_id": u.id, "char_id": c["_id"]})
        await update.message.reply_text(
            f"✅ To'g'ri! {u.first_name}, {c['name']} ({c['anime']}) "
            f"kolleksiyangizga qo'shildi."
        )
    else:
        await update.message.reply_text("❌ Noto'g'ri, qayta urinib ko'ring.")


async def harem(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    ids = [d["char_id"] async for d in collection.find({"user_id": u.id})]
    if not ids:
        await update.message.reply_text("Kolleksiyangiz hozircha bo'sh.")
        return
    lines = []
    for cid, n in list(Counter(ids).items())[:50]:
        c = await chars.find_one({"_id": cid})
        lines.append(f"• {c['name']} ({c['anime']}) x{n}")
    await update.message.reply_text(
        f"🌸 {u.first_name} kolleksiyasi:\n" + "\n".join(lines)
    )

async def inline(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.inline_query
    text = q.query.strip().lower()
    ids = [d["char_id"] async for d in collection.find({"user_id": q.from_user.id})]
    results = []
    async for c in chars.find({"_id": {"$in": list(set(ids))}}):
        if text and text not in c["name"].lower():
            continue
        results.append(
            InlineQueryResultCachedPhoto(
                id=str(c["_id"]),
                photo_file_id=c["file_id"],
                caption=f"🌸 {c['name']}\n{c['anime']} | {c['rarity']}",
            )
        )
        if len(results) >= 50:
            break
    await q.answer(results, cache_time=5, is_personal=True)

app = ApplicationBuilder().token(os.environ["BOT_TOKEN"]).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("guess", guess))
app.add_handler(CommandHandler("harem", harem))
app.add_handler(
    MessageHandler(filters.PHOTO & filters.CaptionRegex(r"^/upload"), upload)
)
app.add_handler(
    MessageHandler(filters.ChatType.GROUPS & ~filters.COMMAND, count_messages)
)
app.add_handler(InlineQueryHandler(inline))
app.run_polling()
