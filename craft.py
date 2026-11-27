import html
import logging
import random
import re
from datetime import datetime, timedelta, timezone
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes
from stil import stil
import sozlama as S

# Craft : bir xil waifudan bir nechta nusxani birlashtirib, o'sha waifuning
# keyingi darajadagi versiyasini olish. Faqat asosiy guruhda ishlaydi.
# Keyingi daraja versiyasi bazada bo'lmasa, hech narsa olinmaydi.
# Narx, soni va kunlik limit /panel -> Craft bo'limidan o'zgartiriladi.
TOSHKENT = timezone(timedelta(hours=5))
TARTIB = ("common", "rare", "epic", "legendary", "special", "max")
NOM = {"common": "ELITA", "rare": "SUPER", "epic": "MEGA",
       "legendary": "ULTRA", "special": "COLLECTOR", "max": "MAX"}
BELGI = {"common": "💠", "rare": "🌟", "epic": "💎",
         "legendary": "🔥", "special": "⛩️", "max": "👑"}
RAMKA = "✨━ ━━━━━━━━━ ━✨"
BETDA = 6

_baza = None
_yulduz = None
_guruh = ""


def bugun():
    return datetime.now(TOSHKENT).strftime("%Y-%m-%d")


def K(x):
    return html.escape(str(x))


def daraja(p):
    d = str(p.get("rarity", "")).lower()
    return d if d in TARTIB else None


def keyingi(d):
    i = TARTIB.index(d)
    return TARTIB[i + 1] if i + 1 < len(TARTIB) else None


# Zaxira qiymatlar: sozlama.py eski bo'lsa ham craft ishlayveradi
ZAXIRA = {
    "craft_limit": 3,
    "craft_soni_common": 5, "craft_soni_rare": 5, "craft_soni_epic": 6,
    "craft_soni_legendary": 8, "craft_soni_special": 10,
    "craft_narx_common": 150, "craft_narx_rare": 400, "craft_narx_epic": 900,
    "craft_narx_legendary": 3500, "craft_narx_special": 9000,
}


def _ol(kalit):
    try:
        return S.ol(kalit)
    except Exception:
        return ZAXIRA[kalit]


def soni(d):
    return _ol("craft_soni_" + d)


def narx(d):
    return _ol("craft_narx_" + d)


def limit():
    return _ol("craft_limit")


def shart(d):
    return {"rarity": {"$in": [d, d.capitalize(), d.upper()]}}


def toza(ism):
    # Ism boshi va oxiridagi emoji/belgilar olib tashlanadi, katta-kichik harf farqsiz
    ism = str(ism or "").strip()
    i, j = 0, len(ism)
    while i < j and not ism[i].isalnum():
        i += 1
    while j > i and not ism[j - 1].isalnum():
        j -= 1
    return " ".join(ism[i:j].split()).casefold()


async def versiyalar(baza, p):
    # Shu waifuning (emoji va belgilarga qaramay bir xil ism) keyingi daraja versiyalari.
    # Manba mos bo'lsa faqat shular.
    d = daraja(p)
    n = keyingi(d) if d else None
    asos = toza(p.get("name"))
    if not n or not asos:
        return []
    q = dict(shart(n), name={"$regex": re.escape(asos), "$options": "i"})
    topilgan = [x async for x in baza["characters"].find(q).limit(100)
                if toza(x.get("name")) == asos]
    mos = [x for x in topilgan
           if str(x.get("anime", "")).strip().lower() == str(p.get("anime", "")).strip().lower()]
    return mos or topilgan


async def maqsad(baza, p):
    # Bir nechta versiya bo'lsa tasodifiy bittasi
    v = await versiyalar(baza, p)
    return random.choice(v) if v else None


async def qolgan(baza, uid):
    u = await baza["users"].find_one({"_id": uid}) or {}
    ishl = u.get("craft_n", 0) if u.get("craft_sana") == bugun() else 0
    return max(limit() - ishl, 0), u.get("coins", 0)


async def mumkinlar(baza, uid):
    # [(waifu, nusxa soni, maqsad)] : yetarli nusxasi va keyingi daraja versiyasi bor
    eng_kam = min(soni(d) for d in TARTIB[:-1])
    guruh = baza["collection"].aggregate([
        {"$match": {"user_id": uid}},
        {"$group": {"_id": "$char_id", "n": {"$sum": 1}}},
        {"$match": {"n": {"$gte": eng_kam}}},
    ])
    sonlar = {g["_id"]: g["n"] async for g in guruh}
    if not sonlar:
        return []
    natija = []
    async for p in baza["characters"].find({"_id": {"$in": list(sonlar)}}):
        d = daraja(p)
        if not d or d == "max" or sonlar[p["_id"]] < soni(d):
            continue
        m = await maqsad(baza, p)
        if m:
            natija.append((p, sonlar[p["_id"]], m))
    natija.sort(key=lambda t: (TARTIB.index(daraja(t[0])), str(t[0].get("name", "")).lower()))
    return natija


async def craft_qil(baza, uid, raqam):
    # (kod, malumot). kod: ok, yoq, versiya_yoq, limit, tanga_yetmaydi, nusxa_yetmaydi, xato
    p = await baza["characters"].find_one({"raqam": raqam})
    if not p:
        return "yoq", {}
    d = daraja(p)
    if not d or d == "max":
        return "versiya_yoq", {}
    m = await maqsad(baza, p)
    if not m:
        return "versiya_yoq", {}
    kerak, pul, lim = soni(d), narx(d), limit()
    if lim <= 0:
        return "limit", {}
    users, col = baza["users"], baza["collection"]
    b = bugun()
    await users.update_one({"_id": uid, "craft_sana": {"$ne": b}},
                           {"$set": {"craft_sana": b, "craft_n": 0}})
    r = await users.update_one(
        {"_id": uid, "coins": {"$gte": pul}, "craft_sana": b, "craft_n": {"$lt": lim}},
        {"$inc": {"coins": -pul, "craft_n": 1}},
    )
    if r.modified_count == 0:
        u = await users.find_one({"_id": uid}) or {}
        if u.get("craft_sana") == b and u.get("craft_n", 0) >= lim:
            return "limit", {}
        if u.get("coins", 0) < pul:
            return "tanga_yetmaydi", {"narx": pul}
        return "xato", {}

    async def qaytar(nusxa=0):
        for _ in range(nusxa):
            await col.insert_one({"user_id": uid, "char_id": p["_id"]})
        await users.update_one({"_id": uid}, {"$inc": {"coins": pul, "craft_n": -1}})

    try:
        idlar = [x["_id"] async for x in col.find({"user_id": uid, "char_id": p["_id"]}).limit(kerak)]
        if len(idlar) < kerak:
            await qaytar()
            return "nusxa_yetmaydi", {"kerak": kerak, "bor": len(idlar)}
        o = await col.delete_many({"_id": {"$in": idlar}})
        if o.deleted_count != kerak:
            await qaytar(o.deleted_count)
            return "xato", {}
    except Exception as xato:
        logging.warning("Craft: nusxalarni olib bo'lmadi: %s", xato)
        await qaytar()
        return "xato", {}
    try:
        await col.insert_one({"user_id": uid, "char_id": m["_id"]})
    except Exception as xato:
        logging.warning("Craft: yangi waifu berilmadi, qaytarildi: %s", xato)
        await qaytar(kerak)
        return "xato", {}
    if await col.count_documents({"user_id": uid, "char_id": p["_id"]}) == 0:
        # Oxirgi nusxa ketdi : sevimlilardan ham olib tashlanadi
        await users.update_one({"_id": uid}, {"$pull": {"yuraklar": p["_id"]}})
        await users.update_one({"_id": uid, "sevimli": p["_id"]}, {"$unset": {"sevimli": ""}})
    u = await users.find_one({"_id": uid}) or {}
    return "ok", {"p": p, "m": m, "kerak": kerak, "narx": pul, "coins": u.get("coins", 0)}


# ---------- Bot ----------
def _t(matn, data):
    return InlineKeyboardButton(stil(matn), callback_data=data)


def _asosiy(update):
    c = update.effective_chat
    return bool(c and (getattr(c, "username", None) or "").lower() == _guruh)


async def _royxat(uid, sahifa):
    q, tanga = await qolgan(_baza, uid)
    royxat = await mumkinlar(_baza, uid)
    qoidalar = "\n".join(
        f"{BELGI[d]} {NOM[d]} → {BELGI[keyingi(d)]} {NOM[keyingi(d)]} : {soni(d)}× + 🪙 {narx(d)}"
        for d in TARTIB[:-1]
    )
    bosh = (
        f"{RAMKA}\n⚒️ Craft\n\n"
        "Bir xil waifuning nusxalarini birlashtirib, o'sha waifuning keyingi daraja versiyasini oling\n\n"
        f"{qoidalar}\n\n"
        f"🔁 Bugun : {q}/{limit()}  •  👛 {tanga}\n\n"
    )
    if not royxat:
        return bosh + "Hozircha craft qilinadigan waifu yo'q. Bir xil waifudan yetarli nusxa va uning yuqori daraja versiyasi kerak.", None
    jami = (len(royxat) + BETDA - 1) // BETDA
    sahifa = max(0, min(sahifa, jami - 1))
    qator = []
    for p, n, m in royxat[sahifa * BETDA:(sahifa + 1) * BETDA]:
        d = daraja(p)
        qator.append([_t(f"{BELGI[d]} {p['name']} ×{n} → {NOM[keyingi(d)]}", f"cr:s:{uid}:{p['raqam']}")])
    if jami > 1:
        nav = []
        if sahifa > 0:
            nav.append(_t("⬅️", f"cr:l:{uid}:{sahifa - 1}"))
        nav.append(_t(f"{sahifa + 1}/{jami}", f"cr:l:{uid}:{sahifa}"))
        if sahifa < jami - 1:
            nav.append(_t("➡️", f"cr:l:{uid}:{sahifa + 1}"))
        qator.append(nav)
    return bosh + "Tanlang :", InlineKeyboardMarkup(qator)


async def craft(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _asosiy(update):
        await update.message.reply_text(
            "⚒️ Craft faqat asosiy guruhda ishlaydi",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton(stil("➡️ Asosiy guruhga o'tish"), url=f"https://t.me/{_guruh}")
            ]]),
        )
        return
    try:
        matn, t = await _royxat(update.effective_user.id, 0)
    except Exception as xato:
        logging.exception("Craft ro'yxatida xato")
        await update.message.reply_text(f"❌ Craft xatosi : {type(xato).__name__} {xato}")
        return
    await update.message.reply_text(matn, reply_markup=t)


async def craft_tugma(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        await _tugma_ish(update, context)
    except Exception as xato:
        logging.exception("Craft tugmasida xato")
        try:
            await update.callback_query.answer(f"❌ Xato : {type(xato).__name__}", show_alert=True)
        except Exception:
            pass


async def _tugma_ish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    qism = q.data.split(":")
    amal, egasi = qism[1], int(qism[2])
    if q.from_user.id != egasi:
        await q.answer("Bu sizning craftingiz emas. /craft yozing", show_alert=True)
        return
    if not _asosiy(update):
        await q.answer("Craft faqat asosiy guruhda", show_alert=True)
        return
    if amal == "l":
        matn, t = await _royxat(egasi, int(qism[3]))
        await q.edit_message_text(matn, reply_markup=t)
        await q.answer()
        return
    raqam = int(qism[3])
    if amal == "s":
        p = await _baza["characters"].find_one({"raqam": raqam})
        v = await versiyalar(_baza, p) if p else []
        d = daraja(p) if p else None
        if not p or not v or not d or d == "max":
            await q.answer("Bu waifuni craft qilib bo'lmaydi", show_alert=True)
            return
        qol, tanga = await qolgan(_baza, egasi)
        bor = await _baza["collection"].count_documents({"user_id": egasi, "char_id": p["_id"]})
        t = InlineKeyboardMarkup([[
            _t("✅ Craft qilish", f"cr:y:{egasi}:{raqam}"),
            _t("⬅️ Orqaga", f"cr:l:{egasi}:0"),
        ]])
        await q.edit_message_text(
            f"{RAMKA}\n⚒️ Craft\n\n"
            f"🗽 {K(p['name'])}\n"
            f"{BELGI[d]} {NOM[d]} × {soni(d)} (sizda {bor}) → {BELGI[keyingi(d)]} {NOM[keyingi(d)]}"
            + (f" (tasodifiy, {len(v)} xil versiya)" if len(v) > 1 else "") + "\n"
            f"💰 To'lov : 🪙 {narx(d)}\n"
            f"👛 Tangangiz : {tanga}\n"
            f"🔁 Bugungi qolgan : {qol}/{limit()}\n\n"
            f"⚠️ {soni(d)} ta nusxa ketadi. Davom etasizmi ?",
            parse_mode="HTML", reply_markup=t,
        )
        await q.answer()
        return
    kod, d = await craft_qil(_baza, egasi, raqam)
    if kod != "ok":
        xabar = {
            "tanga_yetmaydi": f"💸 Tanga yetmaydi : kerak 🪙 {d.get('narx', '')}",
            "limit": "⏳ Bugungi craft limiti tugadi. Ertaga qayting !",
            "versiya_yoq": "⚠️ Bu waifuning yuqori daraja versiyasi yo'q",
            "nusxa_yetmaydi": f"⚠️ Nusxa yetmaydi : kerak {d.get('kerak', '')}, bor {d.get('bor', '')}",
        }.get(kod, "❌ Xatolik, qayta urinib ko'ring. Hech narsa yo'qolmadi")
        await q.answer(xabar, show_alert=True)
        return
    m = d["m"]
    try:
        await q.message.reply_photo(
            m["file_id"],
            caption=(
                f"{RAMKA}\n⚒️ Craft muvaffaqiyatli !\n\n"
                f"🫧 {K(q.from_user.first_name)}\n"
                f"🗽 Ismi : {K(m['name'])}\n"
                f"🎗️ RANK : {_yulduz(m)}\n"
                f"👀 Manba : {K(m['anime'])}\n"
                f"🔢 Raqam : {m.get('raqam', '?')}\n\n"
                f"🔁 {d['kerak']}× {K(d['p']['name'])} → {BELGI[daraja(m)]} {NOM[daraja(m)]}\n"
                f"💰 To'lov : 🪙 {d['narx']}\n"
                f"👛 Qoldiq : {d['coins']}"
            ),
            parse_mode="HTML",
        )
    except Exception as xato:
        logging.warning("Craft rasmini yuborib bo'lmadi: %s", xato)
        await q.message.reply_text(f"⚒️ Craft : {K(m['name'])} ({NOM[daraja(m)]})", parse_mode="HTML")
    matn, t = await _royxat(egasi, 0)
    await q.edit_message_text(matn, reply_markup=t)
    await q.answer("⚒️")


def ulash(ilova, baza, rasmiy_guruh, yulduz_matni):
    global _baza, _yulduz, _guruh
    _baza = baza
    _yulduz = yulduz_matni
    _guruh = rasmiy_guruh
    ilova.add_handler(CommandHandler("craft", craft))
    ilova.add_handler(CallbackQueryHandler(craft_tugma, pattern=r"^cr:"))
