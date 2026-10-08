import os
import re
import html
import random
import logging
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
CIZIQ = "━━━━━━━━━━━━━━"

# kalit: (ko'rinadigan nom, chiqish ehtimoli)
# Kalitlar bazadagi eski personajlar bilan mos qolishi uchun o'zgarmadi
NODIRLIK = {
    "common": ("✨ Yaxshi", 60),
    "rare": ("💎 Ajoyib", 25),
    "epic": ("🏆 Super", 10),
    "legendary": ("👑 Mega", 5),
}

# /yuklash da yoziladigan nomlar (eski nomlar ham ishlaydi)
NODIRLIK_NOMLARI = {
    "yaxshi": "common",
    "ajoyib": "rare",
    "super": "epic",
    "mega": "legendary",
    "oddiy": "common",
    "nodir": "rare",
    "epik": "epic",
    "afsonaviy": "legendary",
}

# Guruhda chiqqanda ko'rinadigan sarlavhalar
SARLAVHA = {
    "common": "🌸 YANGI PERSONAJ CHIQDI! 🌸",
    "rare": "💎 AJOYIB PERSONAJ CHIQDI! 💎",
    "epic": "⚡ SUPER PERSONAJ CHIQDI! ⚡",
    "legendary": "🔥👑 MEGA PERSONAJ CHIQDI! 👑🔥",
}

# Daraja yulduzlari va ramka belgisi
YULDUZ = {"common": 1, "rare": 2, "epic": 3, "legendary": 4}
RAMKA = {
    "common": "┈",
    "rare": "◈",
    "epic": "❖",
    "legendary": "✦",
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
def e(matn):
    # HTML belgilarini xavfsiz qilish
    return html.escape(str(matn))


def nodirlik_kaliti(matn):
    matn = matn.lower().strip()
    matn = NODIRLIK_NOMLARI.get(matn, matn)
    return matn if matn in NODIRLIK else None


def nodirlik_belgisi(p):
    kalit = p["rarity"].lower()
    return NODIRLIK[kalit][0] if kalit in NODIRLIK else p["rarity"]


def kartochka(p, sarlavha):
    kalit = p["rarity"].lower()
    soni = YULDUZ.get(kalit, 1)
    yulduz = "★" * soni + "☆" * (4 - soni)
    chiziq = RAMKA.get(kalit, "─") * 12
    kod = str(p["_id"])[-4:].upper()
    return (
        f"{sarlavha}\n"
        f"{chiziq}\n"
        f"<blockquote>"
        f"👤 <b>Ism:</b> {e(p['name'])}\n"
        f"📺 <b>Anime:</b> <i>{e(p['anime'])}</i>\n"
        f"💎 <b>Nodirlik:</b> {nodirlik_belgisi(p)}\n"
        f"🌟 <b>Daraja:</b> {yulduz}\n"
        f"🆔 <b>Kod:</b> <code>#{kod}</code>"
        f"</blockquote>\n"
        f"{chiziq}"
    )


def kolleksiya_tugmasi():
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(
            "🖼 Kolleksiyani ko'rish",
            switch_inline_query_current_chat="",
        )
    ]])


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
    matn = (
        f"✨{CIZIQ}✨\n"
        f"🌸 <b>WAIFU BOTGA XUSH KELIBSIZ!</b> 🌸\n"
        f"✨{CIZIQ}✨\n\n"
        f"👋 Salom, <b>{e(f.first_name)}</b>!\n"
        f"👥 Botda <b>{jami}</b> ta foydalanuvchi bor\n\n"
        f"📜 <b>Buyruqlar:</b>\n"
        f"🔹 /topish <i>ism</i> — personajni topish\n"
        f"🔹 /kolleksiya — mening kolleksiyam\n"
        f"🔹 /id — Telegram ID raqamim\n\n"
        f"🎴 Botni guruhga qo'shing va personajlarni yig'ing!"
    )
    await update.message.reply_text(matn, parse_mode="HTML")


async def id_korsat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"🆔 Sizning ID: <code>{update.effective_user.id}</code>",
        parse_mode="HTML",
    )


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
            "Nodirlik: Yaxshi, Ajoyib, Super yoki Mega"
        )
        return
    ism, anime, nodirlik = qismlar
    kalit = nodirlik_kaliti(nodirlik)
    if not kalit:
        await xabar.reply_text(
            "Nodirlik: Yaxshi, Ajoyib, Super yoki Mega bo'lishi kerak."
        )
        return
    await personajlar.insert_one({
        "name": ism, "anime": anime, "rarity": kalit,
        "file_id": xabar.photo[-1].file_id,
    })
    jami = await personajlar.count_documents({})
    await xabar.reply_text(
        f"✅ <b>{e(ism)}</b> ({NODIRLIK[kalit][0]}) qo'shildi!\n"
        f"🎴 Jami personaj: <b>{jami}</b>",
        parse_mode="HTML",
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
    sarlavha = SARLAVHA.get(p["rarity"].lower(), "🌸 YANGI PERSONAJ CHIQDI! 🌸")
    await context.bot.send_photo(
        chat_id, p["file_id"],
        caption=(
            f"✨{CIZIQ}✨\n"
            f"<b>{sarlavha}</b>\n"
            f"✨{CIZIQ}✨\n\n"
            f"💬 Ismini toping:\n"
            f"👉 <code>/topish ism</code>"
        ),
        parse_mode="HTML",
    )


async def topish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if not context.args:
        await update.message.reply_text("💬 Ism yozing: /topish ism")
        return
    chiqqan = await chiqqanlar.find_one({"_id": chat_id})
    if not chiqqan:
        await update.message.reply_text("🔍 Hozir topiladigan personaj yo'q.")
        return
    p = await personajlar.find_one({"_id": chiqqan["char_id"]})
    javob = " ".join(context.args).lower().strip()
    toliq_ism = p["name"].lower()
    if javob == toliq_ism or javob in toliq_ism.split():
        await chiqqanlar.delete_one({"_id": chat_id})
        f = update.effective_user
        await kolleksiya.insert_one({"user_id": f.id, "char_id": p["_id"]})
        matn = (
            kartochka(p, "🎉 <b>TABRIKLAYMAN!</b> 🎉")
            + f"\n✅ <b>{e(f.first_name)}</b>, personaj kolleksiyangizga qo'shildi!"
        )
        await update.message.reply_photo(
            p["file_id"], caption=matn, parse_mode="HTML",
            reply_markup=kolleksiya_tugmasi(),
        )
    else:
        await update.message.reply_text(
            "❌ <b>Noto'g'ri!</b> Qayta urinib ko'ring 🔁",
            parse_mode="HTML",
        )


async def kolleksiyam(update: Update, context: ContextTypes.DEFAULT_TYPE):
    f = update.effective_user
    idlar = [d["char_id"] async for d in kolleksiya.find({"user_id": f.id})]
    if not idlar:
        await update.message.reply_text(
            "📭 Kolleksiyangiz hozircha bo'sh.\n"
            "Guruhda personajni topib, kolleksiyani boshlang!"
        )
        return
    sanash = {}
    for pid in idlar:
        sanash[pid] = sanash.get(pid, 0) + 1
    tartib = list(NODIRLIK)[::-1]  # Megadan boshlab
    royxat = [
        p async for p in personajlar.find({"_id": {"$in": list(sanash)}})
    ]
    royxat.sort(
        key=lambda p: tartib.index(p["rarity"].lower())
        if p["rarity"].lower() in tartib else 99
    )
    qatorlar = []
    for i, p in enumerate(royxat[:40], 1):
        belgi = nodirlik_belgisi(p).split()[0]
        qatorlar.append(
            f"{i}. {belgi} <b>{e(p['name'])}</b> "
            f"<i>({e(p['anime'])})</i> ×{sanash[p['_id']]}"
        )
    matn = (
        f"📚 <b>{e(f.first_name)} KOLLEKSIYASI</b>\n"
        f"{CIZIQ}\n"
        f"🎴 Jami: <b>{len(idlar)}</b> ta | "
        f"Turli: <b>{len(royxat)}</b> xil\n"
        f"{CIZIQ}\n"
        + "\n".join(qatorlar)
    )
    await update.message.reply_text(
        matn, parse_mode="HTML", reply_markup=kolleksiya_tugmasi()
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
                caption=kartochka(p, "🌸 <b>PERSONAJ</b> 🌸"),
                parse_mode="HTML",
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
