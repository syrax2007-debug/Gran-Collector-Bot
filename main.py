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
CIZIQ = "━━━━━━━━━━━━━━"
YUQORI = "╔══════════════╗"
PASTKI = "╚══════════════╝"
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
    "common": ("✨ YAXSHI", 60),
    "rare": ("💎 AJOYIB", 25),
    "epic": ("🔥 SUPER", 10),
    "legendary": ("👑 MEGA", 5),
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

# Guruhda chiqqanda ko'rinadigan sarlavhalar
SARLAVHA = {
    "common": "🌸 YANGI PERSONAJ CHIQDI! 🌸",
    "rare": "💎 AJOYIB PERSONAJ CHIQDI! 💎",
    "epic": "⚡ SUPER PERSONAJ CHIQDI! ⚡",
    "legendary": "🔥👑 MEGA PERSONAJ CHIQDI! 👑🔥",
    "special": "💠✨ MAXSUS PERSONAJ CHIQDI! ✨💠",
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
    # Katta harfga o'tkazib, HTML uchun xavfsiz qilish
    return html.escape(str(matn).upper())


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


def kartochka(p, sarlavha):
    kalit = p["rarity"].lower()
    if kalit == "special":
        daraja = "✨ MAXSUS ✨"
    else:
        soni = YULDUZ.get(kalit, 1)
        daraja = "★" * soni + "☆" * (5 - soni)
    kod = str(p["_id"])[-4:].upper()
    return (
        f"{sarlavha}\n"
        f"{YUQORI}\n"
        f"<blockquote>"
        f"👤 <b>ISM:</b> {K(p['name'])}\n"
        f"🔖 <b>MANBA:</b> <i>{K(p['anime'])}</i>\n"
        f"💎 <b>NODIRLIK:</b> {nodirlik_belgisi(p)}\n"
        f"🌟 <b>DARAJA:</b> {daraja}\n"
        f"🆔 <b>KOD:</b> <code>#{kod}</code>"
        f"</blockquote>\n"
        f"{PASTKI}"
    )


def mini_app_tugmasi():
    return InlineKeyboardButton(
        "🌐 MINI APP", web_app=WebAppInfo(url=MINI_APP_URL)
    )


def kolleksiya_tugmasi(egasi, shaxsiy=False):
    # 1-tugma: bosgan odam O'Z kolleksiyasini ko'radi
    # 2-tugma: boshqalar kolleksiya EGASINING kolleksiyasini ko'radi
    nom = egasi.first_name.upper()[:16]
    qatorlar = [
        [InlineKeyboardButton(
            "🖼 MENING KOLLEKSIYAM",
            switch_inline_query_current_chat="",
        )],
        [InlineKeyboardButton(
            f"👁 {nom} KOLLEKSIYASI",
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
        f"🚫 <b>BU BUYRUQ FAQAT BOTGA ISHONILGAN GURUHLARDA ISHLAYDI.</b>\n"
        f"{CIZIQ}\n"
        f"✅ RASMIY GURUHGA QO'SHILING VA BONUSLARDAN FOYDALANING!",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("💬 RASMIY GURUH", url=GURUH_URL)
        ]]),
    )
    return False


async def ruxsat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    c = update.effective_chat
    if c.type not in ("group", "supergroup"):
        await update.message.reply_text("❌ BU BUYRUQ FAQAT GURUHDA ISHLAYDI.")
        return
    await ruxsatlilar.update_one(
        {"_id": c.id}, {"$set": {"title": c.title}}, upsert=True
    )
    await update.message.reply_text(
        f"✅ <b>GURUH TASDIQLANDI!</b>\n"
        f"🎁 /bonus  📅 /kunlik  🎰 /ruletka ENDI SHU YERDA ISHLAYDI.",
        parse_mode="HTML",
    )


async def ruxsat_ochir(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    await ruxsatlilar.delete_one({"_id": update.effective_chat.id})
    await update.message.reply_text("🛑 GURUH TASDIG'I BEKOR QILINDI.")


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
        f"👋 SALOM, <b>{K(f.first_name)}</b>!\n"
        f"👥 BOTDA <b>{jami}</b> TA FOYDALANUVCHI BOR\n\n"
        f"📜 <b>BUYRUQLAR:</b>\n"
        f"🔹 <code>/topish ism</code> — PERSONAJNI TOPISH\n"
        f"🔹 /kolleksiya — MENING KOLLEKSIYAM\n"
        f"🔹 <code>/sovga ism</code> — SOVGA QILISH (JAVOB BERIB)\n"
        f"🔹 /balans — MENING TANGALARIM\n"
        f"🔹 /id — TELEGRAM ID RAQAMIM\n\n"
        f"🎁 <b>RASMIY GURUHDA:</b>\n"
        f"🔸 /bonus — SUPER PERSONAJ + {XUSH_BONUS_TANGA} 🪙 (BIR MARTA)\n"
        f"🔸 /kunlik — HAR KUNGI TANGA\n"
        f"🔸 /ruletka — 🎰 OMAD SINOVI\n\n"
        f"🎴 BOTNI GURUHGA QO'SHING VA PERSONAJLARNI YIG'ING!"
    )
    shaxsiy = update.effective_chat.type == "private"
    tugma = None
    if shaxsiy:
        tugma = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("📢 KANAL", url=KANAL_URL),
                InlineKeyboardButton("💬 GURUH", url=GURUH_URL),
            ],
            [mini_app_tugmasi()],
        ])
    await update.message.reply_text(
        matn, parse_mode="HTML", reply_markup=tugma
    )


async def id_korsat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"🆔 SIZNING ID: <code>{update.effective_user.id}</code>",
        parse_mode="HTML",
    )


async def balans(update: Update, context: ContextTypes.DEFAULT_TYPE):
    f = update.effective_user
    u = await foydalanuvchilar.find_one({"_id": f.id}) or {}
    await update.message.reply_text(
        f"💰✨{CIZIQ}✨💰\n"
        f"👤 <b>{K(f.first_name)}</b>\n"
        f"🪙 <b>TANGALARINGIZ:</b> {u.get('coins', 0)}\n"
        f"💰✨{CIZIQ}✨💰",
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
        await update.message.reply_text(
            f"✅ <b>SIZ BONUSNI ALLAQACHON OLGANSIZ!</b>\n"
            f"{CIZIQ}\n"
            f"🎴 /kolleksiya — PERSONAJINGIZNI KO'RING\n"
            f"📅 /kunlik — HAR KUNGI TANGA\n"
            f"🎰 /ruletka — OMADINGIZNI SINANG",
            parse_mode="HTML",
        )
        return
    p = await bonus_personaji()
    if not p:
        await update.message.reply_text(
            "⚠️ HOZIRCHA BONUS PERSONAJI YO'Q. ADMINGA XABAR BERING."
        )
        return
    r = await foydalanuvchilar.update_one(
        {"_id": f.id, "xush_bonus": {"$ne": True}},
        {"$set": {"xush_bonus": True}, "$inc": {"coins": XUSH_BONUS_TANGA}},
    )
    if r.modified_count == 0:
        await update.message.reply_text("✅ BONUS ALLAQACHON OLINGAN.")
        return
    await kolleksiya.insert_one({"user_id": f.id, "char_id": p["_id"]})
    matn = (
        kartochka(p, "🎁✨ <b>XUSH KELIBSIZ BONUSI!</b> ✨🎁")
        + f"\n🪙 <b>+{XUSH_BONUS_TANGA} TANGA</b>\n"
        f"🎉 <b>{K(f.first_name)}</b>, SOVG'ALARINGIZ MUBORAK BO'LSIN!"
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
            f"⏳ <b>BUGUNGI BONUSNI ALLAQACHON OLGANSIZ!</b>\n"
            f"{CIZIQ}\n"
            f"🌙 ERTAGA QAYTING, YANA KO'PROQ TANGA KUTMOQDA!",
            parse_mode="HTML",
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
        await update.message.reply_text("⏳ BUGUNGI BONUS ALLAQACHON OLINGAN.")
        return
    u = await foydalanuvchilar.find_one({"_id": f.id}) or {}
    await update.message.reply_text(
        f"📅✨{CIZIQ}✨📅\n"
        f"🎁 <b>KUNLIK BONUS!</b> 🎁\n"
        f"{CIZIQ}\n"
        f"👤 <b>{K(f.first_name)}</b>\n"
        f"🔥 <b>SERIYA:</b> {seriya} KUN\n"
        f"🪙 <b>+{miqdor} TANGA</b>\n"
        f"💰 <b>JAMI:</b> {u.get('coins', 0)}\n"
        f"{CIZIQ}\n"
        f"🌟 HAR KUNI KELING, BONUS O'SIB BORADI!",
        parse_mode="HTML",
    )


def ruletka_hisobla(qiymat):
    # 🎰 qiymati 1..64: har bir g'ildirak 0..3 (BAR, uzum, limon, yetti)
    v = qiymat - 1
    g = [v % 4, (v // 4) % 4, v // 16]
    if g[0] == g[1] == g[2]:
        if g[0] == 3:
            return RULETKA_JEKPOT, "👑 <b>JEKPOT! 7️⃣7️⃣7️⃣</b> 👑"
        return RULETKA_UCHTA, "🎉 <b>UCHTA BIR XIL!</b> 🎉"
    if len(set(g)) == 2:
        return RULETKA_IKKITA, "✨ <b>IKKITA BIR XIL!</b> ✨"
    return 0, "😔 <b>BU SAFAR OMAD KELMADI</b>"


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
            f"⏳ <b>BUGUNGI {RULETKA_LIMIT} TA URINISH TUGADI!</b>\n"
            f"{CIZIQ}\n"
            f"🌙 ERTAGA YANA OMADINGIZNI SINANG 🎰",
            parse_mode="HTML",
        )
        return
    qolgan = RULETKA_LIMIT - (ishlatilgan + 1)

    dice = await update.message.reply_dice(emoji="🎰")
    await asyncio.sleep(3)  # animatsiya tugashini kutamiz
    miqdor, nom = ruletka_hisobla(dice.dice.value)
    if miqdor:
        await foydalanuvchilar.update_one(
            {"_id": f.id}, {"$inc": {"coins": miqdor}}
        )
    u = await foydalanuvchilar.find_one({"_id": f.id}) or {}
    yutuq = f"🪙 <b>+{miqdor} TANGA</b>" if miqdor else "🪙 <b>+0 TANGA</b>"
    await dice.reply_text(
        f"🎰✨{CIZIQ}✨🎰\n"
        f"{nom}\n"
        f"{CIZIQ}\n"
        f"👤 <b>{K(f.first_name)}</b>\n"
        f"{yutuq}\n"
        f"💰 <b>JAMI:</b> {u.get('coins', 0)}\n"
        f"🎟 <b>QOLGAN URINISH:</b> {qolgan}\n"
        f"{CIZIQ}",
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
            f"🌸✨{CIZIQ}✨🌸\n"
            f"💖 <b>SALOM, GURUH A'ZOLARI!</b> 💖\n"
            f"🌸✨{CIZIQ}✨🌸\n\n"
            f"🤗 MENI BU YERGA QO'SHGANINGIZ UCHUN RAHMAT!\n"
            f"🎴 MEN PERSONAJ YIG'ISH O'YINI BOTIMAN.\n\n"
            f"🔹 GURUHDA YOZISHAVERING, PERSONAJLAR CHIQADI\n"
            f"🔹 ISMINI <code>/topish ism</code> BILAN TOPING\n"
            f"🔹 /kolleksiya — YIG'GANLARINGIZNI KO'RING\n\n"
            f"🎁 BONUS, KUNLIK VA RULETKA UCHUN GURUH TASDIQLANISHI KERAK. "
            f"RASMIY GURUHDA BARCHASI TAYYOR!",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("💬 RASMIY GURUH", url=GURUH_URL)
            ]]),
        )
        return

    if not await ruxsatli_guruhmi(chat):
        return
    odamlar = [m for m in yangilar if not m.is_bot]
    if not odamlar:
        return
    nomlar = ", ".join(eslatma(m) for m in odamlar)
    await xabar.reply_text(
        f"🌸✨{CIZIQ}✨🌸\n"
        f"💖 <b>XUSH KELIBSIZ, {nomlar}!</b> 💖\n"
        f"🌸✨{CIZIQ}✨🌸\n\n"
        f"🤗 SIZNI BU YERDA KO'RIB JUDA XURSANDMIZ!\n"
        f"🎴 SIZ ENDI PERSONAJ YIG'UVCHILAR OILASIDASIZ.\n\n"
        f"🎁 <b>BOSHLANG'ICH SOVG'A:</b>\n"
        f"👉 /bonus — SUPER PERSONAJ + {XUSH_BONUS_TANGA} 🪙 (BIR MARTA)\n"
        f"📅 /kunlik — HAR KUNGI TANGA\n"
        f"🎰 /ruletka — OMADINGIZNI SINANG\n"
        f"💬 PERSONAJ CHIQSA: <code>/topish ism</code>\n\n"
        f"🌟 <b>OMAD YOR BO'LSIN!</b> 🌟",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton("📢 KANAL", url=KANAL_URL),
                InlineKeyboardButton("🤖 BOT", url=context.bot.link),
            ],
        ]),
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
            "RASM YUBORING, IZOHGA YOZING:\n"
            "/yuklash Ism | Manba | Nodirlik\n"
            "NODIRLIK: YAXSHI, AJOYIB, SUPER, MEGA YOKI MAXSUS"
        )
        return
    ism, manba, nodirlik = qismlar
    kalit = nodirlik_kaliti(nodirlik)
    if not kalit:
        await xabar.reply_text(
            "NODIRLIK: YAXSHI, AJOYIB, SUPER, MEGA YOKI MAXSUS BO'LISHI KERAK."
        )
        return
    await personajlar.insert_one({
        "name": ism, "anime": manba, "rarity": kalit,
        "file_id": xabar.photo[-1].file_id,
    })
    jami = await personajlar.count_documents({})
    await xabar.reply_text(
        f"✅ <b>{K(ism)}</b> ({NODIRLIK[kalit][0]}) QO'SHILDI!\n"
        f"🎴 JAMI PERSONAJ: <b>{jami}</b>",
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
    sarlavha = SARLAVHA.get(p["rarity"].lower(), "🌸 YANGI PERSONAJ CHIQDI! 🌸")
    await context.bot.send_photo(
        chat_id, p["file_id"],
        caption=(
            f"✨{CIZIQ}✨\n"
            f"<b>{sarlavha}</b>\n"
            f"✨{CIZIQ}✨\n\n"
            f"💬 ISMINI TOPING:\n"
            f"👉 <code>/topish ism</code>"
        ),
        parse_mode="HTML",
    )


async def topish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if not context.args:
        await update.message.reply_text("💬 ISM YOZING: /topish ism")
        return
    chiqqan = await chiqqanlar.find_one({"_id": chat_id})
    if not chiqqan:
        await update.message.reply_text("🔍 HOZIR TOPILADIGAN PERSO
