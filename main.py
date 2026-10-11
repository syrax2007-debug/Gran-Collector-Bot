import os
import re
import html
import random
import asyncio
import logging
from datetime import datetime, timedelta, timezone
import dns.asyncresolver
from bson import ObjectId
from pymongo import AsyncMongoClient
from stil import stil, StilBot
from royxat import (
    raqam_tuzat, keyingi_raqam, kolleksiya_malumot, kolleksiya_izohi,
)
from telegram import (
    Update, InlineQueryResultCachedPhoto,
    InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo,
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    InlineQueryHandler, CallbackQueryHandler, ContextTypes, filters,
)

# Xatolarni ko'rish uchun jurnal
logging.basicConfig(level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)

# DNS sozlamasi
resolver = dns.asyncresolver.Resolver(configure=False)
resolver.nameservers = ["8.8.8.8", "1.1.1.1"]
dns.asyncresolver.default_resolver = resolver

# ---------- Sozlamalar ----------
ADMIN_ID = 0  # o'zingizning Telegram ID raqamingiz
MINI_APP_URL = "https://syrax2007-debug.github.io/Gran-Collector-Bot/"
CHIQISH_ORALIGI = 50  # nechta xabardan keyin personaj chiqadi
RAMKA = "✨━ ━━━━━━━━━ ━✨"
TOSHKENT = timezone(timedelta(hours=5))

# Kanal va rasmiy guruh
KANAL_URL = "https://t.me/Grab_Collector"
GURUH_URL = "https://t.me/Grab_Collector_Chat"
RASMIY_GURUH = "grab_collector_chat"  # kichik harflarda, @ siz

# Bonuslar
XUSH_BONUS_TANGA = 222  # bir martalik bonus: tanga
KUNLIK_BONUS = 50  # kunlik bonus: boshlang'ich miqdor
KUNLIK_QOSHIMCHA = 10  # har bir ketma-ket kun uchun qo'shimcha
KUNLIK_MAKS_SERIYA = 6  # shu kundan keyin o'smaydi (50 + 5x10 = 100)

# Ruletka (🎰)
RULETKA_LIMIT = 3  # kuniga urinishlar soni
RULETKA_JEKPOT = 300  # 7️⃣7️⃣7️⃣
RULETKA_UCHTA = 100  # boshqa uchta bir xil
RULETKA_IKKITA = 15  # ikkita bir xil

# kalit: (ko'rinadigan nom, chiqish ehtimoli)
NODIRLIK = {
    "common": ("🟢 YAXSHI", 60),
    "rare": ("🔵 AJOYIB", 25),
    "epic": ("🟣 SUPER", 10),
    "legendary": ("🔥 MEGA", 5),
    "special": ("💠 MAXSUS", 2),
}

# /yuklash da yoziladigan nomlar (eski nomlar ham ishlaydi)
NODIRLIK_NOMLARI = {
    "yaxshi": "common",
    "ajoyib": "rare",
    "super": "epic",
    "mega": "legendary",
    "maxsus": "special",
    "oddiy": "common",
    "nodir": "rare",
    "epik": "epic",
    "afsonaviy": "legendary",
}

# Daraja yulduzlari (5 tadan). MAXSUS yulduzsiz
YULDUZ = {"common": 1, "rare": 2, "epic": 3, "legendary": 4}

# ---------- Baza ----------
mijoz = AsyncMongoClient(os.environ["MONGO_URI"])
baza = mijoz["waifu"]
foydalanuvchilar = baza["users"]
personajlar = baza["characters"]
chiqqanlar = baza["spawns"]
kolleksiya = baza["collection"]
ruxsatlilar = baza["allowed_chats"]
hisoblagich = {}


# ---------- Yordamchi funksiyalar ----------
def K(matn):
    # HTML uchun xavfsiz qilish (uslubni stil.py o'zi beradi)
    return html.escape(str(matn))


def eslatma(f):
    # Foydalanuvchiga havola (ismi bosiladigan bo'ladi)
    return f'<a href="tg://user?id={f.id}">{K(f.first_name)}</a>'


def bugun():
    return datetime.now(TOSHKENT).strftime("%Y-%m-%d")


def kecha():
    return (datetime.now(TOSHKENT) - timedelta(days=1)).strftime("%Y-%m-%d")


def nodirlik_kaliti(matn):
    matn = matn.lower().strip()
    matn = NODIRLIK_NOMLARI.get(matn, matn)
    return matn if matn in NODIRLIK else None


def nodirlik_belgisi(p):
    kalit = p["rarity"].lower()
    return NODIRLIK[kalit][0] if kalit in NODIRLIK else p["rarity"].upper()


def yulduz_matni(p):
    kalit = p["rarity"].lower()
    if kalit == "special":
        return "✨ MAXSUS ✨"
    soni = YULDUZ.get(kalit, 1)
    return "★" * soni + "☆" * (5 - soni)


def kartochka(p):
    # Inline natijalar uchun qisqa kartochka
    kod = str(p["_id"])[-4:].upper()
    return (
        f"🗽 Ismi : {K(p['name'])}\n"
        f"🎗️ RANK : {yulduz_matni(p)}\n"
        f"👀 Manba : {K(p['anime'])}\n"
        f"🔢 Raqam : {p.get('raqam', '?')} | 🆔 <code>#{kod}</code>"
    )


def mini_app_tugmasi():
    return InlineKeyboardButton(
        stil("🌐 Mini App"), web_app=WebAppInfo(url=MINI_APP_URL)
    )


def kolleksiya_tugmasi(egasi, shaxsiy=False):
    # 1-tugma: bosgan odam O'Z kolleksiyasini ko'radi
    # 2-tugma: boshqalar kolleksiya EGASINING kolleksiyasini ko'radi
    nom = egasi.first_name[:16]
    qatorlar = [
        [InlineKeyboardButton(
            stil("🖼 Mening kolleksiyam"),
            switch_inline_query_current_chat="",
        )],
        [InlineKeyboardButton(
            stil(f"👁 {nom} kolleksiyasi"),
            switch_inline_query_current_chat=f"u{egasi.id}",
        )],
    ]
    if shaxsiy:
        qatorlar.append([mini_app_tugmasi()])
    return InlineKeyboardMarkup(qatorlar)


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


async def bonus_personaji():
    # Avval SUPER (epik), bo'lmasa boshqa darajalardan
    for kalit in ("epic", "rare", "common", "legendary"):
        shart = {"rarity": {"$in": [kalit, kalit.capitalize()]}}
        soni = await personajlar.count_documents(shart)
        if soni:
            return await personajlar.find_one(
                shart, skip=random.randrange(soni)
            )
    return None


# ---------- Ishonchli guruhlar ----------
async def ruxsatli_guruhmi(chat):
    if chat.type not in ("group", "supergroup"):
        return False
    if (chat.username or "").lower() == RASMIY_GURUH:
        return True
    return await ruxsatlilar.find_one({"_id": chat.id}) is not None


async def guruh_tekshir(update: Update):
    # Bonus, kunlik va ruletka faqat ishonchli guruhlarda ishlaydi
    if await ruxsatli_guruhmi(update.effective_chat):
        return True
    await update.message.reply_text(
        f"{RAMKA}\n🚫 Bu buyruq faqat rasmiy guruhda ishlaydi !",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton(stil("💬 Rasmiy guruh"), url=GURUH_URL)
        ]]),
    )
    return False


async def ruxsat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    c = update.effective_chat
    if c.type not in ("group", "supergroup"):
        await update.message.reply_text("❌ Bu buyruq faqat guruhda ishlaydi !")
        return
    await ruxsatlilar.update_one(
        {"_id": c.id}, {"$set": {"title": c.title}}, upsert=True
    )
    await update.message.reply_text("✅ Guruh tasdiqlandi !")


async def ruxsat_ochir(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    await ruxsatlilar.delete_one({"_id": update.effective_chat.id})
    await update.message.reply_text("🛑 Guruh tasdig'i bekor qilindi !")


# ---------- Oddiy buyruqlar ----------
async def boshlash(update: Update, context: ContextTypes.DEFAULT_TYPE):
    f = update.effective_user
    await foydalanuvchilar.update_one(
        {"_id": f.id}, {"$set": {"name": f.first_name}}, upsert=True
    )
    matn = (
        "✨━ ━━━━━━━━━━━━ ━✨\n"
        "💎 WAIFU BOTGA XUSH KELIBSIZ! ✊\n\n"
        f"👋 SALOM, {K(f.first_name)}!\n\n"
        "🌟 BOTNI GURUHGA QO'SHING VA PERSONAJLARNI YIG'ING!\n"
        "✨━ ━ ━ ━ ━ ━ ━ ━ ━ ━ ━ ━ ✨"
    )
    tugma = None
    if update.effective_chat.type == "private":
        tugma = InlineKeyboardMarkup([
            [
                InlineKeyboardButton(stil("📢 Kanal"), url=KANAL_URL),
                InlineKeyboardButton(stil("💬 Guruh"), url=GURUH_URL),
            ],
            [mini_app_tugmasi()],
        ])
    await update.message.reply_text(
        matn, parse_mode="HTML", reply_markup=tugma
    )


async def id_korsat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"🆔 ID : <code>{update.effective_user.id}</code>",
        parse_mode="HTML",
    )


async def balans(update: Update, context: ContextTypes.DEFAULT_TYPE):
    f = update.effective_user
    u = await foydalanuvchilar.find_one({"_id": f.id}) or {}
    await update.message.reply_text(
        f"👛 {K(f.first_name)} : {u.get('coins', 0)} tanga",
        parse_mode="HTML",
    )


# ---------- Bonuslar (faqat ishonchli guruhda) ----------
async def bonus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await guruh_tekshir(update):
        return
    f = update.effective_user
    await foydalanuvchilar.update_one(
        {"_id": f.id}, {"$set": {"name": f.first_name}}, upsert=True
    )
    u = await foydalanuvchilar.find_one({"_id": f.id}) or {}
    if u.get("xush_bonus"):
        await update.message.reply_text("🎁 Bonusni allaqachon olgansiz !")
        return
    p = await bonus_personaji()
    if not p:
        await update.message.reply_text(
            "⚠️ Hozircha bonus waifusi yo'q. Adminga xabar bering."
        )
        return
    r = await foydalanuvchilar.update_one(
        {"_id": f.id, "xush_bonus": {"$ne": True}},
        {"$set": {"xush_bonus": True}, "$inc": {"coins": XUSH_BONUS_TANGA}},
    )
    if r.modified_count == 0:
        await update.message.reply_text("🎁 Bonusni allaqachon olgansiz !")
        return
    await kolleksiya.insert_one({"user_id": f.id, "char_id": p["_id"]})
    matn = (
        f"{RAMKA}\n"
        "🎁 Xush kelibsiz bonusi !\n\n"
        f"🫧 {K(f.first_name)} sovg'a oldi !\n"
        f"🗽 Ismi : {K(p['name'])}\n"
        f"🎗️ RANK : {yulduz_matni(p)}\n"
        f"👀 Manba : {K(p['anime'])}\n"
        f"💰 Tanga : +{XUSH_BONUS_TANGA}\n\n"
        "🫶 Waifularni koring  /kolleksiya!"
    )
    await update.message.reply_photo(
        p["file_id"], caption=matn, parse_mode="HTML",
        reply_markup=kolleksiya_tugmasi(f, False),
    )


async def kunlik(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await guruh_tekshir(update):
        return
    f = update.effective_user
    await foydalanuvchilar.update_one(
        {"_id": f.id}, {"$set": {"name": f.first_name}}, upsert=True
    )
    u = await foydalanuvchilar.find_one({"_id": f.id}) or {}
    b = bugun()
    if u.get("kunlik_sana") == b:
        await update.message.reply_text(
            "⏳ Bugungi bonusni olgansiz. Ertaga qayting !"
        )
        return
    seriya = (u.get("kunlik_seriya", 0) + 1) if u.get("kunlik_sana") == kecha() else 1
    miqdor = KUNLIK_BONUS + KUNLIK_QOSHIMCHA * (
        min(seriya, KUNLIK_MAKS_SERIYA) - 1
    )
    r = await foydalanuvchilar.update_one(
        {"_id": f.id, "kunlik_sana": {"$ne": b}},
        {
            "$set": {"kunlik_sana": b, "kunlik_seriya": seriya},
            "$inc": {"coins": miqdor},
        },
    )
    if r.modified_count == 0:
        await update.message.reply_text(
            "⏳ Bugungi bonusni olgansiz. Ertaga qayting !"
        )
        return
    u = await foydalanuvchilar.find_one({"_id": f.id}) or {}
    await update.message.reply_text(
        f"{RAMKA}\n"
        "📅 Kunlik bonus !\n\n"
        f"🫧 {K(f.first_name)}\n"
        f"🔥 Seriya : {seriya} kun\n"
        f"💰 Tanga : +{miqdor}\n"
        f"👛 Jami : {u.get('coins', 0)}\n\n"
        "🌙 Ertaga qayting, bonus oshadi !",
        parse_mode="HTML",
    )


def ruletka_hisobla(qiymat):
    # 🎰 qiymati 1..64: har bir g'ildirak 0..3 (BAR, uzum, limon, yetti)
    v = qiymat - 1
    g = [v % 4, (v // 4) % 4, v // 16]
    if g[0] == g[1] == g[2]:
        if g[0] == 3:
            return RULETKA_JEKPOT, "Jekpot ! 7️⃣7️⃣7️⃣"
        return RULETKA_UCHTA, "Uchta bir xil !"
    if len(set(g)) == 2:
        return RULETKA_IKKITA, "Ikkita bir xil !"
    return 0, "Bu safar omad kelmadi"


async def ruletka(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await guruh_tekshir(update):
        return
    f = update.effective_user
    b = bugun()
    await foydalanuvchilar.update_one(
        {"_id": f.id}, {"$set": {"name": f.first_name}}, upsert=True
    )
    u = await foydalanuvchilar.find_one({"_id": f.id}) or {}
    ishlatilgan = u.get("ruletka_soni", 0) if u.get("ruletka_sana") == b else 0
    if u.get("ruletka_sana") != b:
        await foydalanuvchilar.update_one(
            {"_id": f.id}, {"$set": {"ruletka_sana": b, "ruletka_soni": 0}}
        )
    r = await foydalanuvchilar.update_one(
        {"_id": f.id, "ruletka_sana": b, "ruletka_soni": {"$lt": RULETKA_LIMIT}},
        {"$inc": {"ruletka_soni": 1}},
    )
    if r.modified_count == 0:
        await update.message.reply_text(
            "⏳ Bugungi urinishlar tugadi. Ertaga qayting !"
        )
        return
    qolgan = RULETKA_LIMIT - (ishlatilgan + 1)

    dice = await update.message.reply_dice(emoji="🎰")
    await asyncio.sleep(3)  # animatsiya tugashini kutamiz
    miqdor, natija = ruletka_hisobla(dice.dice.value)
    if miqdor:
        await foydalanuvchilar.update_one(
            {"_id": f.id}, {"$inc": {"coins": miqdor}}
        )
    u = await foydalanuvchilar.find_one({"_id": f.id}) or {}
    await dice.reply_text(
        f"{RAMKA}\n"
        f"🎰 {natija}\n\n"
        f"🫧 {K(f.first_name)}\n"
        f"💰 Tanga : +{miqdor}\n"
        f"👛 Jami : {u.get('coins', 0)}\n"
        f"🎟 Qolgan urinish : {qolgan}",
        parse_mode="HTML",
    )


# ---------- Guruhga kelganlarni kutib olish ----------
async def xush_kelibsiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    xabar = update.message
    chat = update.effective_chat
    yangilar = xabar.new_chat_members or []

    # Botning o'zi guruhga qo'shilganda
    if any(m.id == context.bot.id for m in yangilar):
        await xabar.reply_text(
            f"{RAMKA}\n"
            "💫 Salom, guruh a'zolari !\n\n"
            "🫶 Meni qo'shganingiz uchun rahmat !\n"
            "🐾 Yozishaveringiz, waifular chiqadi\n"
            "🗽 /topish ism — Waifuni topish\n"
            "🎴 /kolleksiya — Waifularingiz",
            parse_mode="HTML",
        )
        return

    if not await ruxsatli_guruhmi(chat):
        return
    odamlar = [m for m in yangilar if not m.is_bot]
    if not odamlar:
        return
    nomlar = ", ".join(eslatma(m) for m in odamlar)
    await xabar.reply_text(
        f"{RAMKA}\n"
        f"💫 Xush kelibsiz, {nomlar} !\n\n"
        "🫶 Sizni ko'rib xursandmiz !\n"
        f"🎁 /bonus — Super waifu + {XUSH_BONUS_TANGA} tanga\n"
        "📅 /kunlik — Kunlik tanga\n"
        "🎰 /ruletka — Omadni sinang\n"
        "🐾 /topish ism — Waifuni topish\n\n"
        "🌟 Omad yor bo'lsin !",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton(stil("📢 Kanal"), url=KANAL_URL),
            InlineKeyboardButton(stil("🤖 Bot"), url=context.bot.link),
        ]]),
    )


# ---------- Admin: personaj yuklash ----------
async def yuklash(update: Update, context: ContextTypes.DEFAULT_TYPE):
    xabar = update.message
    if update.effective_user.id != ADMIN_ID:
        return
    matn = re.sub(r"^/\w+(@\w+)?", "", xabar.caption or "").strip()
    qismlar = [q.strip() for q in matn.split("|")]
    if len(qismlar) != 3 or not all(qismlar):
        await xabar.reply_text(
            "Rasm yuboring, izohga yozing:\n"
            "/yuklash Ism | Manba | Nodirlik\n"
            "Nodirlik: Yaxshi, Ajoyib, Super, Mega yoki Maxsus"
        )
        return
    ism, manba, nodirlik = qismlar
    kalit = nodirlik_kaliti(nodirlik)
    if not kalit:
        await xabar.reply_text(
            "Nodirlik: Yaxshi, Ajoyib, Super, Mega yoki Maxsus bo'lishi kerak."
        )
        return
    await raqam_tuzat(baza)
    raqam = await keyingi_raqam(baza)
    await personajlar.insert_one({
        "name": ism, "anime": manba, "rarity": kalit,
        "file_id": xabar.photo[-1].file_id, "raqam": raqam,
    })
    jami = await personajlar.count_documents({})
    await xabar.reply_text(
        f"✅ {K(ism)} ({NODIRLIK[kalit][0]}) qo'shildi !\n"
        f"🔢 Raqam : {raqam} | 🎴 Jami : {jami}",
        parse_mode="HTML",
    )


# ---------- Guruh o'yini ----------
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
        caption=(
            "✨━ ━━━━━━━━━ ━✨\n"
            " 💫YANGI PERSONAJ CHIQDI!\n"
            f"🎗️ RANK : {yulduz_matni(p)}\n\n"
            "🐾   <code>/topish ism</code> 🇺🇿"
        ),
        parse_mode="HTML",
)
