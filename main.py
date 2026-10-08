import os
import re
import random
import logging
from collections import Counter
import dns.asyncresolver
from pymongo import AsyncMongoClient
from telegram import (
    Update, InlineQueryResultCachedPhoto,
    InlineKeyboardButton, InlineKeyboardMarkup,
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    InlineQueryHandler, ContextTypes, filters,
)

# Xatolarni ko'rish uchun jurnal
logging.basicConfig(level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)

# Termux uchun DNS sozlamasi
resolver = dns.asyncresolver.Resolver(configure=False)
resolver.nameservers = ["8.8.8.8", "1.1.1.1"]
dns.asyncresolver.default_resolver = resolver

# ---------- Sozlamalar ----------
ADMIN_ID = 8288620037  # o'zingizning Telegram ID raqamingiz
CHIQISH_ORALIGI = 10  # nechta xabardan keyin personaj chiqadi

# kalit: (ko'rinadigan nom, chiqish ehtimoli)
NODIRLIK = {
    "common": ("☀️ Yaxshi", 60),
    "rare": ("✨ Ajoyib", 25),
    "epic": ("🏆 Super", 10),
    "legendary": ("👑 Mega", 5),
}

# /yuklash da yoziladigan nomlar
NODIRLIK_NOMLARI = {
    "oddiy": "common",
    "nodir": "rare",
    "epik": "epic",
    "afsonaviy": "legendary",
}

# ---------- Baza ----------
mijoz = AsyncMongoClient(os.environ["MONGO_URI"])
baza = mijoz["waifu"]
foydalanuvchilar = baza["users"]
personajlar = baza["characters"]
chiqqanlar = baza["spawns"]
kolleksiya = baza["collection"]
hisoblagich = {}


# ---------- Yordamchi funksiyalar ----------
def nodirlik_kaliti(matn):
    matn = matn.lower().strip()
    matn = NODIRLIK_NOMLARI.get(matn, matn)
    return matn if matn in NODIRLIK else None


def nodirlik_belgisi(p):
    kalit = p["rarity"].lower()
    return NODIRLIK[kalit][0] if kalit in NODIRLIK else p["rarity"]


async def tasodifiy_personaj():
    kalitlar = list(NODIRLIK)
    ehtimollar = [NODIRLIK[k][1] for k in kalitlar]
    for _ in range(10):
        kalit = random.choices(kalitlar, ehtimollar)[0]
        shart = {"rarity": {"$in": [kalit, kalit.capitalize()]}}
        soni = await personajlar.count_documents(shart)
        if soni:
            return await personajlar.find_one(
                shart, skip=random.randrange(soni)
            )
    jami = await personajlar.count_documents({})
    if jami == 0:
        return None
    return await personajlar.find_one({}, skip=random.randrange(jami))


# ---------- Buyruqlar ----------
async def boshlash(update: Update, context: ContextTypes.DEFAULT_TYPE):
    f = update.effective_user
    await foydalanuvchilar.update_one(
        {"_id": f.id}, {"$set": {"name": f.first_name}}, upsert=True
    )
    jami = await foydalanuvchilar.count_documents({})
    await update.message.reply_text(
        f"Salom, {f.first_name}! Botda {jami} ta foydalanuvchi bor 🌸"
    )


async def id_korsat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"Sizning ID: {update.effective_user.id}")


async def yuklash(update: Update, context: ContextTypes.DEFAULT_TYPE):
    xabar = update.message
    if update.effective_user.id != ADMIN_ID:
        return
    matn = re.sub(r"^/\w+(@\w+)?", "", xabar.caption or "").strip()
    qismlar = [q.strip() for q in matn.split("|")]
    if len(qismlar) != 3 or not all(qismlar):
        await xabar.reply_text(
            "Rasm yuboring, izohga yozing:\n"
            "/yuklash Ism | Anime | Nodirlik\n"
            "Nodirlik: Oddiy, Nodir, Epik yoki Afsonaviy"
        )
        return
    ism, anime, nodirlik = qismlar
    kalit = nodirlik_kaliti(nodirlik)
    if not kalit:
        await xabar.reply_text(
            "Nodirlik: Oddiy, Nodir, Epik yoki Afsonaviy bo'lishi kerak."
        )
        return
    await personajlar.insert_one({
        "name": ism, "anime": anime, "rarity": kalit,
        "file_id": xabar.photo[-1].file_id,
    })
    jami = await personajlar.count_documents({})
    await xabar.reply_text(
        f"✅ {ism} ({NODIRLIK[kalit][0]}) qo'shildi. Jami: {jami}"
    )


async def xabarlarni_sanash(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    hisoblagich[chat_id] = hisoblagich.get(chat_id, 0) + 1
    if hisoblagich[chat_id] < CHIQISH_ORALIGI:
        return
    hisoblagich[chat_id] = 0
    p = await tasodifiy_personaj()
    if not p:
        return
    await chiqqanlar.update_one(
        {"_id": chat_id}, {"$set": {"char_id": p["_id"]}}, upsert=True
    )
    await context.bot.send_photo(
        chat_id, p["file_id"],
        caption="🌸 Yangi personaj chiqdi!\nIsmini topish uchun: /topish ism",
    )


async def topish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if not context.args:
        await update.message.reply_text("Ism yozing: /topish ism")
        return
    chiqqan = await chiqqanlar.find_one({"_id": chat_id})
    if not chiqqan:
        await update.message.reply_text("Hozir topiladigan personaj yo'q.")
        return
    p = await personajlar.find_one({"_id": chiqqan["char_id"]})
    javob = " ".join(context.args).lower().strip()
    toliq_ism = p["name"].lower()
    if javob == toliq_ism or javob in toliq_ism.split():
        await chiqqanlar.delete_one({"_id": chat_id})
        f = update.effective_user
        await kolleksiya.insert_one({"user_id": f.id, "char_id": p["_id"]})
        await update.message.reply_text(
            f"✅ To'g'ri! {f.first_name}, {p['name']} ({p['anime']})\n"
            f"Nodirlik: {nodirlik_belgisi(p)}\n"
            f"Kolleksiyangizga qo'shildi."
        )
    else:
        await update.message.reply_text("❌ Noto'g'ri, qayta urinib ko'ring.")


async def kolleksiyam(update: Update, context: ContextTypes.DEFAULT_TYPE):
    f = update.effective_user
    idlar = [d["char_id"] async for d in kolleksiya.find({"user_id": f.id})]
    if not idlar:
        await update.message.reply_text("Kolleksiyangiz hozircha bo'sh.")
        return
    qatorlar = []
    for pid, soni in list(Counter(idlar).items())[:50]:
        p = await personajlar.find_one({"_id": pid})
        qatorlar.append(
            f"• {p['name']} ({p['anime']}) {nodirlik_belgisi(p)} x{soni}"
        )
    await update.message.reply_text(
        f"🌸 {f.first_name} kolleksiyasi:\n" + "\n".join(qatorlar)
    )


async def inline_qidiruv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    so_rov = update.inline_query
    matn = so_rov.query.strip().lower()
    idlar = [
        d["char_id"]
        async for d in kolleksiya.find({"user_id": so_rov.from_user.id})
    ]
    natijalar = []
    async for p in personajlar.find({"_id": {"$in": list(set(idlar))}}):
        if matn and matn not in p["name"].lower():
            continue
        natijalar.append(
            InlineQueryResultCachedPhoto(
                id=str(p["_id"]),
                photo_file_id=p["file_id"],
                caption=f"🌸 {p['name']}\n{p['anime']} | {nodirlik_belgisi(p)}",
            )
        )
        if len(natijalar) >= 50:
            break
    await so_rov.answer(natijalar, cache_time=5, is_personal=True)


# ---------- Botni ishga tushirish ----------
ilova = ApplicationBuilder().token(os.environ["BOT_TOKEN"]).build()
ilova.add_handler(CommandHandler("start", boshlash))
ilova.add_handler(CommandHandler("id", id_korsat))
ilova.add_handler(CommandHandler(["topish", "guess"], topish))
ilova.add_handler(CommandHandler(["kolleksiya", "harem"], kolleksiyam))
ilova.add_handler(
    MessageHandler(
        filters.PHOTO & filters.CaptionRegex(r"^/(yuklash|upload)"), yuklash
    )
)
ilova.add_handler(
    MessageHandler(filters.ChatType.GROUPS & ~filters.COMMAND, xabarlarni_sanash)
)
ilova.add_handler(InlineQueryHandler(inline_qidiruv))
ilova.run_polling()
