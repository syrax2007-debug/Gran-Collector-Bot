import asyncio
import html
import logging
import re
from datetime import datetime, timedelta, timezone
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    CommandHandler, CallbackQueryHandler, TypeHandler, ContextTypes,
    ApplicationHandlerStop,
)
import ismlar

# Qo'shimcha admin buyruqlari. Hammasi faqat admin uchun.
# Odamni 2 xil ko'rsatish mumkin:
#   1) uning xabariga REPLY qilib:  /tangaber 100
#   2) ID raqami bilan:             /tangaber 123456789 100

RAMKA = "✨━ ━━━━━━━━━ ━✨"
TOSHKENT = timezone(timedelta(hours=5))
COLLECTOR_KALIT = "special"

_baza = None
_admin_id = 0
_nodirlik = {}
_yulduz = None
_tasodifiy = None
_oraliq_asl = 120
_rasmiy = ""
_oraliq = None  # xotirada: joriy chiqish oralig'i
_banlar = None  # xotirada: taqiqlanganlar ID to'plami
_vazifalar = set()  # fon vazifalari yo'qolib ketmasligi uchun


def admin_mi(update):
    u = update.effective_user
    return bool(u) and u.id == _admin_id


def _variant(kalit):
    return [kalit, kalit.capitalize(), kalit.upper()]


def K(s):
    return html.escape(str(s))


def hedef(update, context):
    # (uid, qolgan_argumentlar). Reply bo'lsa - o'sha odam, bo'lmasa - 1-argument ID
    r = update.message.reply_to_message
    args = list(context.args or [])
    if r and r.from_user and not r.from_user.is_bot:
        return r.from_user.id, args
    if args and re.fullmatch(r"\d{5,15}", args[0]):
        return int(args[0]), args[1:]
    return None, args


async def _ism(uid, context, chat_id=None):
    try:
        xarita = await ismlar.ol(_baza, [uid], context.bot, chat_id)
        return K(xarita.get(uid) or uid)
    except Exception:
        return K(uid)


async def _foydalanuvchi(uid):
    return await _baza["users"].find_one({"_id": uid})


async def _waifu(raqam):
    return await _baza["characters"].find_one({"raqam": int(raqam)})


def _daraja_nomi(p):
    return _nodirlik.get(str(p.get("rarity", "")).lower(), (str(p.get("rarity")), 0))[0]


YO_YOQ = (
    "❌ Odamni ko'rsating:\n"
    "• uning xabariga <b>reply</b> qiling, yoki\n"
    "• ID raqamini yozing."
)


# ---------- /tangaber ----------
async def tangaber(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not admin_mi(update):
        return
    xabar = update.message
    uid, args = hedef(update, context)
    if uid is None or not args or not re.fullmatch(r"[+-]?\d{1,9}", args[0]):
        await xabar.reply_text(
            "🪙 Tanga berish yoki olish:\n"
            "<code>/tangaber 100</code>  (odam xabariga reply)\n"
            "<code>/tangaber 123456789 100</code>\n"
            "Olish uchun minus: <code>/tangaber 123456789 -50</code>\n\n"
            + YO_YOQ.split("\n", 1)[1],
            parse_mode="HTML",
        )
        return
    u = await _foydalanuvchi(uid)
    if not u:
        await xabar.reply_text("🔍 Bu odam bazada yo'q (botga /start bosmagan)")
        return
    son = int(args[0])
    eski = u.get("coins", 0)
    yangi = max(eski + son, 0)
    await _baza["users"].update_one({"_id": uid}, {"$set": {"coins": yangi}})
    nom = await _ism(uid, context, update.effective_chat.id)
    await xabar.reply_text(
        f"✅ {nom}\n🪙 {eski} ➜ {yangi} ({'+' if son >= 0 else ''}{son})",
        parse_mode="HTML",
    )


# ---------- /waifuber ----------
async def waifuber(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not admin_mi(update):
        return
    xabar = update.message
    uid, args = hedef(update, context)
    if uid is None or not args or not args[0].isdigit():
        await xabar.reply_text(
            "🎁 Waifu berish:\n"
            "<code>/waifuber 4821</code>  (odam xabariga reply)\n"
            "<code>/waifuber 123456789 4821</code>\n"
            "Bir necha nusxa: <code>/waifuber 4821 3</code>\n\n"
            + YO_YOQ.split("\n", 1)[1],
            parse_mode="HTML",
        )
        return
    if not await _foydalanuvchi(uid):
        await xabar.reply_text("🔍 Bu odam bazada yo'q (botga /start bosmagan)")
        return
    p = await _waifu(args[0])
    if not p:
        await xabar.reply_text("🔍 Bunday raqamli waifu topilmadi")
        return
    n = 1
    if len(args) > 1 and args[1].isdigit():
        n = max(1, min(int(args[1]), 20))
    for _ in range(n):
        await _baza["collection"].insert_one(
            {"user_id": uid, "char_id": p["_id"]}
        )
    nom = await _ism(uid, context, update.effective_chat.id)
    await xabar.reply_text(
        f"✅ {nom} ga berildi\n"
        f"🗽 {K(p['name'])} ({K(_daraja_nomi(p))}) × {n}",
        parse_mode="HTML",
    )


# ---------- /waifuol ----------
async def waifuol(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not admin_mi(update):
        return
    xabar = update.message
    uid, args = hedef(update, context)
    if uid is None or not args or not args[0].isdigit():
        await xabar.reply_text(
            "🗑 Waifuni olib qo'yish:\n"
            "<code>/waifuol 4821</code>  (odam xabariga reply)\n"
            "<code>/waifuol 123456789 4821</code>\n"
            "Bir necha nusxa: <code>/waifuol 4821 2</code>\n\n"
            + YO_YOQ.split("\n", 1)[1],
            parse_mode="HTML",
        )
        return
    p = await _waifu(args[0])
    if not p:
        await xabar.reply_text("🔍 Bunday raqamli waifu topilmadi")
        return
    n = 1
    if len(args) > 1 and args[1].isdigit():
        n = max(1, min(int(args[1]), 20))
    olindi = 0
    for _ in range(n):
        r = await _baza["collection"].delete_one(
            {"user_id": uid, "char_id": p["_id"]}
        )
        if getattr(r, "deleted_count", 0) == 0:
            break
        olindi += 1
    nom = await _ism(uid, context, update.effective_chat.id)
    if olindi == 0:
        await xabar.reply_text(f"🔍 {nom} da bu waifu yo'q", parse_mode="HTML")
        return
    await xabar.reply_text(
        f"✅ {nom} dan olindi\n🗽 {K(p['name'])} × {olindi}",
        parse_mode="HTML",
    )


# ---------- /foydalanuvchi ----------
async def foydalanuvchi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not admin_mi(update):
        return
    xabar = update.message
    uid, _ = hedef(update, context)
    if uid is None:
        await xabar.reply_text(
            "👤 Odam haqida ma'lumot:\n"
            "<code>/foydalanuvchi</code>  (odam xabariga reply)\n"
            "<code>/foydalanuvchi 123456789</code>",
            parse_mode="HTML",
        )
        return
    u = await _foydalanuvchi(uid)
    if not u:
        await xabar.reply_text("🔍 Bu odam bazada yo'q")
        return
    sanash = {}
    async for d in _baza["collection"].find({"user_id": uid}):
        sanash[d["char_id"]] = sanash.get(d["char_id"], 0) + 1
    jami = sum(sanash.values())
    darajalar = {}
    sevimli = None
    if sanash:
        async for p in _baza["characters"].find({"_id": {"$in": list(sanash)}}):
            nom = _daraja_nomi(p)
            darajalar[nom] = darajalar.get(nom, 0) + sanash[p["_id"]]
            if u.get("sevimli") == p["_id"]:
                sevimli = p["name"]
    qator = "\n".join(
        f"   {K(k)} : {v}" for k, v in sorted(darajalar.items())
    ) or "   —"
    taklif = await _baza["users"].count_documents({"referrer": uid})
    tolangan = await _baza["users"].count_documents(
        {"referrer": uid, "ref_tolangan": True}
    )
    taklif_qilgan = u.get("referrer")
    taqiq = await _banlar_ol()
    taqiq_matn = "ha" if uid in taqiq else "yo'q"
    nom = await _ism(uid, context, update.effective_chat.id)
    matn = (
        f"👤 {nom}\n"
        f"🆔 <code>{uid}</code>\n"
        f"🪙 Tanga : {u.get('coins', 0)}\n"
        f"🎴 Waifu : {jami} ta, {len(sanash)} xil\n"
        f"{qator}\n"
        f"❤ Sevimli : {K(sevimli) if sevimli else '—'}\n"
        f"👥 Referal : {taklif} ta (tasdiqlangan {tolangan})\n"
        f"↪️ Taklif qilgan : {taklif_qilgan if taklif_qilgan else '—'}\n"
        f"🚫 Taqiq : {taqiq_matn}"
    )
    await xabar.reply_text(matn, parse_mode="HTML")


# ---------- /ban, /unban ----------
async def _banlar_ol():
    global _banlar
    if _banlar is None:
        _banlar = set()
        async for d in _baza["banlar"].find({}):
            _banlar.add(d["_id"])
    return _banlar


async def ban_tekshir(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Taqiqlangan odamning hech bir buyrug'i va tugmasi ishlamaydi
    f = update.effective_user
    if not f or f.id == _admin_id:
        return
    if f.id in await _banlar_ol():
        raise ApplicationHandlerStop


async def ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not admin_mi(update):
        return
    xabar = update.message
    uid, args = hedef(update, context)
    if uid is None:
        await xabar.reply_text(
            "🚫 Taqiqlash:\n"
            "<code>/ban</code>  (odam xabariga reply)\n"
            "<code>/ban 123456789 sabab</code>",
            parse_mode="HTML",
        )
        return
    if uid == _admin_id:
        await xabar.reply_text("❌ O'zingizni taqiqlab bo'lmaydi")
        return
    sabab = " ".join(args).strip()
    await _baza["banlar"].update_one(
        {"_id": uid},
        {"$set": {"sabab": sabab, "vaqt": datetime.now(TOSHKENT).isoformat()}},
        upsert=True,
    )
    (await _banlar_ol()).add(uid)
    nom = await _ism(uid, context, update.effective_chat.id)
    await xabar.reply_text(
        f"🚫 {nom} taqiqlandi" + (f"\nSabab: {K(sabab)}" if sabab else ""),
        parse_mode="HTML",
    )


async def unban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not admin_mi(update):
        return
    xabar = update.message
    uid, _ = hedef(update, context)
    if uid is None:
        await xabar.reply_text(
            "✅ Taqiqni olib tashlash:\n"
            "<code>/unban</code>  (odam xabariga reply)\n"
            "<code>/unban 123456789</code>",
            parse_mode="HTML",
        )
        return
    await _baza["banlar"].delete_one({"_id": uid})
    (await _banlar_ol()).discard(uid)
    nom = await _ism(uid, context, update.effective_chat.id)
    await xabar.reply_text(f"✅ {nom} ga ruxsat berildi", parse_mode="HTML")


# ---------- /xabar (hammaga) ----------
async def xabar_buyruq(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not admin_mi(update):
        return
    xabar = update.message
    if update.effective_chat.type != "private":
        await xabar.reply_text("❌ Bu buyruq faqat botning shaxsiy chatida ishlaydi")
        return
    r = xabar.reply_to_message
    matn = re.sub(r"^/\w+(@\w+)?\s*", "", xabar.text or "", count=1).strip()
    if r:
        yuk = ("nusxa", r.chat.id, r.message_id)
        korinish = "↩️ Siz reply qilgan xabar (rasm bilan) yuboriladi"
    elif matn:
        yuk = ("matn", matn)
        korinish = matn
    else:
        await xabar.reply_text(
            "📢 Hammaga xabar:\n"
            "<code>/xabar Salom, bugun yangi event!</code>\n"
            "Rasmli xabar: avval shu xabarni botga yuboring, so'ng unga "
            "reply qilib <code>/xabar</code> yozing.",
            parse_mode="HTML",
        )
        return
    soni = await _baza["users"].count_documents({"_id": {"$gt": 0}})
    kalit = str(xabar.message_id)
    context.bot_data.setdefault("xabarlar", {})[kalit] = yuk
    await xabar.reply_text(
        f"📢 {soni} ta foydalanuvchiga yuboriladi:\n\n{korinish}",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Yuborish", callback_data=f"xb:ha:{kalit}"),
            InlineKeyboardButton("❌ Bekor", callback_data=f"xb:yoq:{kalit}"),
        ]]),
    )


async def _tarqat(bot, yuk, admin_chat):
    yubordi = 0
    yetmadi = 0
    async for u in _baza["users"].find({"_id": {"$gt": 0}}):
        uid = u["_id"]
        for urinish in range(2):
            try:
                if yuk[0] == "nusxa":
                    await bot.copy_message(uid, yuk[1], yuk[2])
                else:
                    await bot.send_message(uid, yuk[1])
                yubordi += 1
                break
            except Exception as xato:
                kut = getattr(xato, "retry_after", None)
                if kut and urinish == 0:
                    await asyncio.sleep(float(kut) + 1)
                    continue
                yetmadi += 1
                break
        await asyncio.sleep(0.06)
    try:
        await bot.send_message(
            admin_chat,
            f"✅ Xabar tarqatildi\n📨 Yetib bordi : {yubordi}\n"
            f"🚫 Yetmadi : {yetmadi} (botni bloklaganlar)",
        )
    except Exception as xato:
        logging.warning("Xabar hisobotini yuborib bo'lmadi: %s", xato)


async def xabar_tugma(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not q or q.from_user.id != _admin_id:
        if q:
            await q.answer()
        return
    await q.answer()
    _, amal, kalit = q.data.split(":", 2)
    yuk = context.bot_data.get("xabarlar", {}).pop(kalit, None)
    if not yuk:
        await q.edit_message_text("⌛ Bu so'rov eskirgan. Qayta /xabar yuboring.")
        return
    if amal == "yoq":
        await q.edit_message_text("🛑 Bekor qilindi")
        return
    await q.edit_message_text("⏳ Yuborilmoqda... tugagach xabar beraman")
    t = asyncio.create_task(_tarqat(context.bot, yuk, q.message.chat_id))
    _vazifalar.add(t)
    t.add_done_callback(_vazifalar.discard)


# ---------- /spawn ----------
async def spawn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not admin_mi(update):
        return
    xabar = update.message
    chat = update.effective_chat
    if chat.type not in ("group", "supergroup"):
        await xabar.reply_text("❌ Bu buyruq faqat guruhda ishlaydi")
        return
    args = context.args or []
    if args and args[0].isdigit():
        p = await _waifu(args[0])
        if not p:
            await xabar.reply_text("🔍 Bunday raqamli waifu topilmadi")
            return
    else:
        p = await _tasodifiy()
        if not p:
            await xabar.reply_text("❌ Waifu topilmadi")
            return
    await _baza["spawns"].update_one(
        {"_id": chat.id}, {"$set": {"char_id": p["_id"]}}, upsert=True
    )
    await context.bot.send_photo(
        chat.id, p["file_id"],
        caption=(
            f"{RAMKA}\n"
            " 💫YANGI PERSONAJ CHIQDI!\n"
            f"🎗️ RANK : {_yulduz(p)}\n\n"
            "🐾   <code>/topish ism</code> 🇺🇿"
        ),
        parse_mode="HTML",
    )
    try:
        await xabar.delete()
    except Exception:
        pass


# ---------- /oraliq ----------
async def oraliq_ol(boshlangich=None):
    # main.py har bir guruh xabarida shu yerdan oraliqni oladi
    global _oraliq
    if _oraliq is None:
        try:
            d = await _baza["sozlamalar"].find_one({"_id": "oraliq"})
        except Exception as xato:
            logging.warning("Oraliqni o'qib bo'lmadi: %s", xato)
            return boshlangich or _oraliq_asl
        _oraliq = int(d["son"]) if d and d.get("son") else (boshlangich or _oraliq_asl)
    return _oraliq


async def oraliq(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global _oraliq
    if not admin_mi(update):
        return
    xabar = update.message
    args = context.args or []
    hozir = await oraliq_ol()
    if not args:
        await xabar.reply_text(
            f"⏱ Waifu har {hozir} ta xabardan keyin chiqadi\n\n"
            "O'zgartirish: <code>/oraliq 75</code>\n"
            f"Asl holatga qaytarish: <code>/oraliq asl</code> ({_oraliq_asl})",
            parse_mode="HTML",
        )
        return
    if args[0].lower() in ("asl", "reset"):
        await _baza["sozlamalar"].delete_one({"_id": "oraliq"})
        _oraliq = _oraliq_asl
        await xabar.reply_text(f"✅ Asl holatga qaytdi : {_oraliq_asl}")
        return
    if not args[0].isdigit() or not 10 <= int(args[0]) <= 5000:
        await xabar.reply_text("❌ 10 dan 5000 gacha son yozing : /oraliq 75")
        return
    n = int(args[0])
    await _baza["sozlamalar"].update_one(
        {"_id": "oraliq"}, {"$set": {"son": n}}, upsert=True
    )
    _oraliq = n
    await xabar.reply_text(f"✅ Endi har {n} ta xabardan keyin waifu chiqadi")


# ---------- /eventochir ----------
async def eventochir(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not admin_mi(update):
        return
    xabar = update.message
    matn = re.sub(r"^/\w+(@\w+)?", "", xabar.text or "", count=1).strip()
    qismlar = [q.strip() for q in matn.split("|")]
    if len(qismlar) != 2 or not qismlar[0] or not qismlar[1]:
        await xabar.reply_text(
            "⛩️ Eventdagi hamma Collector waifuni boshqa eventga o'tkazish:\n"
            "<code>/eventochir Qish 2026 | Yoz 2026</code>\n"
            "Eventsizlar uchun eski nom: <code>Boshqa</code>",
            parse_mode="HTML",
        )
        return
    eski = " ".join(qismlar[0].split())
    yangi = " ".join(qismlar[1].split())
    shart = {"rarity": {"$in": _variant(COLLECTOR_KALIT)}}
    if eski.casefold() == "boshqa":
        shart["$or"] = [{"event": {"$exists": False}}, {"event": ""}]
    else:
        shart["event"] = {"$regex": f"^{re.escape(eski)}$", "$options": "i"}
    soni = await _baza["characters"].count_documents(shart)
    if not soni:
        await xabar.reply_text("🔍 Bunday eventda Collector waifu yo'q. /event bilan ro'yxatni ko'ring")
        return
    await _baza["characters"].update_many(shart, {"$set": {"event": yangi}})
    d = await _baza["sozlamalar"].find_one({"_id": "event"})
    if d and (d.get("nom") or "").casefold() == eski.casefold():
        await _baza["sozlamalar"].update_one(
            {"_id": "event"}, {"$set": {"nom": yangi}}
        )
    await xabar.reply_text(
        f"✅ {soni} ta waifu o'tkazildi\n⛩️ {K(eski)} ➜ {K(yangi)}",
        parse_mode="HTML",
    )


# ---------- /sozlamalar ----------
async def sozlamalar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not admin_mi(update):
        return
    b = _baza
    hozir = await oraliq_ol()
    mx = await b["sozlamalar"].find_one({"_id": "max"}) or {}
    ev = await b["sozlamalar"].find_one({"_id": "event"}) or {}
    if mx.get("faol"):
        mx_matn = f"✅ {mx.get('sanalgan', 0)} / {mx.get('maqsad', 0)}"
    else:
        mx_matn = "⏸ o'chiq"
    odamlar = await b["users"].count_documents({})
    waifular = await b["characters"].count_documents({})
    nusxalar = await b["collection"].count_documents({})
    guruhlar = await b["allowed_chats"].count_documents({})
    taqiqlar = len(await _banlar_ol())
    await update.message.reply_text(
        "⚙️ Sozlamalar\n\n"
        f"⏱ Waifu chiqish oralig'i : {hozir} xabar\n"
        f"👑 MAX : {mx_matn}\n"
        f"⛩️ Faol event : {K(ev.get('nom')) if ev.get('nom') else '—'}\n"
        f"💬 Rasmiy guruh : @{K(_rasmiy)}\n"
        f"✅ Tasdiqlangan guruhlar : {guruhlar}\n\n"
        f"👥 Odamlar : {odamlar}\n"
        f"🗽 Waifular : {waifular}\n"
        f"🎴 Kolleksiyalarda : {nusxalar} nusxa\n"
        f"🚫 Taqiqlanganlar : {taqiqlar}",
        parse_mode="HTML",
    )


# ---------- main.py ga ulash ----------
def ulash(ilova, baza, admin_id, nodirlik, yulduz_matni, tasodifiy, oraliq_asl,
          rasmiy_guruh):
    global _baza, _admin_id, _nodirlik, _yulduz, _tasodifiy, _oraliq_asl, _rasmiy
    _baza = baza
    _admin_id = admin_id
    _nodirlik = nodirlik
    _yulduz = yulduz_matni
    _tasodifiy = tasodifiy
    _oraliq_asl = oraliq_asl
    _rasmiy = rasmiy_guruh
    # group=-5: taqiqlangan odam boshqa hamma ishlovchilardan oldin to'xtatiladi
    ilova.add_handler(TypeHandler(Update, ban_tekshir), group=-5)
    for nom, f in (
        ("tangaber", tangaber), ("waifuber", waifuber), ("waifuol", waifuol),
        ("foydalanuvchi", foydalanuvchi), ("ban", ban), ("unban", unban),
        ("xabar", xabar_buyruq), ("spawn", spawn), ("oraliq", oraliq),
        ("eventochir", eventochir), ("sozlamalar", sozlamalar),
    ):
        ilova.add_handler(CommandHandler(nom, f))
    ilova.add_handler(CallbackQueryHandler(xabar_tugma, pattern=r"^xb:"))
