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
import admin_vositalar
import referal
import reyting
import ismlar
import maxevent
import adminplus
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
ADMIN_ID = 8288620037  # o'zingizning Telegram ID raqamingiz
MINI_APP_URL = "https://syrax2007-debug.github.io/Gran-Collector-Bot/"
CHIQISH_ORALIGI = 120  # nechta xabardan keyin personaj chiqadi
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

# 6 ta daraja. kalit (bazada saqlanadi): (ko'rinadigan nom, chiqish ehtimoli)
# Ehtimol 0 bo'lsa, oddiy chiqishda uchramaydi:
#   COLLECTOR - faqat EVENT paytida, MAX - faqat asosiy guruhda (/max orqali)
NODIRLIK = {
    "common": ("💠 ELITA", 60),
    "rare": ("🌟 SUPER", 25),
    "epic": ("💎 MEGA", 10),
    "legendary": ("🔥 ULTRA", 5),
    "special": ("⛩️ COLLECTOR", 0),
    "max": ("👑 MAX", 0),
}

# /yuklash da yoziladigan nomlar (eski nomlar ham ishlaydi)
NODIRLIK_NOMLARI = {
    "elita": "common",
    "super": "rare",
    "mega": "epic",
    "ultra": "legendary",
    "collector": "special",
    "max": "max",
    "yaxshi": "common",
    "ajoyib": "rare",
    "maxsus": "special",
    "oddiy": "common",
    "nodir": "rare",
    "epik": "epic",
    "afsonaviy": "legendary",
}

# Daraja yulduzlari (6 tadan)
YULDUZ = {
    "common": 1, "rare": 2, "epic": 3, "legendary": 4, "special": 5, "max": 6,
}
YULDUZ_JAMI = 6
# Oddiy chiqishdan chiqarib tashlanadigan darajalar
YOPIQ_DARAJALAR = ["special", "Special", "max", "Max", "MAX"]

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
    soni = YULDUZ.get(str(p["rarity"]).lower(), 1)
    return "★" * soni + "☆" * (YULDUZ_JAMI - soni)


def kartochka(p):
    # Inline natijalar uchun qisqa kartochka
    return (
        f"🗽 Ismi : {K(p['name'])}\n"
        f"🎗️ RANK : {yulduz_matni(p)}\n"
        f"👀 Manba : {K(p['anime'])}\n"
        f"🔢 Raqam : {p.get('raqam', '?')}"
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
    # Event faol bo'lsa, ba'zan shu eventning Collector waifusi chiqadi
    p = await maxevent.event_personaji()
    if p:
        return p
    kalitlar = [k for k in NODIRLIK if NODIRLIK[k][1] > 0]
    ehtimollar = [NODIRLIK[k][1] for k in kalitlar]
    for _ in range(10):
        kalit = random.choices(kalitlar, ehtimollar)[0]
        shart = {"rarity": {"$in": [kalit, kalit.capitalize()]}}
        soni = await personajlar.count_documents(shart)
        if soni:
            return await personajlar.find_one(
                shart, skip=random.randrange(soni)
            )
    shart = {"rarity": {"$nin": YOPIQ_DARAJALAR}}
    jami = await personajlar.count_documents(shart)
    if jami == 0:
        return None
    return await personajlar.find_one(shart, skip=random.randrange(jami))


async def bonus_personaji():
    # Avval MEGA, bo'lmasa boshqa darajalardan
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
        f"🎁 /bonus — Mega waifu + {XUSH_BONUS_TANGA} tanga\n"
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
YUKLASH_YORDAM = (
    "Rasm yuboring, izohga yozing:\n"
    "/yuklash Ism | Manba | Daraja\n"
    "Daraja: Elita, Super, Mega, Ultra, Collector yoki Max\n\n"
    "⛩️ Collector uchun event nomi ham kerak:\n"
    "/yuklash Ism | Manba | Collector | Event nomi\n"
    "(masalan: Qish 2026, Yoz, Halloween)"
)


async def yuklash(update: Update, context: ContextTypes.DEFAULT_TYPE):
    xabar = update.message
    if update.effective_user.id != ADMIN_ID:
        return
    matn = re.sub(r"^/\w+(@\w+)?", "", xabar.caption or "").strip()
    qismlar = [q.strip() for q in matn.split("|")]
    if len(qismlar) not in (3, 4) or not all(qismlar):
        await xabar.reply_text(YUKLASH_YORDAM)
        return
    ism, manba, nodirlik = qismlar[:3]
    kalit = nodirlik_kaliti(nodirlik)
    if not kalit:
        await xabar.reply_text(
            "Daraja: Elita, Super, Mega, Ultra, Collector yoki Max bo'lishi kerak."
        )
        return
    event = None
    if kalit == "special":
        if len(qismlar) != 4:
            await xabar.reply_text(
                "⛩️ Collector uchun event nomi kerak:\n"
                "/yuklash Ism | Manba | Collector | Event nomi"
            )
            return
        event = " ".join(qismlar[3].split())
    await raqam_tuzat(baza)
    raqam = await keyingi_raqam(baza)
    hujjat = {
        "name": ism, "anime": manba, "rarity": kalit,
        "file_id": xabar.photo[-1].file_id, "raqam": raqam,
    }
    if event:
        hujjat["event"] = event
    await personajlar.insert_one(hujjat)
    jami = await personajlar.count_documents({})
    await xabar.reply_text(
        f"✅ {K(ism)} ({NODIRLIK[kalit][0]}) qo'shildi !\n"
        + (f"⛩️ Event : {K(event)}\n" if event else "")
        + f"🔢 Raqam : {raqam} | 🎴 Jami : {jami}",
        parse_mode="HTML",
    )


# ---------- Guruh o'yini ----------
async def xabarlarni_sanash(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    # MAX: faqat asosiy guruhda va admin /max bergan bo'lsagina sanaydi
    try:
        await maxevent.sana(update, context)
    except Exception as xato:
        logging.warning("MAX sanashda xato: %s", xato)
    hisoblagich[chat_id] = hisoblagich.get(chat_id, 0) + 1
    if hisoblagich[chat_id] < await adminplus.oraliq_ol(CHIQISH_ORALIGI):
        return
    hisoblagich[chat_id] = 0
    # MAX personaj hali topilmagan bo'lsa, uning ustiga oddiysi chiqmasin
    if await maxevent.max_kutilyapti(chat_id):
        return
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

# ---------- 2-BO'LAK: topish, kolleksiya, sovga, inline ----------
async def topish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if not context.args:
        await update.message.reply_text("💬 Ism yozing : /topish ism")
        return
    chiqqan = await chiqqanlar.find_one({"_id": chat_id})
    if not chiqqan:
        await update.message.reply_text("🔍 Hozir topiladigan waifu yo'q")
        return
    p = await personajlar.find_one({"_id": chiqqan["char_id"]})
    javob = " ".join(context.args).lower().strip()
    toliq_ism = p["name"].lower()
    if javob == toliq_ism or javob in toliq_ism.split():
        await chiqqanlar.delete_one({"_id": chat_id})
        f = update.effective_user
        await kolleksiya.insert_one({"user_id": f.id, "char_id": p["_id"]})
        matn = (
            f"🫧 {K(f.first_name)} waifuni topdi !\n\n"
            f"🗽 Ismi : {K(p['name'])}\n"
            f"🎗️ RANK : {yulduz_matni(p)}\n"
            f"👀 Manba : {K(p['anime'])}\n"
            "Kolleksiyangizga Qo'shildi !🤙\n\n"
            "🫶 Waifularni koring  /kolleksiya!"
        )
        await update.message.reply_photo(
            p["file_id"], caption=matn, parse_mode="HTML",
            reply_markup=kolleksiya_tugmasi(
                f, update.effective_chat.type == "private"
            ),
        )
    else:
        await update.message.reply_text("❌ Noto'g'ri ! Qayta urinib koring")


# ---------- Kolleksiya (rasm izohida, sahifalar bilan) ----------
def sahifa_qatori(egasi_id, kim_id, sahifa, jami):
    return [
        InlineKeyboardButton(
            "◀️",
            callback_data=f"kp:{egasi_id}:{kim_id}:{(sahifa - 1) % jami}",
        ),
        InlineKeyboardButton(f"{sahifa + 1}/{jami}", callback_data="kn"),
        InlineKeyboardButton(
            "▶️",
            callback_data=f"kp:{egasi_id}:{kim_id}:{(sahifa + 1) % jami}",
        ),
    ]


async def kolleksiyam(update: Update, context: ContextTypes.DEFAULT_TYPE):
    xabar = update.message
    f = update.effective_user
    javob = xabar.reply_to_message
    # Biror odamning xabariga javob bo'lsa, o'sha odamning kolleksiyasi
    if javob and javob.from_user and not javob.from_user.is_bot:
        f = javob.from_user
    ozi = f.id == update.effective_user.id

    malumot = await kolleksiya_malumot(baza, f.id)
    if not malumot:
        if ozi:
            matn = "📭 Kolleksiyangiz hozircha bo'sh. Guruhda waifu topib boshlang !"
        else:
            matn = f"📭 {K(f.first_name)} kolleksiyasi hozircha bo'sh."
        await xabar.reply_text(matn, parse_mode="HTML")
        return

    qismlar = malumot["qismlar"]
    izoh = kolleksiya_izohi(f.first_name, malumot["jami"], qismlar, 0)
    shaxsiy = update.effective_chat.type == "private" and ozi
    qatorlar = [
        list(r) for r in kolleksiya_tugmasi(f, shaxsiy).inline_keyboard
    ]
    if len(qismlar) > 1:
        qatorlar.insert(
            0, sahifa_qatori(f.id, update.effective_user.id, 0, len(qismlar))
        )
    klaviatura = InlineKeyboardMarkup(qatorlar)

    tasodifiy = random.choice(malumot["royxat"])
    try:
        await xabar.reply_photo(
            tasodifiy["file_id"], caption=izoh, parse_mode="HTML",
            reply_markup=klaviatura,
        )
    except Exception:
        await xabar.reply_text(
            izoh, parse_mode="HTML", reply_markup=klaviatura
        )


async def kolleksiya_sahifa(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    qism = q.data.split(":")
    egasi_id, kim_id, sahifa = int(qism[1]), int(qism[2]), int(qism[3])
    if q.from_user.id != kim_id:
        await q.answer("Bu sizning so'rovingiz emas. /kolleksiya yozing", show_alert=True)
        return
    malumot = await kolleksiya_malumot(baza, egasi_id)
    if not malumot:
        await q.answer("Kolleksiya bo'sh", show_alert=True)
        return
    qismlar = malumot["qismlar"]
    sahifa = sahifa % len(qismlar)

    rasmli = bool(q.message.photo)
    eski = (q.message.caption_html if rasmli else q.message.text_html) or ""
    sarlavha = "\n".join(eski.split("\n")[:2])
    yangi = sarlavha + "\n\n" + qismlar[sahifa]
    if len(qismlar) > 1:
        yangi += f"\n\n📄 {sahifa + 1}/{len(qismlar)}"

    qatorlar = []
    if q.message.reply_markup:
        qatorlar = [list(r) for r in q.message.reply_markup.inline_keyboard]
    if qatorlar and qatorlar[0] and str(
        qatorlar[0][0].callback_data or ""
    ).startswith("kp:"):
        qatorlar.pop(0)
    if len(qismlar) > 1:
        qatorlar.insert(0, sahifa_qatori(egasi_id, kim_id, sahifa, len(qismlar)))
    klaviatura = InlineKeyboardMarkup(qatorlar)

    try:
        if rasmli:
            await q.edit_message_caption(
                caption=yangi, parse_mode="HTML", reply_markup=klaviatura
            )
        else:
            await q.edit_message_text(
                yangi, parse_mode="HTML", reply_markup=klaviatura
            )
    except Exception:
        pass
    await q.answer()


async def bosh_tugma(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()


# ---------- Sovga ----------
async def sovga(update: Update, context: ContextTypes.DEFAULT_TYPE):
    xabar = update.message
    yuboruvchi = update.effective_user
    yordam = (
        "🎁 Sovga qilish : odamning xabariga javob berib yozing\n"
        "<code>/sovga ism</code>  yoki  <code>/sovga 4821</code>"
    )
    javob = xabar.reply_to_message
    if not javob or not javob.from_user or not context.args:
        await xabar.reply_text(yordam, parse_mode="HTML")
        return
    oluvchi = javob.from_user
    if oluvchi.is_bot or oluvchi.id == yuboruvchi.id:
        await xabar.reply_text("❌ Bu odamga sovga qilib bo'lmaydi !")
        return

    so_z = " ".join(context.args).strip().lstrip("#").lower()
    idlar = {
        d["char_id"] async for d in kolleksiya.find({"user_id": yuboruvchi.id})
    }
    royxat = [
        p async for p in personajlar.find({"_id": {"$in": list(idlar)}})
    ]
    # Avval raqam bo'yicha, keyin ism bo'yicha qidiramiz
    tanlangan = None
    for p in royxat:
        if str(p.get("raqam", "")) == so_z:
            tanlangan = p
            break
    if not tanlangan:
        for p in royxat:
            ism = p["name"].lower()
            if so_z == ism or so_z in ism.split():
                tanlangan = p
                break
    if not tanlangan:
        await xabar.reply_text("🔍 Bunday waifu kolleksiyangizda yo'q")
        return

    tugmalar = InlineKeyboardMarkup([[
        InlineKeyboardButton(
            stil("✅ Yuborish"),
            callback_data=f"sh:{yuboruvchi.id}:{oluvchi.id}:{tanlangan['_id']}",
        ),
        InlineKeyboardButton(
            stil("❌ Bekor"), callback_data=f"sb:{yuboruvchi.id}"
        ),
    ]])
    await xabar.reply_text(
        f"{RAMKA}\n"
        "🎁 Sovga\n\n"
        f"🫧 {eslatma(yuboruvchi)} ➜ {eslatma(oluvchi)}\n"
        f"🗽 Ismi : {K(tanlangan['name'])}\n"
        f"🎗️ RANK : {yulduz_matni(tanlangan)}\n\n"
        "Tasdiqlaysizmi ?",
        parse_mode="HTML",
        reply_markup=tugmalar,
    )


async def sovga_tugma(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    qismlar = q.data.split(":")
    # Tugmani faqat sovga qilayotgan odam bosa oladi
    if int(qismlar[1]) != q.from_user.id:
        await q.answer("Bu sizning sovg'angiz emas", show_alert=True)
        return
    if qismlar[0] == "sb":
        await q.edit_message_text("❌ Sovga bekor qilindi.")
        await q.answer()
        return

    yuboruvchi_id = int(qismlar[1])
    oluvchi_id = int(qismlar[2])
    pid = ObjectId(qismlar[3])
    # Waifuni yuboruvchidan olib tashlaymiz (bir marta, xavfsiz)
    olindi = await kolleksiya.find_one_and_delete(
        {"user_id": yuboruvchi_id, "char_id": pid}
    )
    if not olindi:
        await q.edit_message_text("❌ Bu waifu endi sizda yo'q.")
        await q.answer()
        return
    await kolleksiya.insert_one({"user_id": oluvchi_id, "char_id": pid})
    await q.edit_message_text("🎁 Sovga yuborildi ! 🫶")
    await q.answer("🎁")


# ---------- Inline ----------
async def inline_qidiruv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    so_rov = update.inline_query
    matn = so_rov.query.strip().lower()
    egasi_id = so_rov.from_user.id
    # "u12345" ko'rinishidagi so'rov: boshqa odamning kolleksiyasi
    m = re.match(r"^u(\d+)\s*(.*)$", matn)
    if m:
        egasi_id = int(m.group(1))
        matn = m.group(2).strip()
    idlar = [d["char_id"] async for d in kolleksiya.find({"user_id": egasi_id})]
    natijalar = []
    async for p in personajlar.find({"_id": {"$in": list(set(idlar))}}):
        if matn and matn not in p["name"].lower():
            continue
        natijalar.append(
            InlineQueryResultCachedPhoto(
                id=str(p["_id"]),
                photo_file_id=p["file_id"],
                caption=stil(kartochka(p)),
                parse_mode="HTML",
            )
        )
        if len(natijalar) >= 50:
            break
    await so_rov.answer(natijalar, cache_time=5, is_personal=True)


# ---------- Botni ishga tushirish ----------
ilova = ApplicationBuilder().bot(StilBot(os.environ["BOT_TOKEN"])).build()
ilova.add_handler(CommandHandler("start", boshlash))
ilova.add_handler(CommandHandler("id", id_korsat))
ilova.add_handler(CommandHandler("balans", balans))
ilova.add_handler(CommandHandler("bonus", bonus))
ilova.add_handler(CommandHandler("kunlik", kunlik))
ilova.add_handler(CommandHandler(["ruletka", "slot"], ruletka))
ilova.add_handler(CommandHandler("ruxsat", ruxsat))
ilova.add_handler(CommandHandler("ruxsat_ochir", ruxsat_ochir))
ilova.add_handler(CommandHandler(["topish", "guess"], topish))
ilova.add_handler(CommandHandler(["kolleksiya", "harem"], kolleksiyam))
ilova.add_handler(CommandHandler(["sovga", "gift"], sovga))
ilova.add_handler(CallbackQueryHandler(sovga_tugma, pattern=r"^(sh|sb):"))
ilova.add_handler(CallbackQueryHandler(kolleksiya_sahifa, pattern=r"^kp:"))
ilova.add_handler(CallbackQueryHandler(bosh_tugma, pattern=r"^kn$"))
ilova.add_handler(
    MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, xush_kelibsiz)
)
ilova.add_handler(
    MessageHandler(
        filters.PHOTO & filters.CaptionRegex(r"^/(yuklash|upload)"), yuklash
    )
)
ilova.add_handler(
    MessageHandler(
        filters.ChatType.GROUPS & ~filters.COMMAND & ~filters.StatusUpdate.ALL,
        xabarlarni_sanash,
    )
)
ilova.add_handler(InlineQueryHandler(inline_qidiruv))
admin_vositalar.ulash(ilova, baza, ADMIN_ID, nodirlik_kaliti, NODIRLIK)
referal.ulash(ilova, baza)
reyting.ulash(ilova, baza)
ismlar.ulash(ilova, baza)
maxevent.ulash(ilova, baza, ADMIN_ID, RASMIY_GURUH, yulduz_matni)
adminplus.ulash(
    ilova, baza, ADMIN_ID, NODIRLIK, yulduz_matni, tasodifiy_personaj,
    CHIQISH_ORALIGI, RASMIY_GURUH,
)

if __name__ == "__main__":
    ilova.run_polling()
