import html
import logging
import random
import time
import uuid
from collections import Counter
from datetime import datetime, timedelta, timezone
from telegram import (
    InlineKeyboardButton, InlineKeyboardMarkup, Update, WebAppInfo,
)
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes
import haftalik

# ---------- Sozlamalar ----------
TOSHKENT = timezone(timedelta(hours=5))
MINI_APP_URL = "https://syrax2007-debug.github.io/Gran-Collector-Bot/"

# Daraja narxlari (tanga). /narx va /trade shu narxlardan foydalanadi
NARX = {
    "common": 600,
    "rare": 1800,
    "epic": 5000,
    "legendary": 12000,
    "special": 30000,
    "max": 80000,
}
# Almashib bo'lmaydigan darajalar (faqat tushish bilan olinadi)
ALMASHMAYDI = ("special", "max")
TRADE_LIMIT = 5  # kuniga nechta almashish
TRADE_MUDDAT = 600  # taklif necha soniya amal qiladi

# /claim ehtimollari (nisbat; jami 100 bo'lishi shart emas)
CLAIM_IHTIMOL = [("common", 45), ("rare", 25), ("epic", 15), ("legendary", 5)]

_baza = None
_nodirlik = {}
_yulduz = None
_guruh_tekshir = None
_ramka = "✨━ ━━━━━━━━━ ━✨"


# ---------- Yordamchi ----------
def K(x):
    return html.escape(str(x))


def bugun():
    return datetime.now(TOSHKENT).strftime("%Y-%m-%d")


def kalit(p):
    return str(p["rarity"]).lower()


def nom(p):
    k = kalit(p)
    return _nodirlik[k][0] if k in _nodirlik else str(p["rarity"]).upper()


def bog(uid, ism):
    return f'<a href="tg://user?id={uid}">{K(ism)}</a>'


async def _bot_nomi(bot):
    try:
        return bot.username or (await bot.get_me()).username
    except Exception:
        return ""


# ---------- /narx ----------
async def narx_buyruq(update: Update, context: ContextTypes.DEFAULT_TYPE):
    qatorlar = []
    for k in ("common", "rare", "epic", "legendary", "special", "max"):
        belgi = _nodirlik[k][0] if k in _nodirlik else k.upper()
        izoh = "  (almashilmaydi)" if k in ALMASHMAYDI else ""
        qatorlar.append(f"{belgi} : 🪙 {NARX[k]}{izoh}")
    await update.message.reply_text(
        f"{_ramka}\n"
        "💰 Daraja narxlari\n\n" + "\n".join(qatorlar) + "\n\n"
        "🔁 Almashish : odam xabariga javob berib\n"
        "<code>/trade 4821 1033</code>\n"
        "(birinchi raqam sizniki, ikkinchisi uniki)\n"
        "Daraja har xil bo'lsa, farqni qiymati past tomon tanga bilan to'laydi.",
        parse_mode="HTML",
    )


# ---------- /claim ----------
async def _claim_personaji():
    ranglar = []
    for k, v in CLAIM_IHTIMOL:
        shart = {"rarity": {"$in": [k, k.capitalize(), k.upper()]}}
        soni = await _baza["characters"].count_documents(shart)
        if soni:
            ranglar.append((shart, soni, v))
    if not ranglar:
        return None
    shart, soni, _ = random.choices(ranglar, weights=[r[2] for r in ranglar])[0]
    return await _baza["characters"].find_one(shart, skip=random.randrange(soni))


async def claim(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _guruh_tekshir(update):
        return
    f = update.effective_user
    users = _baza["users"]
    await users.update_one(
        {"_id": f.id}, {"$set": {"name": f.first_name}}, upsert=True
    )
    b = bugun()
    r = await users.update_one(
        {"_id": f.id, "claim_sana": {"$ne": b}}, {"$set": {"claim_sana": b}}
    )
    if r.modified_count == 0:
        await update.message.reply_text(
            "⏳ Bugungi waifuni olgansiz. Ertaga qayting !"
        )
        return
    p = await _claim_personaji()
    if not p:
        await users.update_one({"_id": f.id}, {"$set": {"claim_sana": ""}})
        await update.message.reply_text(
            "⚠️ Hozircha waifu yo'q. Adminga xabar bering."
        )
        return
    await _baza["collection"].insert_one({"user_id": f.id, "char_id": p["_id"]})
    await update.message.reply_photo(
        p["file_id"],
        caption=(
            f"{_ramka}\n"
            "🎁 Kunlik waifu !\n\n"
            f"🫧 {K(f.first_name)} waifu oldi !\n"
            f"🗽 Ismi : {K(p['name'])}\n"
            f"🎗️ RANK : {_yulduz(p)}\n"
            f"👀 Manba : {K(p['anime'])}\n"
            f"🔢 Raqam : {p.get('raqam', '?')}\n\n"
            "🌙 Ertaga yana qayting !"
        ),
        parse_mode="HTML",
    )


# ---------- /profil ----------
async def profil(update: Update, context: ContextTypes.DEFAULT_TYPE):
    xabar = update.message
    kim = update.effective_user
    if xabar.reply_to_message and xabar.reply_to_message.from_user:
        kim = xabar.reply_to_message.from_user
    if kim.is_bot:
        await xabar.reply_text("❌ Bot uchun profil yo'q !")
        return
    ozi = kim.id == update.effective_user.id
    u = await _baza["users"].find_one({"_id": kim.id}) or {}
    sanash = Counter()
    async for d in _baza["collection"].find({"user_id": kim.id}):
        sanash[d["char_id"]] += 1
    chars = {}
    if sanash:
        async for p in _baza["characters"].find({"_id": {"$in": list(sanash)}}):
            chars[p["_id"]] = p
    jami = sum(sanash.values())
    darajalar = Counter()
    for cid, n in sanash.items():
        if cid in chars:
            darajalar[kalit(chars[cid])] += n

    # Sevimli waifu (Mini App'da tanlangan). Yo'q bo'lsa, eng yuqori darajalisi
    sevimli = chars.get(u.get("sevimli")) if u.get("sevimli") in sanash else None
    tanlangan_web = sevimli is not None
    if sevimli is None and chars:
        eng = max(_yulduz_son(p) for p in chars.values())
        sevimli = random.choice([p for p in chars.values() if _yulduz_son(p) == eng])
    # Eng yuqori daraja
    yuqori = ""
    if chars:
        p = max(chars.values(), key=_yulduz_son)
        yuqori = nom(p)

    tolangan = await _baza["users"].count_documents(
        {"referrer": kim.id, "ref_tolangan": True}
    )
    hafta = (
        await _baza["haftalik"].find_one(
            {"_id": f"{haftalik.hafta_id()}:{kim.id}"}
        )
        or {}
    )
    qator = " ".join(
        f"{_nodirlik[k][0].split()[0]} {darajalar.get(k, 0)}"
        for k in ("common", "rare", "epic", "legendary", "special", "max")
        if k in _nodirlik
    )
    matn = (
        f"{_ramka}\n"
        "👤 Profil\n\n"
        f"🫧 {bog(kim.id, kim.first_name)}\n"
        f"🆔 <code>{kim.id}</code>\n\n"
        f"🎴 Waifular : {jami} ({len(sanash)} xil)\n"
        f"{qator}\n"
        f"🏆 Eng yuqori : {yuqori or '➖'}\n"
        f"🌟 Sevimli : {K(sevimli['name']) if tanlangan_web else '➖'}\n\n"
        f"👛 Tanga : {u.get('coins', 0)}\n"
        f"👥 Takliflar : {tolangan}\n"
        f"📊 Bu hafta : 🎴 {hafta.get('waifu', 0)} • 🪙 {hafta.get('coin', 0)} • 👥 {hafta.get('ref', 0)}"
    )
    if ozi and not tanlangan_web:
        matn += (
            "\n\n💡 Mini App'da waifuni ♡ bilan sevimli qiling: "
            "profil kartangizda shu rasm chiqadi !"
        )
    # Mini App tugmasi: shaxsiy chatda to'g'ridan-to'g'ri, guruhda bot orqali
    if update.effective_chat.type == "private":
        tugma = InlineKeyboardButton("🌐 Mini App", web_app=WebAppInfo(url=MINI_APP_URL))
    else:
        bot_nomi = await _bot_nomi(context.bot)
        tugma = InlineKeyboardButton(
            "🌐 Mini App", url=f"https://t.me/{bot_nomi}?start=profil"
        )
    klaviatura = InlineKeyboardMarkup([[tugma]])
    if sevimli:
        try:
            await xabar.reply_photo(
                sevimli["file_id"], caption=matn, parse_mode="HTML",
                reply_markup=klaviatura,
            )
            return
        except Exception as xato:
            logging.warning("Profil rasmini yuborib bo'lmadi: %s", xato)
    await xabar.reply_text(matn, parse_mode="HTML", reply_markup=klaviatura)


def _yulduz_son(p):
    return {"common": 1, "rare": 2, "epic": 3, "legendary": 4, "special": 5, "max": 6}.get(kalit(p), 1)


# ---------- /trade ----------
async def _egasi_waifu(uid, raqam):
    # Odamning kolleksiyasidan shu raqamli waifuni topadi
    p = await _baza["characters"].find_one({"raqam": raqam})
    if not p:
        return None
    bor = await _baza["collection"].find_one({"user_id": uid, "char_id": p["_id"]})
    return p if bor else None


async def _kunlik_son(uid):
    u = await _baza["users"].find_one({"_id": uid}) or {}
    return u.get("trade_soni", 0) if u.get("trade_sana") == bugun() else 0


async def _kunlik_oshir(uid):
    b = bugun()
    await _baza["users"].update_one(
        {"_id": uid, "trade_sana": {"$ne": b}},
        {"$set": {"trade_sana": b, "trade_soni": 0}},
    )
    await _baza["users"].update_one({"_id": uid}, {"$inc": {"trade_soni": 1}})


async def trade(update: Update, context: ContextTypes.DEFAULT_TYPE):
    xabar = update.message
    men = update.effective_user
    yordam = (
        "🔁 Almashish : odam xabariga javob berib yozing\n"
        "<code>/trade 4821 1033</code>\n"
        "4821 - sizning waifu raqamingiz, 1033 - uniki.\n"
        "Narxlar : /narx"
    )
    javob = xabar.reply_to_message
    if (
        not javob or not javob.from_user or len(context.args) != 2
        or not all(a.lstrip("#").isdigit() for a in context.args)
    ):
        await xabar.reply_text(yordam, parse_mode="HTML")
        return
    u2 = javob.from_user
    if u2.is_bot or u2.id == men.id:
        await xabar.reply_text("❌ Bu odam bilan almashib bo'lmaydi !")
        return
    mening = await _egasi_waifu(men.id, int(context.args[0].lstrip("#")))
    uning = await _egasi_waifu(u2.id, int(context.args[1].lstrip("#")))
    if not mening:
        await xabar.reply_text("🔍 Birinchi raqam sizning kolleksiyangizda yo'q")
        return
    if not uning:
        await xabar.reply_text("🔍 Ikkinchi raqam bu odamda yo'q")
        return
    if kalit(mening) in ALMASHMAYDI or kalit(uning) in ALMASHMAYDI:
        await xabar.reply_text("🚫 COLLECTOR va MAX waifular almashilmaydi !")
        return
    if await _kunlik_son(men.id) >= TRADE_LIMIT:
        await xabar.reply_text(f"⏳ Bugungi almashish limiti tugadi ({TRADE_LIMIT} ta)")
        return
    # farq > 0: men olayotgan waifu qimmatroq, farqni men to'layman
    farq = NARX[kalit(uning)] - NARX[kalit(mening)]
    tolovchi = men.id if farq > 0 else u2.id
    if farq != 0:
        t = await _baza["users"].find_one({"_id": tolovchi}) or {}
        if t.get("coins", 0) < abs(farq):
            kim = "Sizda" if tolovchi == men.id else "Bu odamda"
            await xabar.reply_text(f"💸 {kim} tanga yetmaydi : kerak 🪙 {abs(farq)}")
            return
    tid = uuid.uuid4().hex[:10]
    await _baza["trades"].insert_one({
        "_id": tid, "a": men.id, "b": u2.id,
        "ca": mening["_id"], "cb": uning["_id"],
        "farq": farq, "t": time.time(),
    })
    if farq > 0:
        tanga = f"\n💸 {bog(men.id, men.first_name)} qo'shimcha to'laydi : 🪙 {farq}"
    elif farq < 0:
        tanga = f"\n💸 {bog(u2.id, u2.first_name)} qo'shimcha to'laydi : 🪙 {-farq}"
    else:
        tanga = "\n⚖️ Darajalar teng, tanga kerak emas"
    tugmalar = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Qabul qilish", callback_data=f"td:y:{tid}"),
        InlineKeyboardButton("❌ Bekor", callback_data=f"td:n:{tid}"),
    ]])
    await xabar.reply_text(
        f"{_ramka}\n"
        "🔁 Almashish taklifi\n\n"
        f"🫧 {bog(men.id, men.first_name)} beradi :\n"
        f"🗽 {K(mening['name'])} • {_yulduz(mening)} • 🪙 {NARX[kalit(mening)]}\n\n"
        f"🫧 {bog(u2.id, u2.first_name)} beradi :\n"
        f"🗽 {K(uning['name'])} • {_yulduz(uning)} • 🪙 {NARX[kalit(uning)]}\n"
        f"{tanga}\n\n"
        f"{bog(u2.id, u2.first_name)}, qabul qilasizmi ?",
        parse_mode="HTML", reply_markup=tugmalar,
    )


async def trade_tugma(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    _, amal, tid = q.data.split(":")
    d = await _baza["trades"].find_one({"_id": tid})
    if not d:
        await q.answer("Bu taklif endi amal qilmaydi", show_alert=True)
        return
    kim = q.from_user.id
    if amal == "n":
        if kim not in (d["a"], d["b"]):
            await q.answer("Bu sizning taklifingiz emas", show_alert=True)
            return
        await _baza["trades"].delete_one({"_id": tid})
        await q.edit_message_text("❌ Almashish bekor qilindi.")
        await q.answer()
        return
    if kim != d["b"]:
        await q.answer("Faqat taklif olgan odam qabul qila oladi", show_alert=True)
        return
    # Taklif faqat bir marta bajariladi
    d = await _baza["trades"].find_one_and_delete({"_id": tid})
    if not d:
        await q.answer("Bu taklif endi amal qilmaydi", show_alert=True)
        return
    if time.time() - d["t"] > TRADE_MUDDAT:
        await q.edit_message_text("⌛ Taklif muddati tugadi.")
        await q.answer()
        return
    a, b, ca, cb, farq = d["a"], d["b"], d["ca"], d["cb"], d["farq"]
    if await _kunlik_son(a) >= TRADE_LIMIT or await _kunlik_son(b) >= TRADE_LIMIT:
        await q.edit_message_text("⏳ Kunlik almashish limiti tugagan.")
        await q.answer()
        return
    users = _baza["users"]
    tolovchi, oluvchi = (a, b) if farq > 0 else (b, a)
    miqdor = abs(farq)
    if miqdor:
        r = await users.update_one(
            {"_id": tolovchi, "coins": {"$gte": miqdor}},
            {"$inc": {"coins": -miqdor}},
        )
        if r.modified_count == 0:
            await q.edit_message_text("💸 Tanga yetmaydi, almashish bekor.")
            await q.answer()
            return
    coll = _baza["collection"]
    x = await coll.find_one_and_delete({"user_id": a, "char_id": ca})
    y = await coll.find_one_and_delete({"user_id": b, "char_id": cb}) if x else None
    if not (x and y):
        # Qaytaramiz
        if x:
            await coll.insert_one({"user_id": a, "char_id": ca})
        if miqdor:
            await users.update_one({"_id": tolovchi}, {"$inc": {"coins": miqdor}})
        await q.edit_message_text("❌ Waifu endi mavjud emas, almashish bekor.")
        await q.answer()
        return
    await coll.insert_one({"user_id": b, "char_id": ca})
    await coll.insert_one({"user_id": a, "char_id": cb})
    if miqdor:
        await users.update_one({"_id": oluvchi}, {"$inc": {"coins": miqdor}})
    await _kunlik_oshir(a)
    await _kunlik_oshir(b)
    await q.edit_message_text("✅ Almashish bajarildi ! 🫶")
    await q.answer("🔁")


def ulash(ilova, baza, nodirlik, yulduz_matni, guruh_tekshir):
    global _baza, _nodirlik, _yulduz, _guruh_tekshir
    _baza = baza
    _nodirlik = nodirlik
    _yulduz = yulduz_matni
    _guruh_tekshir = guruh_tekshir
    ilova.add_handler(CommandHandler("narx", narx_buyruq))
    ilova.add_handler(CommandHandler("claim", claim))
    ilova.add_handler(CommandHandler(["profil", "profile"], profil))
    ilova.add_handler(CommandHandler("trade", trade))
    ilova.add_handler(CallbackQueryHandler(trade_tugma, pattern=r"^td:"))
