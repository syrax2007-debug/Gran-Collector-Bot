import html
import logging
import random
from datetime import datetime, timedelta, timezone
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes
from stil import stil
import sozlama as S

# Sandiq : har bir quti o'z darajasidan tasodifiy waifu beradi (omadli quti).
# Narx va kunlik limit /panel dan o'zgartiriladi (sozlama.py: quti_*, qlimit_*).
# Bot (/sandiq) ham, Mini App (api.py) ham shu yerdagi sotib_ol() dan foydalanadi.
TOSHKENT = timezone(timedelta(hours=5))
QUTILAR = ("common", "rare", "epic", "legendary")
NOMLAR = {"common": "ELITA", "rare": "SUPER", "epic": "MEGA", "legendary": "ULTRA"}
BELGI = {"common": "💠", "rare": "🌟", "epic": "💎", "legendary": "🔥"}
RAMKA = "✨━ ━━━━━━━━━ ━✨"

_baza = None
_yulduz = None


def bugun():
    return datetime.now(TOSHKENT).strftime("%Y-%m-%d")


def narx(k):
    return S.ol("quti_" + k)


def limit(k):
    return S.ol("qlimit_" + k)


def shart(k):
    return {"rarity": {"$in": [k, k.capitalize(), k.upper()]}}


async def holat(baza, uid):
    # (tanga, [har bir quti holati])
    u = await baza["users"].find_one({"_id": uid}) or {}
    bir_kun = u.get("sandiq_sana") == bugun()
    royxat = []
    for k in QUTILAR:
        ishl = u.get("sandiq_" + k, 0) if bir_kun else 0
        lim = limit(k)
        soni = await baza["characters"].count_documents(shart(k))
        royxat.append({
            "k": k, "nom": NOMLAR[k], "narx": narx(k), "limit": lim,
            "qolgan": max(lim - ishl, 0), "bor": soni > 0,
        })
    return u.get("coins", 0), royxat


async def sotib_ol(baza, uid, k):
    # (kod, malumot). kod: ok, nomalum, yopiq, limit, tanga_yetmaydi, waifu_yoq, xato
    if k not in QUTILAR:
        return "nomalum", {}
    lim, pul = limit(k), narx(k)
    if lim <= 0:
        return "yopiq", {}
    soni = await baza["characters"].count_documents(shart(k))
    if soni == 0:
        return "waifu_yoq", {}
    users = baza["users"]
    b = bugun()
    # Yangi kun: hisoblagichlar nolga qaytadi
    await users.update_one(
        {"_id": uid, "sandiq_sana": {"$ne": b}},
        {"$set": dict({"sandiq_sana": b}, **{"sandiq_" + x: 0 for x in QUTILAR})},
    )
    # Tanga va kunlik limit bir vaqtda tekshiriladi (ikki marta bosishdan himoya)
    r = await users.update_one(
        {"_id": uid, "coins": {"$gte": pul}, "sandiq_sana": b,
         "sandiq_" + k: {"$lt": lim}},
        {"$inc": {"coins": -pul, "sandiq_" + k: 1}},
    )
    if r.modified_count == 0:
        u = await users.find_one({"_id": uid}) or {}
        if u.get("sandiq_sana") == b and u.get("sandiq_" + k, 0) >= lim:
            return "limit", {}
        if u.get("coins", 0) < pul:
            return "tanga_yetmaydi", {"narx": pul, "coins": u.get("coins", 0)}
        return "xato", {}
    try:
        p = await baza["characters"].find_one(shart(k), skip=random.randrange(soni))
        if p is None:
            raise RuntimeError("waifu topilmadi")
        await baza["collection"].insert_one({"user_id": uid, "char_id": p["_id"]})
    except Exception as xato:
        logging.warning("Quti ochilmadi, tanga qaytarildi: %s", xato)
        await users.update_one(
            {"_id": uid}, {"$inc": {"coins": pul, "sandiq_" + k: -1}}
        )
        return "xato", {}
    u = await users.find_one({"_id": uid}) or {}
    return "ok", {"p": p, "narx": pul, "coins": u.get("coins", 0)}


# ---------- Botdagi /sandiq ----------
def K(x):
    return html.escape(str(x))


def _tugma(matn, data):
    return InlineKeyboardButton(stil(matn), callback_data=data)


async def _bosh_korinish(uid):
    tanga, royxat = await holat(_baza, uid)
    qator = []
    for q in royxat:
        if q["limit"] <= 0 or not q["bor"]:
            holati = "yopiq"
        else:
            holati = f"bugun {q['qolgan']}/{q['limit']}"
        qator.append(f"{BELGI[q['k']]} {q['nom']} : 🪙 {q['narx']} • {holati}")
    matn = (
        f"{RAMKA}\n"
        "📦 Sandiq\n\n"
        "📦 Har bir quti o'z darajasida tasodifiy waifu beradi\n\n"
        + "\n".join(qator) + "\n\n"
        f"👛 Tangangiz : {tanga}"
    )
    tugmalar = []
    juft = []
    for q in royxat:
        if q["limit"] <= 0 or not q["bor"]:
            continue
        juft.append(_tugma(f"📦 {q['nom']} • {q['narx']}", f"sq:o:{uid}:{q['k']}"))
        if len(juft) == 2:
            tugmalar.append(juft)
            juft = []
    if juft:
        tugmalar.append(juft)
    return matn, InlineKeyboardMarkup(tugmalar) if tugmalar else None


async def sandiq(update: Update, context: ContextTypes.DEFAULT_TYPE):
    f = update.effective_user
    matn, t = await _bosh_korinish(f.id)
    await update.message.reply_text(matn, reply_markup=t)


async def sandiq_tugma(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    qismlar = q.data.split(":")
    amal, egasi = qismlar[1], int(qismlar[2])
    if q.from_user.id != egasi:
        await q.answer("Bu sizning sandig'ingiz emas. /sandiq yozing", show_alert=True)
        return
    if amal == "b":
        matn, t = await _bosh_korinish(egasi)
        await q.edit_message_text(matn, reply_markup=t)
        await q.answer()
        return
    k = qismlar[3]
    if k not in QUTILAR:
        await q.answer("Noma'lum quti", show_alert=True)
        return
    if amal == "o":
        t = InlineKeyboardMarkup([[
            _tugma("✅ Sotib olish", f"sq:y:{egasi}:{k}"),
            _tugma("⬅️ Orqaga", f"sq:b:{egasi}"),
        ]])
        await q.edit_message_text(
            f"{RAMKA}\n"
            f"📦 {NOMLAR[k]} qutisi\n\n"
            f"🎁 Tasodifiy {BELGI[k]} {NOMLAR[k]} waifu beradi\n"
            f"💰 Narx : 🪙 {narx(k)}\n\n"
            "Sotib olasizmi ?",
            reply_markup=t,
        )
        await q.answer()
        return
    # amal == "y": sotib olish
    kod, d = await sotib_ol(_baza, egasi, k)
    if kod != "ok":
        xabar = {
            "tanga_yetmaydi": f"💸 Tanga yetmaydi : kerak 🪙 {d.get('narx', narx(k))}",
            "limit": "⏳ Bugungi limit tugadi. Ertaga qayting !",
            "yopiq": "🚫 Bu quti hozir yopiq",
            "waifu_yoq": "⚠️ Bu darajada waifu yo'q. Adminga xabar bering",
        }.get(kod, "❌ Xatolik, qayta urinib ko'ring")
        await q.answer(xabar, show_alert=True)
        return
    p = d["p"]
    try:
        await q.message.reply_photo(
            p["file_id"],
            caption=(
                f"{RAMKA}\n"
                f"🎁 {NOMLAR[k]} qutisi ochildi !\n\n"
                f"🫧 {K(q.from_user.first_name)}\n"
                f"🗽 Ismi : {K(p['name'])}\n"
                f"🎗️ RANK : {_yulduz(p)}\n"
                f"👀 Manba : {K(p['anime'])}\n"
                f"🔢 Raqam : {p.get('raqam', '?')}\n\n"
                f"💰 Narx : 🪙 {d['narx']}\n"
                f"👛 Qoldiq : {d['coins']}"
            ),
            parse_mode="HTML",
        )
    except Exception as xato:
        logging.warning("Quti rasmini yuborib bo'lmadi: %s", xato)
        await q.message.reply_text(
            f"🎁 {NOMLAR[k]} qutisi ochildi : {K(p['name'])}", parse_mode="HTML"
        )
    matn, t = await _bosh_korinish(egasi)
    await q.edit_message_text(matn, reply_markup=t)
    await q.answer("🎁")


def ulash(ilova, baza, yulduz_matni):
    global _baza, _yulduz
    _baza = baza
    _yulduz = yulduz_matni
    ilova.add_handler(CommandHandler(["sandiq", "quti"], sandiq))
    ilova.add_handler(CallbackQueryHandler(sandiq_tugma, pattern=r"^sq:"))
