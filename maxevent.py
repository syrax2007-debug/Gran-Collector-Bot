import html
import logging
import sozlama as S
import random
import re
from pymongo import ReturnDocument
from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

# ---------- Sozlamalar ----------
# MAX nimani sanaydi: "soz" - xabarlardagi so'zlar, "xabar" - har bir xabar 1 ta
SANASH = "soz"
# Event faol paytda chiqadigan personajlarning necha foizi Collector bo'ladi
EVENT_FOIZ = 20  # standart; haqiqiy qiymat /panel dan (sozlama.py)
MAX_KALIT = "max"
COLLECTOR_KALIT = "special"

_baza = None
_admin_id = 0
_rasmiy = ""  # asosiy guruh username'i (kichik harflarda, @ siz)
_yulduz = None  # yulduz_matni funksiyasi (main.py dan)
_faol = None  # xotirada: MAX sanash yoqilganmi (None - hali o'qilmagan)


def _variant(kalit):
    # Bazada "max", "Max" yoki "MAX" bo'lishi mumkin
    return [kalit, kalit.capitalize(), kalit.upper()]


def _birlik():
    return "so'z" if SANASH == "soz" else "xabar"


def _admin_shaxsiy(update):
    u = update.effective_user
    return bool(u) and u.id == _admin_id and update.effective_chat.type == "private"


# ---------- MAX: asosiy guruh xabarlarini sanash ----------
async def sana(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # main.py har bir guruh xabarida chaqiradi
    global _faol
    if _faol is False:  # tez yo'l: o'chiq bo'lsa hech narsa qilmaymiz
        return
    chat = update.effective_chat
    if (chat.username or "").lower() != _rasmiy:
        return
    sozlama = _baza["sozlamalar"]
    if _faol is None:
        d = await sozlama.find_one({"_id": "max"})
        _faol = bool(d and d.get("faol"))
        if not _faol:
            return
    xabar = update.effective_message
    matn = ((xabar.text or xabar.caption or "") if xabar else "")
    n = len(matn.split()) if SANASH == "soz" else 1
    if n <= 0:
        return
    d = await sozlama.find_one_and_update(
        {"_id": "max", "faol": True},
        {"$inc": {"sanalgan": n}},
        return_document=ReturnDocument.AFTER,
    )
    if not d:
        _faol = False
        return
    if d.get("sanalgan", 0) < d.get("maqsad", 0):
        return
    # Maqsadga yetdi: faqat bitta jarayon MAX ni chiqaradi
    r = await sozlama.update_one(
        {"_id": "max", "faol": True, "sanalgan": {"$gte": d["maqsad"]}},
        {"$set": {"faol": False}},
    )
    if r.modified_count == 0:
        return
    _faol = False
    await _max_chiqar(context, chat.id)


async def _max_chiqar(context, chat_id):
    shart = {"rarity": {"$in": _variant(MAX_KALIT)}}
    soni = await _baza["characters"].count_documents(shart)
    if not soni:
        try:
            await context.bot.send_message(
                _admin_id,
                "⚠️ MAX chiqish vaqti keldi, lekin MAX waifu topilmadi.\n"
                "Yuklang va /max son yuboring.",
            )
        except Exception:
            pass
        return
    p = await _baza["characters"].find_one(
        shart, skip=random.randrange(soni)
    )
    await _baza["spawns"].update_one(
        {"_id": chat_id}, {"$set": {"char_id": p["_id"]}}, upsert=True
    )
    await context.bot.send_photo(
        chat_id, p["file_id"],
        caption=(
            "✨━ ━━━━━━━━━ ━✨\n"
            " 👑 MAX PERSONAJ CHIQDI!\n"
            f"🎗️ RANK : {_yulduz(p)}\n\n"
            "🐾   <code>/topish ism</code> 🇺🇿"
        ),
        parse_mode="HTML",
    )


async def max_kutilyapti(chat_id):
    # Guruhda MAX personaj hali topilmagan bo'lsa True
    s = await _baza["spawns"].find_one({"_id": chat_id})
    if not s:
        return False
    p = await _baza["characters"].find_one({"_id": s["char_id"]}, {"rarity": 1})
    return bool(p) and str(p.get("rarity", "")).lower() == MAX_KALIT


async def max_buyruq(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global _faol
    if not _admin_shaxsiy(update):
        return
    xabar = update.message
    sozlama = _baza["sozlamalar"]
    soni = await _baza["characters"].count_documents(
        {"rarity": {"$in": _variant(MAX_KALIT)}}
    )
    d = await sozlama.find_one({"_id": "max"}) or {}

    if not context.args:
        if d.get("faol"):
            holat = (
                f"✅ Yoqilgan : {d.get('sanalgan', 0)} / {d.get('maqsad', 0)} "
                f"{_birlik()}"
            )
        else:
            holat = "⏸ O'chiq (MAX chiqmaydi)"
        await xabar.reply_text(
            "👑 MAX\n\n"
            f"{holat}\n"
            f"🎴 MAX waifular : {soni} ta\n\n"
            f"Asosiy guruhda nechta {_birlik()}dan keyin chiqsin:\n"
            "<code>/max 500</code>\n"
            "To'xtatish : <code>/max 0</code>",
            parse_mode="HTML",
        )
        return

    arg = context.args[0].lower()
    if arg in ("0", "stop", "bekor"):
        await sozlama.update_one(
            {"_id": "max"}, {"$set": {"faol": False}}, upsert=True
        )
        _faol = False
        await xabar.reply_text("🛑 MAX sanash to'xtatildi")
        return
    if not arg.isdigit() or int(arg) < 1:
        await xabar.reply_text("❌ Son yozing : /max 500")
        return
    if soni == 0:
        await xabar.reply_text(
            "⚠️ Avval MAX waifu yuklang:\n"
            "<code>/yuklash Ism | Manba | Max</code>",
            parse_mode="HTML",
        )
        return
    n = int(arg)
    await sozlama.update_one(
        {"_id": "max"},
        {"$set": {"faol": True, "maqsad": n, "sanalgan": 0}},
        upsert=True,
    )
    _faol = True
    await xabar.reply_text(
        "✅ MAX yoqildi !\n\n"
        f"👑 Asosiy guruhda {n} {_birlik()}dan keyin MAX chiqadi.\n"
        "Chiqqandan keyin o'zi o'chadi, qayta /max yuboring."
    )


# ---------- EVENT (Collector waifular) ----------
async def _eventlar():
    # {kalit: [ko'rinadigan nom, soni]}
    sanash = {}
    async for d in _baza["characters"].find(
        {"rarity": {"$in": _variant(COLLECTOR_KALIT)}}
    ):
        nom = " ".join(str(d.get("event") or "").split()) or "Boshqa"
        k = nom.casefold()
        if k not in sanash:
            sanash[k] = [nom, 0]
        sanash[k][1] += 1
    return sanash


async def event_buyruq(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _admin_shaxsiy(update):
        return
    xabar = update.message
    eventlar = await _eventlar()
    d = await _baza["sozlamalar"].find_one({"_id": "event"}) or {}
    faol = (d.get("nom") or "").casefold()

    if not context.args:
        if not eventlar:
            await xabar.reply_text(
                "⛩️ Eventlar yo'q.\n\n"
                "Collector yuklash:\n"
                "<code>/yuklash Ism | Manba | Collector | Event nomi</code>",
                parse_mode="HTML",
            )
            return
        qatorlar = "\n".join(
            f"{'✅' if k == faol else '▫️'} {html.escape(nom)} — {n} ta"
            for k, (nom, n) in eventlar.items()
        )
        await xabar.reply_text(
            f"⛩️ Eventlar\n\n{qatorlar}\n\n"
            "Yoqish : <code>/event Event nomi</code>\n"
            "To'xtatish : /eventtugat",
            parse_mode="HTML",
        )
        return

    s = " ".join(context.args).strip()
    tanlangan = eventlar.get(s.casefold())
    if not tanlangan:
        await xabar.reply_text(
            "🔍 Bunday event yo'q. Ro'yxat uchun /event yozing"
        )
        return
    await _baza["sozlamalar"].update_one(
        {"_id": "event"}, {"$set": {"nom": tanlangan[0]}}, upsert=True
    )
    await xabar.reply_text(
        f"✅ Event yoqildi : {tanlangan[0]}\n"
        f"⛩️ Collector waifular : {tanlangan[1]} ta\n"
        f"🎲 Chiqish ulushi : {S.ol('event_foiz')}%"
    )


async def event_tugat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _admin_shaxsiy(update):
        return
    await _baza["sozlamalar"].update_one(
        {"_id": "event"}, {"$set": {"nom": None}}, upsert=True
    )
    await update.message.reply_text("🛑 Event to'xtatildi")


async def event_qosh(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # /eventqosh 4821 | Qish 2026 : mavjud Collector waifuni eventga qo'shadi
    if not _admin_shaxsiy(update):
        return
    xabar = update.message
    matn = re.sub(r"^/\w+(@\w+)?", "", xabar.text or "").strip()
    qismlar = [q.strip() for q in matn.split("|")]
    if len(qismlar) != 2 or not qismlar[0].isdigit() or not qismlar[1]:
        await xabar.reply_text(
            "⛩️ Waifuni eventga qo'shish:\n"
            "<code>/eventqosh 4821 | Qish 2026</code>",
            parse_mode="HTML",
        )
        return
    p = await _baza["characters"].find_one({"raqam": int(qismlar[0])})
    if not p:
        await xabar.reply_text("🔍 Bunday waifu topilmadi")
        return
    if str(p.get("rarity", "")).lower() != COLLECTOR_KALIT:
        await xabar.reply_text("❌ Bu waifu Collector emas")
        return
    nom = " ".join(qismlar[1].split())
    await _baza["characters"].update_one(
        {"_id": p["_id"]}, {"$set": {"event": nom}}
    )
    await xabar.reply_text(
        f"✅ {p['name']} ➜ event : {nom}"
    )


async def event_personaji():
    # Event faol bo'lsa va tasodif tushsa, shu eventdan Collector beradi
    if random.random() * 100 >= S.ol('event_foiz'):
        return None
    d = await _baza["sozlamalar"].find_one({"_id": "event"})
    nom = (d or {}).get("nom")
    if not nom:
        return None
    shart = {"rarity": {"$in": _variant(COLLECTOR_KALIT)}}
    if nom.casefold() == "boshqa":
        shart["$or"] = [{"event": {"$exists": False}}, {"event": ""}]
    else:
        shart["event"] = {
            "$regex": f"^{re.escape(nom)}$", "$options": "i",
        }
    soni = await _baza["characters"].count_documents(shart)
    if not soni:
        return None
    return await _baza["characters"].find_one(
        shart, skip=random.randrange(soni)
    )


# ---------- main.py ga ulash ----------
def ulash(ilova, baza, admin_id, rasmiy_guruh, yulduz_matni):
    global _baza, _admin_id, _rasmiy, _yulduz
    _baza = baza
    _admin_id = admin_id
    _rasmiy = rasmiy_guruh.lower()
    _yulduz = yulduz_matni
    ilova.add_handler(CommandHandler("max", max_buyruq))
    ilova.add_handler(CommandHandler("event", event_buyruq))
    ilova.add_handler(CommandHandler("eventtugat", event_tugat))
    ilova.add_handler(CommandHandler("eventqosh", event_qosh))
