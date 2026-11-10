import html
import logging
import math
import time
import uuid
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes
from stil import stil
import sozlama as S

# Do'kon : o'yinchilar o'z waifularini o'zlari belgilagan narxda bir-biriga sotadi.
# Narx chegarasi daraja narxiga nisbatan (% , /panel dan o'zgartiriladi):
#   eng kami: oddiy darajalar 70%, COLLECTOR 80%; eng ko'pi: 110% (hamma daraja). MAX sotilmaydi.
# Narx qoidasi o'zgarsa, qoidaga mos kelmay qolgan e'lonlar avtomatik bekor bo'ladi (waifu egasiga qaytadi).
# E'lon qo'yilganda waifu sotuvchi kolleksiyasidan chiqib do'konga o'tadi (bekor qilsa qaytadi).
# Bot (/dokon, /sotish, /elonlarim) ham, Mini App (api.py) ham shu yerdagi funksiyalarni ishlatadi.
SOTILADI = ("common", "rare", "epic", "legendary", "special")
NOMLAR = {
    "common": "ELITA", "rare": "SUPER", "epic": "MEGA",
    "legendary": "ULTRA", "special": "COLLECTOR", "max": "MAX",
}
BELGI = {
    "common": "💠", "rare": "🌟", "epic": "💎", "legendary": "🔥",
    "special": "⛩️", "max": "👑",
}
SAHIFA = 8
RAMKA = "✨━ ━━━━━━━━━ ━✨"

_baza = None
_yulduz = None


def kalit(p):
    return str(p["rarity"]).lower()


def asosiy_narx(k):
    return S.ol("narx_" + k)


def min_narx(k):
    foiz = S.ol("bozor_min_col") if k == "special" else S.ol("bozor_min")
    return max(1, math.ceil(asosiy_narx(k) * foiz / 100))


def max_narx(k):
    # None = cheksiz
    m = S.ol("bozor_max")
    if m <= 0:
        return None
    return max(min_narx(k), math.floor(asosiy_narx(k) * m / 100))


def narx_oraliqlari():
    return {
        k: {"min": min_narx(k), "max": max_narx(k), "nom": NOMLAR[k]}
        for k in SOTILADI
    }


def K(x):
    return html.escape(str(x))


# ---------- Asosiy amallar (bot va Mini App uchun umumiy) ----------
TOZALASH_ORALIGI = 300  # soniya
_oxirgi_tozala = 0.0


def narx_joiz(k, narx):
    # E'lon narxi hozirgi qoidaga mosmi (daraja sotiladimi, eng kam va eng ko'p chegaralari)
    if k not in SOTILADI:
        return False
    if narx < min_narx(k):
        return False
    mx = max_narx(k)
    return mx is None or narx <= mx


async def tozala(baza, majbur=False):
    # Hozirgi narx qoidasiga mos kelmagan e'lonlarni bekor qiladi, waifu egasiga qaytadi.
    # Qiymatlar o'zgarganda (masalan, daraja narxlari oshirilganda) eski arzon e'lonlar qolib ketmasligi uchun.
    global _oxirgi_tozala
    hozir = time.time()
    if not majbur and hozir - _oxirgi_tozala < TOZALASH_ORALIGI:
        return 0
    _oxirgi_tozala = hozir
    qaytgan = 0
    try:
        royxat = [d async for d in baza["bozor"].find({}).limit(2000)]
        chars = {}
        for d in royxat:
            if d["c"] not in chars:
                chars[d["c"]] = await baza["characters"].find_one({"_id": d["c"]})
            p = chars[d["c"]]
            if p is None:
                # Waifu bazadan o'chirilgan: e'lon ham ketadi
                await baza["bozor"].find_one_and_delete({"_id": d["_id"]})
                continue
            if not narx_joiz(kalit(p), d["narx"]):
                kod, _ = await bekor(baza, d["u"], d["_id"])
                qaytgan += kod == "ok"
    except Exception as xato:
        logging.warning("Do'konni tozalab bo'lmadi: %s", xato)
    if qaytgan:
        logging.info("Narx qoidasiga mos kelmagan %s ta e'lon bekor qilindi", qaytgan)
    return qaytgan


async def elon_qil(baza, uid, p, narx):
    # (kod, malumot). kod: ok, yangi, yopiq, limit, taqiq, past, baland, topilmadi, xato
    k = kalit(p)
    if k not in SOTILADI:
        return "taqiq", {}
    qulf = await S.yangi_qulf(baza, uid)
    if qulf:
        return "yangi", {"qolgan": qulf}
    lim = S.ol("bozor_limit")
    if lim <= 0:
        return "yopiq", {}
    if narx < min_narx(k):
        return "past", {"min": min_narx(k)}
    mx = max_narx(k)
    if mx is not None and narx > mx:
        return "baland", {"max": mx}
    await tozala(baza)
    faol = await baza["bozor"].count_documents({"u": uid})
    if faol >= lim:
        return "limit", {"limit": lim}
    # Waifuni sotuvchidan olib tashlaymiz (bir marta, xavfsiz)
    olindi = await baza["collection"].find_one_and_delete(
        {"user_id": uid, "char_id": p["_id"]}
    )
    if not olindi:
        return "topilmadi", {}
    eid = uuid.uuid4().hex[:10]
    try:
        u = await baza["users"].find_one({"_id": uid}) or {}
        await baza["bozor"].insert_one({
            "_id": eid, "u": uid, "c": p["_id"], "narx": narx,
            "t": time.time(), "ism": u.get("name") or "Foydalanuvchi",
        })
    except Exception as xato:
        logging.warning("E'lon yozilmadi, waifu qaytarildi: %s", xato)
        await baza["collection"].insert_one({"user_id": uid, "char_id": p["_id"]})
        return "xato", {}
    return "ok", {"id": eid, "narx": narx}


async def bekor(baza, uid, eid):
    # (kod, malumot). kod: ok, yoq
    e = await baza["bozor"].find_one_and_delete({"_id": eid, "u": uid})
    if not e:
        return "yoq", {}
    await baza["collection"].insert_one({"user_id": uid, "char_id": e["c"]})
    return "ok", {}


async def sotib_ol(baza, uid, eid):
    # (kod, malumot). kod: ok, yangi, yoq, oz, tanga_yetmaydi, xato
    qulf = await S.yangi_qulf(baza, uid)
    if qulf:
        return "yangi", {"qolgan": qulf}
    e = await baza["bozor"].find_one({"_id": eid})
    if not e:
        return "yoq", {}
    if e["u"] == uid:
        return "oz", {}
    # Eski narxda qolib ketgan e'lonni sotib bo'lmaydi: qoidaga mos kelmasa bekor qilinadi
    p0 = await baza["characters"].find_one({"_id": e["c"]})
    if p0 is None or not narx_joiz(kalit(p0), e["narx"]):
        await bekor(baza, e["u"], eid)
        return "yoq", {}
    narx = e["narx"]
    users = baza["users"]
    # Avval xaridordan yechamiz (yetarli bo'lsa)
    r = await users.update_one(
        {"_id": uid, "coins": {"$gte": narx}}, {"$inc": {"coins": -narx}}
    )
    if r.modified_count == 0:
        u = await users.find_one({"_id": uid}) or {}
        return "tanga_yetmaydi", {"narx": narx, "coins": u.get("coins", 0)}
    # E'lonni bir marta olamiz: ikki kishi bir vaqtda bossa, bittasi oladi
    d = await baza["bozor"].find_one_and_delete({"_id": eid})
    if not d:
        await users.update_one({"_id": uid}, {"$inc": {"coins": narx}})
        return "yoq", {}
    try:
        await users.update_one({"_id": d["u"]}, {"$inc": {"coins": narx}}, upsert=True)
        await baza["collection"].insert_one({"user_id": uid, "char_id": d["c"]})
    except Exception as xato:
        logging.warning("Xarid bajarilmadi, qaytarildi: %s", xato)
        await users.update_one({"_id": uid}, {"$inc": {"coins": narx}})
        await baza["bozor"].insert_one(d)
        return "xato", {}
    p = await baza["characters"].find_one({"_id": d["c"]})
    u = await users.find_one({"_id": uid}) or {}
    return "ok", {"p": p, "narx": narx, "sotuvchi": d["u"], "coins": u.get("coins", 0)}


def _soz_mos(p, soz):
    # Qidiruv: faqat raqamlar bo'lsa raqam bo'yicha, aks holda ism yoki manba ichidan
    soz = " ".join(str(soz).split()).casefold().lstrip("#")
    if not soz:
        return True
    if soz.isdigit():
        return str(p.get("raqam")) == soz
    return soz in str(p.get("name", "")).casefold() or soz in str(p.get("anime", "")).casefold()


async def elonlar(baza, uid=None, raqam=None, soz=None):
    # [(elon, waifu)] eng yangisi birinchi. uid berilsa, faqat shu odamniki.
    # raqam: aniq waifu raqami. soz: ism, manba yoki raqam bo'yicha qidiruv.
    await tozala(baza)
    f = {}
    if uid is not None:
        f["u"] = uid
    royxat = [d async for d in baza["bozor"].find(f).limit(1000)]
    chars = {}
    for d in royxat:
        if d["c"] not in chars:
            chars[d["c"]] = await baza["characters"].find_one({"_id": d["c"]})
    natija = [
        (d, chars[d["c"]]) for d in royxat
        if chars.get(d["c"]) and (raqam is None or chars[d["c"]].get("raqam") == raqam)
        and (not soz or _soz_mos(chars[d["c"]], soz))
    ]
    natija.sort(key=lambda x: -x[0].get("t", 0))
    return natija


# ---------- Botdagi buyruqlar ----------
def _tugma(matn, data):
    return InlineKeyboardButton(stil(matn), callback_data=data)


def _qator(i, d, p):
    k = kalit(p)
    return (
        f"{i}. {BELGI.get(k, '')} {NOMLAR.get(k, k.upper())} • {K(p['name'])} "
        f"• № {p.get('raqam', '?')}\n"
        f"      💰 🪙 {d['narx']} • 🫧 {K(d.get('ism', ''))}"
    )


_soz = {}  # {odam: oxirgi qidiruv matni}: tugmalar bilan sahifa almashtirish uchun


async def _royxat_korinishi(uid, sahifa, filtr="0"):
    # filtr: "0" = hammasi, raqamlar = shu waifu raqami, "s" = odamning oxirgi qidiruv matni
    filtr = str(filtr)
    raqam, soz = None, None
    if filtr.isdigit() and int(filtr) > 0:
        raqam = int(filtr)
    elif filtr == "s":
        soz = _soz.get(uid)
        if not soz:
            filtr = "0"
    hammasi = await elonlar(_baza, None, raqam, soz)
    jami = max(1, math.ceil(len(hammasi) / SAHIFA))
    sahifa = max(0, min(sahifa, jami - 1))
    qism = hammasi[sahifa * SAHIFA:(sahifa + 1) * SAHIFA]
    sarlavha = f"{RAMKA}\n🏪 Do'kon"
    if raqam:
        sarlavha += f" • № {raqam}"
    elif soz:
        sarlavha += f" • 🔎 {K(soz)}"
    tozalash = [[_tugma("❌ Qidiruvni tozalash", f"bz:p:{uid}:0:0")]] if (raqam or soz) else []
    if not hammasi:
        return (
            f"{sarlavha}\n\n📭 "
            + ("Hech narsa topilmadi" if (raqam or soz) else "Hozircha e'lon yo'q")
            + "\n\n🔎 Qidirish : /dokon ism  yoki  /dokon raqam\n"
            "💡 O'z waifungizni sotish : /sotish raqam narx",
            InlineKeyboardMarkup(tozalash) if tozalash else None,
        )
    matn = (
        f"{sarlavha}\n\n"
        + "\n\n".join(_qator(sahifa * SAHIFA + i + 1, d, p) for i, (d, p) in enumerate(qism))
        + f"\n\n📄 {sahifa + 1}/{jami} • jami {len(hammasi)} ta e'lon\n"
        "🔎 Qidirish : /dokon ism  yoki  /dokon raqam\n"
        "💡 Sotish : /sotish raqam narx"
    )
    tugmalar = [
        [_tugma(f"🛒 {sahifa * SAHIFA + i + 1} • № {p.get('raqam', '?')} • 🪙 {d['narx']}",
                f"bz:o:{d['_id']}:{uid}:{sahifa}:{filtr}")]
        for i, (d, p) in enumerate(qism)
    ]
    if jami > 1:
        tugmalar.append([
            _tugma("◀️", f"bz:p:{uid}:{(sahifa - 1) % jami}:{filtr}"),
            _tugma(f"{sahifa + 1}/{jami}", f"bz:n:{uid}"),
            _tugma("▶️", f"bz:p:{uid}:{(sahifa + 1) % jami}:{filtr}"),
        ])
    return matn, InlineKeyboardMarkup(tugmalar + tozalash)


async def dokon(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    filtr = "0"
    if context.args:
        soz = " ".join(context.args).strip().lstrip("#")[:40]
        if soz.isdigit():
            filtr = str(int(soz))  # 0 bo'lsa, hammasi
        elif soz:
            _soz[uid] = soz
            filtr = "s"
    matn, t = await _royxat_korinishi(uid, 0, filtr)
    await update.message.reply_text(matn, reply_markup=t, parse_mode="HTML")


def _xato_matni(kod, d):
    return {
        "yangi": f"🔒 Yangi foydalanuvchilar {S.ol('yangi_soat')} soat savdo qila olmaydi.\n"
                 f"⏳ Qolgan vaqt : {S.vaqt_matni(d.get('qolgan', 0))}",
        "yopiq": "🚫 Do'kon hozir yopiq",
        "limit": f"⛔ Bir vaqtda {d.get('limit', S.ol('bozor_limit'))} tagacha e'lon qo'yish mumkin. "
                 "Avval birortasini bekor qiling (/elonlarim)",
        "taqiq": "🚫 MAX waifuni sotib bo'lmaydi !",
        "past": f"⚠️ Narx juda past. Bu daraja uchun eng kami : 🪙 {d.get('min')}",
        "baland": f"⚠️ Narx juda baland. Bu daraja uchun eng ko'pi : 🪙 {d.get('max')}",
        "topilmadi": "🔍 Bu waifu kolleksiyangizda yo'q",
        "yoq": "⌛ Bu e'lon endi mavjud emas (sotilgan yoki bekor qilingan)",
        "oz": "❌ O'zingizning e'loningizni sotib ololmaysiz",
        "tanga_yetmaydi": f"💸 Tanga yetmaydi : kerak 🪙 {d.get('narx')}",
    }.get(kod, "❌ Xatolik, qayta urinib ko'ring")


async def sotish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    xabar = update.message
    f = update.effective_user
    args = context.args
    if len(args) != 2 or not all(a.lstrip("#").isdigit() for a in args):
        qatorlar = []
        for k in SOTILADI:
            mx = max_narx(k)
            qatorlar.append(
                f"{BELGI[k]} {NOMLAR[k]} : 🪙 {min_narx(k)} — "
                + (f"🪙 {mx}" if mx is not None else "cheksiz")
            )
        await xabar.reply_text(
            "🏪 Waifuni do'konda sotish\n\n"
            "<code>/sotish 4821 500</code>\n"
            "4821 - waifu raqami, 500 - o'zingiz qo'ygan narx.\n\n"
            "💰 Ruxsat etilgan narxlar:\n" + "\n".join(qatorlar) + "\n\n"
            "Ko'rish : /dokon • E'lonlaringiz : /elonlarim",
            parse_mode="HTML",
        )
        return
    raqam, narx = int(args[0].lstrip("#")), int(args[1].lstrip("#"))
    p = await _baza["characters"].find_one({"raqam": raqam})
    if not p:
        await xabar.reply_text("🔍 Bunday raqamli waifu yo'q")
        return
    kod, d = await elon_qil(_baza, f.id, p, narx)
    if kod != "ok":
        await xabar.reply_text(_xato_matni(kod, d))
        return
    k = kalit(p)
    await xabar.reply_text(
        f"{RAMKA}\n"
        "🏪 E'lon qo'yildi !\n\n"
        f"🗽 {K(p['name'])} • {_yulduz(p)}\n"
        f"🔢 Raqam : {p.get('raqam', '?')}\n"
        f"💰 Narx : 🪙 {narx}\n\n"
        "Bekor qilish : /elonlarim",
        parse_mode="HTML",
    )


async def _mening_korinishi(uid):
    royxat = await elonlar(_baza, uid)
    if not royxat:
        return "📭 Sizda faol e'lon yo'q\n\n💡 Sotish : /sotish raqam narx", None
    matn = f"{RAMKA}\n📋 Mening e'lonlarim\n\n" + "\n\n".join(
        _qator(i + 1, d, p) for i, (d, p) in enumerate(royxat)
    ) + "\n\n❌ Bekor qilsangiz, waifu o'zingizga qaytadi"
    tugmalar = [
        [_tugma(f"❌ {i + 1} • № {p.get('raqam', '?')} bekor", f"bz:c:{d['_id']}:{uid}")]
        for i, (d, p) in enumerate(royxat)
    ]
    return matn, InlineKeyboardMarkup(tugmalar)


async def elonlarim(update: Update, context: ContextTypes.DEFAULT_TYPE):
    matn, t = await _mening_korinishi(update.effective_user.id)
    await update.message.reply_text(matn, reply_markup=t, parse_mode="HTML")


async def bozor_tugma(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    qismlar = q.data.split(":")
    amal = qismlar[1]
    if amal == "n":
        await q.answer()
        return
    # Tugmalarni faqat buyruqni bergan odam bosa oladi
    egasi = int(qismlar[3] if amal in ("o", "y", "c") else qismlar[2])
    if q.from_user.id != egasi:
        await q.answer("Bu sizning do'koningiz emas. /dokon yozing", show_alert=True)
        return
    if amal == "p":
        matn, t = await _royxat_korinishi(egasi, int(qismlar[3]), qismlar[4])
        await q.edit_message_text(matn, reply_markup=t, parse_mode="HTML")
        await q.answer()
        return
    if amal == "c":
        kod, d = await bekor(_baza, egasi, qismlar[2])
        if kod != "ok":
            await q.answer(_xato_matni("yoq", d), show_alert=True)
        matn, t = await _mening_korinishi(egasi)
        await q.edit_message_text(matn, reply_markup=t, parse_mode="HTML")
        await q.answer("✅ Bekor qilindi" if kod == "ok" else "")
        return
    eid = qismlar[2]
    if amal == "o":
        e = await _baza["bozor"].find_one({"_id": eid})
        p = await _baza["characters"].find_one({"_id": e["c"]}) if e else None
        if not e or not p:
            await q.answer(_xato_matni("yoq", {}), show_alert=True)
            return
        if e["u"] == egasi:
            await q.answer(_xato_matni("oz", {}), show_alert=True)
            return
        t = InlineKeyboardMarkup([[
            _tugma("✅ Sotib olish", f"bz:y:{eid}:{egasi}:{qismlar[4]}:{qismlar[5]}"),
            _tugma("⬅️ Orqaga", f"bz:p:{egasi}:{qismlar[4]}:{qismlar[5]}"),
        ]])
        await q.edit_message_text(
            f"{RAMKA}\n"
            "🛒 Sotib olasizmi ?\n\n"
            f"🗽 Ismi : {K(p['name'])}\n"
            f"🎗️ RANK : {_yulduz(p)}\n"
            f"👀 Manba : {K(p['anime'])}\n"
            f"🔢 Raqam : {p.get('raqam', '?')}\n\n"
            f"💰 Narx : 🪙 {e['narx']}\n"
            f"🫧 Sotuvchi : {K(e.get('ism', ''))}",
            reply_markup=t, parse_mode="HTML",
        )
        await q.answer()
        return
    # amal == "y": sotib olish
    kod, d = await sotib_ol(_baza, egasi, eid)
    if kod != "ok":
        await q.answer(_xato_matni(kod, d), show_alert=True)
        if kod in ("yoq", "yangi"):
            matn, t = await _royxat_korinishi(egasi, int(qismlar[4]), qismlar[5])
            await q.edit_message_text(matn, reply_markup=t, parse_mode="HTML")
        return
    p = d["p"]
    try:
        await q.message.reply_photo(
            p["file_id"],
            caption=(
                f"{RAMKA}\n"
                "🛒 Sotib olindi !\n\n"
                f"🫧 {K(q.from_user.first_name)}\n"
                f"🗽 Ismi : {K(p['name'])}\n"
                f"🎗️ RANK : {_yulduz(p)}\n"
                f"🔢 Raqam : {p.get('raqam', '?')}\n\n"
                f"💰 Narx : 🪙 {d['narx']}\n"
                f"👛 Qoldiq : {d['coins']}"
            ),
            parse_mode="HTML",
        )
    except Exception as xato:
        logging.warning("Xarid rasmini yuborib bo'lmadi: %s", xato)
    # Sotuvchiga xabar
    try:
        await context.bot.send_message(
            d["sotuvchi"],
            f"💰 Waifuingiz sotildi !\n\n🗽 {K(p['name'])} • № {p.get('raqam', '?')}\n"
            f"🪙 +{d['narx']}",
            parse_mode="HTML",
        )
    except Exception:
        pass
    matn, t = await _royxat_korinishi(egasi, int(qismlar[4]), qismlar[5])
    await q.edit_message_text(matn, reply_markup=t, parse_mode="HTML")
    await q.answer("🛒")


def ulash(ilova, baza, yulduz_matni):
    global _baza, _yulduz
    _baza = baza
    _yulduz = yulduz_matni
    ilova.add_handler(CommandHandler("dokon", dokon))
    ilova.add_handler(CommandHandler("sotish", sotish))
    ilova.add_handler(CommandHandler("elonlarim", elonlarim))
    ilova.add_handler(CallbackQueryHandler(bozor_tugma, pattern=r"^bz:"))
