import io
import re
import html
from datetime import datetime, timedelta, timezone
from bson import ObjectId, json_util
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler,
    filters,
)
from royxat import DARAJA_EMOJI, manba_kalit

TOSHKENT = timezone(timedelta(hours=5))
ZAXIRA_JADVALLAR = ["users", "characters", "collection", "allowed_chats"]

_baza = None
_admin_id = 0
_kalit = None
_nodirlik = {}


def admin_mi(update):
    u = update.effective_user
    return bool(u) and u.id == _admin_id


def shaxsiy_mi(update):
    return update.effective_chat.type == "private"


async def personaj_top(s):
    # Raqam, #kod yoki to'liq ism bo'yicha topadi
    s = str(s).strip().lstrip("#")
    p = _baza["characters"]
    if s.isdigit():
        d = await p.find_one({"raqam": int(s)})
        if d:
            return d
    async for d in p.find({}):
        if str(d["_id"])[-4:].lower() == s.lower():
            return d
    return await p.find_one(
        {"name": {"$regex": f"^{re.escape(s)}$", "$options": "i"}}
    )


async def yangila(q, matn):
    # Rasmli yoki oddiy xabarni yangilaydi (tugmalar olib tashlanadi)
    if q.message.photo:
        await q.edit_message_caption(caption=matn)
    else:
        await q.edit_message_text(matn)


# ---------- /admin ----------
async def admin_yordam(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not admin_mi(update):
        return
    await update.message.reply_text(
        "🛠 Admin buyruqlari\n\n"
        "/royxat — hamma waifular\n"
        "/statistika — hisobot\n"
        "/zaxira — bazaning nusxasi\n\n"
        "<code>/ochirish 4821</code>\n"
        "<code>/tahrirlash 4821 | Ism | Manba | Nodirlik</code>\n"
        "(o'zgarmasin desangiz - yozing)\n"
        "<code>/royxat mega</code>  yoki  <code>/royxat re:zero</code>\n"
        "/tiklash — zaxira faylini yuborib, izohga yozing",
        parse_mode="HTML",
    )


# ---------- /royxat ----------
async def royxat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not admin_mi(update) or not shaxsiy_mi(update):
        return
    xabar = update.message
    suz = " ".join(context.args).strip()
    hammasi = [d async for d in _baza["characters"].find({})]
    if suz:
        kalit = _kalit(suz)
        if kalit:
            hammasi = [
                d for d in hammasi
                if str(d.get("rarity", "")).lower() == kalit
            ]
        else:
            s = suz.casefold()
            hammasi = [
                d for d in hammasi
                if s in str(d.get("anime", "")).casefold()
                or s in str(d.get("name", "")).casefold()
            ]
    if not hammasi:
        await xabar.reply_text("🔍 Hech narsa topilmadi")
        return
    hammasi.sort(
        key=lambda d: (manba_kalit(d.get("anime", "")), d.get("raqam", 0))
    )
    qatorlar = []
    joriy_manba = None
    for d in hammasi:
        m = " ".join(str(d.get("anime", "")).split())
        if manba_kalit(m) != joriy_manba:
            joriy_manba = manba_kalit(m)
            qatorlar.append(f"\n➤ {html.escape(m)}")
        belgi = DARAJA_EMOJI.get(str(d.get("rarity", "")).lower(), "🔸")
        qatorlar.append(
            f"{d.get('raqam', '?')} {belgi} {html.escape(str(d['name']))}"
        )
    qismlar, joriy = [], ""
    for q in qatorlar:
        if len(joriy) + len(q) + 1 > 3500:
            qismlar.append(joriy)
            joriy = ""
        joriy += q + "\n"
    if joriy:
        qismlar.append(joriy)
    await xabar.reply_text(f"📋 Waifular : {len(hammasi)} ta")
    for q in qismlar:
        await xabar.reply_text(q, parse_mode="HTML")


# ---------- /statistika ----------
async def statistika(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not admin_mi(update) or not shaxsiy_mi(update):
        return
    p = _baza["characters"]
    jami = await p.count_documents({})
    satrlar = []
    for kalit, (nom, _) in _nodirlik.items():
        n = await p.count_documents(
            {"rarity": {"$in": [kalit, kalit.capitalize()]}}
        )
        satrlar.append(f"{nom} : {n}")
    manbalar = {
        manba_kalit(d.get("anime", ""))
        async for d in p.find({}, {"anime": 1})
    }
    foyd = await _baza["users"].count_documents({})
    kol = await _baza["collection"].count_documents({})
    guruh = await _baza["allowed_chats"].count_documents({})
    tanga = 0
    async for u in _baza["users"].find({}, {"coins": 1}):
        tanga += u.get("coins", 0)
    await update.message.reply_text(
        "📊 Statistika\n\n"
        f"🎴 Waifular : {jami}\n"
        + "\n".join(satrlar)
        + f"\n\n🔖 Manbalar : {len(manbalar)}\n"
        f"👥 Foydalanuvchilar : {foyd}\n"
        f"🗂 Kolleksiyadagi waifular : {kol}\n"
        f"💬 Tasdiqlangan guruhlar : {guruh}\n"
        f"💰 Jami tanga : {tanga}"
    )


# ---------- /ochirish ----------
async def ochirish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not admin_mi(update) or not shaxsiy_mi(update):
        return
    xabar = update.message
    if not context.args:
        await xabar.reply_text(
            "🗑 O'chirish : <code>/ochirish 4821</code>", parse_mode="HTML"
        )
        return
    p = await personaj_top(" ".join(context.args))
    if not p:
        await xabar.reply_text("🔍 Bunday waifu topilmadi")
        return
    n = await _baza["collection"].count_documents({"char_id": p["_id"]})
    matn = (
        "🗑 O'chirilsinmi ?\n\n"
        f"🔢 Raqam : {p.get('raqam', '?')}\n"
        f"🗽 Ismi : {html.escape(str(p['name']))}\n"
        f"👀 Manba : {html.escape(str(p['anime']))}\n"
        f"👥 Kolleksiyalarda : {n} ta"
    )
    tugma = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Ha", callback_data=f"oc:ha:{p['_id']}"),
        InlineKeyboardButton("❌ Yo'q", callback_data="oc:yoq"),
    ]])
    await xabar.reply_photo(
        p["file_id"], caption=matn, parse_mode="HTML", reply_markup=tugma
    )


async def ochirish_tugma(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if q.from_user.id != _admin_id:
        await q.answer("Faqat admin", show_alert=True)
        return
    qism = q.data.split(":")
    if qism[1] == "yoq":
        await yangila(q, "❌ Bekor qilindi")
        await q.answer()
        return
    pid = ObjectId(qism[2])
    p = await _baza["characters"].find_one({"_id": pid})
    if not p:
        await yangila(q, "❌ Waifu topilmadi (allaqachon o'chirilgan)")
        await q.answer()
        return
    k = await _baza["collection"].delete_many({"char_id": pid})
    await _baza["spawns"].delete_many({"char_id": pid})
    await _baza["characters"].delete_one({"_id": pid})
    await yangila(
        q,
        f"🗑 O'chirildi : {p.get('raqam', '?')} {p['name']}\n"
        f"👥 Kolleksiyalardan olib tashlandi : {k.deleted_count} ta",
    )
    await q.answer("🗑")


# ---------- /tahrirlash ----------
async def tahrirlash(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not admin_mi(update) or not shaxsiy_mi(update):
        return
    xabar = update.message
    matn = re.sub(r"^/\w+(@\w+)?", "", xabar.text or "").strip()
    qismlar = [q.strip() for q in matn.split("|")]
    if len(qismlar) != 4:
        await xabar.reply_text(
            "✏️ Tahrirlash :\n"
            "<code>/tahrirlash 4821 | Ism | Manba | Nodirlik</code>\n"
            "O'zgarmasin desangiz - yozing, masalan:\n"
            "<code>/tahrirlash 4821 | - | - | Mega</code>",
            parse_mode="HTML",
        )
        return
    kim, ism, manba, nodirlik = qismlar
    p = await personaj_top(kim)
    if not p:
        await xabar.reply_text("🔍 Bunday waifu topilmadi")
        return
    yangi = {}
    if ism and ism != "-":
        yangi["name"] = ism
    if manba and manba != "-":
        yangi["anime"] = manba
    if nodirlik and nodirlik != "-":
        k = _kalit(nodirlik)
        if not k:
            await xabar.reply_text(
                "❌ Nodirlik : Yaxshi, Ajoyib, Super, Mega yoki Maxsus"
            )
            return
        yangi["rarity"] = k
    if not yangi:
        await xabar.reply_text("ℹ️ Hech narsa o'zgartirilmadi")
        return
    await _baza["characters"].update_one({"_id": p["_id"]}, {"$set": yangi})
    p = await _baza["characters"].find_one({"_id": p["_id"]})
    await xabar.reply_text(
        "✅ Yangilandi\n\n"
        f"🔢 Raqam : {p.get('raqam', '?')}\n"
        f"🗽 Ismi : {html.escape(str(p['name']))}\n"
        f"👀 Manba : {html.escape(str(p['anime']))}\n"
        f"💎 Nodirlik : {_nodirlik.get(str(p['rarity']).lower(), ('?',))[0]}",
        parse_mode="HTML",
    )


# ---------- Zaxira va tiklash ----------
async def zaxira_baytlar(baza):
    malumot = {}
    for nom in ZAXIRA_JADVALLAR:
        malumot[nom] = [d async for d in baza[nom].find({})]
    sana = datetime.now(TOSHKENT)
    paket = {
        "versiya": 1,
        "sana": sana.isoformat(),
        "jadvallar": malumot,
    }
    baytlar = json_util.dumps(paket, ensure_ascii=False).encode("utf-8")
    hisob = {n: len(v) for n, v in malumot.items()}
    return baytlar, hisob, sana


async def zaxira(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not admin_mi(update) or not shaxsiy_mi(update):
        return
    baytlar, hisob, sana = await zaxira_baytlar(_baza)
    await update.message.reply_document(
        document=io.BytesIO(baytlar),
        filename=f"zaxira_{sana:%Y-%m-%d_%H%M}.json",
        caption=(
            "💾 Zaxira nusxa\n"
            f"🎴 Waifu : {hisob['characters']}\n"
            f"👥 Foydalanuvchi : {hisob['users']}\n"
            f"🗂 Kolleksiya : {hisob['collection']}"
        ),
    )


async def tiklash(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not admin_mi(update) or not shaxsiy_mi(update):
        return
    xabar = update.message
    hujjat = xabar.document
    if not hujjat and xabar.reply_to_message:
        hujjat = xabar.reply_to_message.document
    if not hujjat:
        await xabar.reply_text(
            "♻️ Tiklash : zaxira faylini yuboring va izohga /tiklash yozing "
            "(yoki faylga javob berib /tiklash yozing)"
        )
        return
    if hujjat.file_size and hujjat.file_size > 15 * 1024 * 1024:
        await xabar.reply_text("❌ Fayl juda katta")
        return
    fayl = await hujjat.get_file()
    baytlar = bytes(await fayl.download_as_bytearray())
    try:
        paket = json_util.loads(baytlar.decode("utf-8"))
        jadvallar = paket["jadvallar"]
        for nom in ZAXIRA_JADVALLAR:
            if nom not in jadvallar:
                raise ValueError(nom)
    except Exception:
        await xabar.reply_text("❌ Bu zaxira fayli emas yoki buzilgan")
        return
    context.bot_data["tiklash"] = jadvallar
    tugma = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Tiklansin", callback_data="tz:ha"),
        InlineKeyboardButton("❌ Bekor", callback_data="tz:yoq"),
    ]])
    await xabar.reply_text(
        "♻️ Zaxira fayli o'qildi\n\n"
        f"🎴 Waifu : {len(jadvallar['characters'])}\n"
        f"👥 Foydalanuvchi : {len(jadvallar['users'])}\n"
        f"🗂 Kolleksiya : {len(jadvallar['collection'])}\n"
        f"📅 Sana : {paket.get('sana', '?')[:16]}\n\n"
        "⚠️ Hozirgi ma'lumot o'chib, shu fayl bilan almashtiriladi.\n"
        "Oldin hozirgi holatning zaxirasi sizga yuboriladi.",
        reply_markup=tugma,
    )


async def tiklash_tugma(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if q.from_user.id != _admin_id:
        await q.answer("Faqat admin", show_alert=True)
        return
    if q.data == "tz:yoq":
        context.bot_data.pop("tiklash", None)
        await q.edit_message_text("❌ Tiklash bekor qilindi")
        await q.answer()
        return
    jadvallar = context.bot_data.pop("tiklash", None)
    if not jadvallar:
        await q.edit_message_text(
            "❌ Fayl topilmadi (bot qayta ishga tushgan bo'lishi mumkin). "
            "Faylni qayta yuboring"
        )
        await q.answer()
        return
    # Xavfsizlik uchun hozirgi holatni oldin yuboramiz
    baytlar, hisob, sana = await zaxira_baytlar(_baza)
    await context.bot.send_document(
        q.message.chat_id,
        document=io.BytesIO(baytlar),
        filename=f"oldingi_holat_{sana:%Y-%m-%d_%H%M}.json",
        caption="💾 Tiklashdan oldingi holat (xavfsizlik uchun)",
    )
    for nom in ZAXIRA_JADVALLAR:
        await _baza[nom].delete_many({})
        if jadvallar[nom]:
            await _baza[nom].insert_many(jadvallar[nom], ordered=False)
    await q.edit_message_text(
        "✅ Tiklandi\n\n"
        f"🎴 Waifu : {len(jadvallar['characters'])}\n"
        f"👥 Foydalanuvchi : {len(jadvallar['users'])}\n"
        f"🗂 Kolleksiya : {len(jadvallar['collection'])}"
    )
    await q.answer("✅")


# ---------- main.py ga ulash ----------
def ulash(ilova, baza, admin_id, nodirlik_kaliti, nodirlik):
    global _baza, _admin_id, _kalit, _nodirlik
    _baza = baza
    _admin_id = admin_id
    _kalit = nodirlik_kaliti
    _nodirlik = nodirlik
    ilova.add_handler(CommandHandler("admin", admin_yordam))
    ilova.add_handler(CommandHandler("royxat", royxat))
    ilova.add_handler(CommandHandler("statistika", statistika))
    ilova.add_handler(CommandHandler("ochirish", ochirish))
    ilova.add_handler(CommandHandler("tahrirlash", tahrirlash))
    ilova.add_handler(CommandHandler("zaxira", zaxira))
    ilova.add_handler(CommandHandler("tiklash", tiklash))
    ilova.add_handler(
        MessageHandler(
            filters.Document.ALL & filters.CaptionRegex(r"^/tiklash"), tiklash
        )
    )
    ilova.add_handler(CallbackQueryHandler(ochirish_tugma, pattern=r"^oc:"))
    ilova.add_handler(CallbackQueryHandler(tiklash_tugma, pattern=r"^tz:"))
