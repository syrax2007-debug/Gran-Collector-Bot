import html
import re
from datetime import datetime, timedelta, timezone
from telegram import Update
from telegram.ext import CommandHandler, ContextTypes
import ismlar

# ---------- Sozlamalar ----------
TOP_SONI = 10  # /top da nechta odam ko'rsatiladi
EGA_SONI = 5  # /ega da nechta ega ko'rsatiladi
COIN_KUNLIK_LIMIT = 1000  # bir kunda ulashish mumkin bo'lgan jami tanga
# Har bir o'rin uchun alohida nishon (o'zgartirsangiz bo'ladi)
NISHONLAR = ["🥇", "🥈", "🥉", "💎", "🔥", "⚡", "🌟", "🎖️", "🏅", "✨"]
CIZIQ = "━━━━━━━━━━━━━━"
TOSHKENT = timezone(timedelta(hours=5))

DARAJA = {
    "common": "Elita 💠",
    "rare": "Super 🌟",
    "epic": "Mega 💎",
    "legendary": "Ultra 🔥",
    "special": "Collector ⛩️",
    "max": "Max 👑",
}

_baza = None


def bugun():
    return datetime.now(TOSHKENT).strftime("%Y-%m-%d")


def toza(s):
    return html.escape(str(s))


def bog(uid, ism):
    # Odamga havola (xabarda ismi ko'rinadi)
    return f'<a href="tg://user?id={uid}">{toza(ism)}</a>'


def nishon(i):
    return NISHONLAR[i] if i < len(NISHONLAR) else "🔹"


# ---------- /top : global reyting ----------
async def top(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kursor = await _baza["collection"].aggregate([
        {"$group": {
            "_id": {"u": "$user_id", "c": "$char_id"},
            "k": {"$sum": 1},
        }},
        {"$group": {
            "_id": "$_id.u",
            "jami": {"$sum": "$k"},
            "turli": {"$sum": 1},
        }},
        {"$sort": {"jami": -1, "turli": -1, "_id": 1}},
    ])
    hammasi = [d async for d in kursor]
    if not hammasi:
        await update.message.reply_text("📭 Hali hech kimda waifu yo'q")
        return

    birinchilar = hammasi[:TOP_SONI]
    idlar = [d["_id"] for d in birinchilar]
    ismlar_xarita = await ismlar.ol(
        _baza, idlar, context.bot, update.effective_chat.id
    )

    qatorlar = []
    for i, d in enumerate(birinchilar):
        ism = ismlar_xarita[d["_id"]]
        qatorlar.append(
            f"{nishon(i)} {toza(ism)}\n"
            f"      🧧 {d['jami']} ta  •  🎴 {d['turli']} xil"
        )

    matn = (
        f"{CIZIQ}\n"
        f"🏆 Global Top {TOP_SONI}\n"
        f"{CIZIQ}\n\n"
        + "\n\n".join(qatorlar)
    )

    # Siz top ro'yxatda bo'lmasangiz, o'z o'rningizni ko'rsatamiz
    me = update.effective_user.id
    for i, d in enumerate(hammasi):
        if d["_id"] == me and i >= TOP_SONI:
            matn += (
                f"\n\n{CIZIQ}\n"
                f"📍 Sizning o'rningiz : {i + 1}\n"
                f"🧧 {d['jami']} ta  •  🎴 {d['turli']} xil"
            )
            break
    await update.message.reply_text(matn, parse_mode="HTML")


# ---------- /ega : waifu kimlarda ko'p ----------
async def ega(update: Update, context: ContextTypes.DEFAULT_TYPE):
    xabar = update.message
    if not context.args:
        await xabar.reply_text(
            "👑 Waifu egalari\n\n"
            "Qaysi waifu kimlarda ko'p ekanini ko'rish:\n"
            "<code>/ega ism</code>  yoki  <code>/ega 4821</code>",
            parse_mode="HTML",
        )
        return

    s = " ".join(context.args).strip()
    personajlar = _baza["characters"]
    kolleksiya = _baza["collection"]

    p = None
    if s.isdigit():
        p = await personajlar.find_one({"raqam": int(s)})
    if not p:
        p = await personajlar.find_one(
            {"name": {"$regex": f"^{re.escape(s)}$", "$options": "i"}}
        )
    if not p:
        topilgan = [
            d async for d in personajlar.find(
                {"name": {"$regex": re.escape(s), "$options": "i"}}
            ).limit(6)
        ]
        if not topilgan:
            await xabar.reply_text("🔍 Bunday waifu topilmadi")
            return
        if len(topilgan) > 1:
            royxat = "\n".join(
                f"• {toza(d['name'])} — <code>{d.get('raqam', '?')}</code>"
                for d in topilgan
            )
            await xabar.reply_text(
                "🔎 Bir nechta waifu topildi. Raqami bilan yozing:\n\n"
                f"{royxat}\n\n<code>/ega raqam</code>",
                parse_mode="HTML",
            )
            return
        p = topilgan[0]

    kursor = await kolleksiya.aggregate([
        {"$match": {"char_id": p["_id"]}},
        {"$group": {"_id": "$user_id", "n": {"$sum": 1}}},
        {"$sort": {"n": -1, "_id": 1}},
        {"$limit": EGA_SONI},
    ])
    egalar = [d async for d in kursor]
    jami_ega = len(await kolleksiya.distinct("user_id", {"char_id": p["_id"]}))

    ismlar_xarita = await ismlar.ol(
        _baza, [d["_id"] for d in egalar], context.bot,
        update.effective_chat.id,
    )

    if egalar:
        qatorlar = "\n".join(
            f"{nishon(i)} {toza(ismlar_xarita[d['_id']])} — ×{d['n']}"
            for i, d in enumerate(egalar)
        )
    else:
        qatorlar = "Hali hech kimda yo'q"

    daraja = DARAJA.get(str(p["rarity"]).lower(), str(p["rarity"]))
    matn = (
        f"🗽 Ismi : {toza(p['name'])}\n"
        f"🎗️ Daraja : {daraja}\n"
        f"👀 Manba : {toza(p['anime'])}\n"
        f"🔢 Raqam : {p.get('raqam', '?')}\n\n"
        f"👑 Egalari ({jami_ega} kishi):\n{qatorlar}"
    )
    await xabar.reply_photo(
        photo=p["file_id"], caption=matn, parse_mode="HTML"
    )


# ---------- /coin : tanga ulashish ----------
async def coin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    xabar = update.message
    yub = update.effective_user
    yordam = (
        "💸 Tanga ulashish\n\n"
        "Odamning xabariga javob berib yozing:\n"
        "<code>/coin 100</code>\n\n"
        "yoki uning ID raqami bilan:\n"
        "<code>/coin 123456789 100</code>\n\n"
        f"Kunlik limit : {COIN_KUNLIK_LIMIT} 🪙"
    )
    args = context.args
    javob = xabar.reply_to_message

    if javob and javob.from_user and args:
        o = javob.from_user
        if o.is_bot:
            await xabar.reply_text("❌ Botga tanga berib bo'lmaydi !")
            return
        oluvchi_id, oluvchi_ism, qiymat = o.id, o.first_name, args[0]
    elif len(args) >= 2 and args[0].isdigit():
        oluvchi_id, oluvchi_ism, qiymat = int(args[0]), None, args[1]
    else:
        await xabar.reply_text(yordam, parse_mode="HTML")
        return

    if not qiymat.isdigit() or int(qiymat) <= 0:
        await xabar.reply_text("❌ Miqdor musbat butun son bo'lsin !")
        return
    n = int(qiymat)
    if oluvchi_id == yub.id:
        await xabar.reply_text("❌ O'zingizga tanga berib bo'lmaydi !")
        return

    users = _baza["users"]
    oluvchi = await users.find_one({"_id": oluvchi_id})
    if oluvchi is None:
        await xabar.reply_text("🔍 Bu odam botdan hali foydalanmagan")
        return
    if oluvchi_ism is None:
        oluvchi_ism = (
            await ismlar.ol(
                _baza, [oluvchi_id], context.bot, update.effective_chat.id
            )
        )[oluvchi_id]

    b = bugun()
    u = await users.find_one({"_id": yub.id}) or {}
    ishlatilgan = u.get("coin_yub", 0) if u.get("coin_sana") == b else 0
    if ishlatilgan + n > COIN_KUNLIK_LIMIT:
        qoldi = max(COIN_KUNLIK_LIMIT - ishlatilgan, 0)
        await xabar.reply_text(
            f"⏳ Kunlik limit : {COIN_KUNLIK_LIMIT} 🪙\n"
            f"Bugun yana {qoldi} 🪙 ulasha olasiz"
        )
        return

    # Avval yuboruvchidan yechamiz (yetarli bo'lsa), keyin oluvchiga qo'shamiz
    r = await users.update_one(
        {"_id": yub.id, "coins": {"$gte": n}},
        {
            "$inc": {"coins": -n},
            "$set": {"coin_sana": b, "coin_yub": ishlatilgan + n},
        },
    )
    if r.modified_count == 0:
        await xabar.reply_text("❌ Tangangiz yetmaydi !")
        return
    await users.update_one({"_id": oluvchi_id}, {"$inc": {"coins": n}})

    u2 = await users.find_one({"_id": yub.id}) or {}
    await xabar.reply_text(
        f"{CIZIQ}\n"
        "💸 Tanga ulashildi !\n\n"
        f"🫧 {bog(yub.id, yub.first_name)} ➜ {bog(oluvchi_id, oluvchi_ism)}\n"
        f"💰 Miqdor : {n} 🪙\n"
        f"👛 Qoldiq : {u2.get('coins', 0)} 🪙",
        parse_mode="HTML",
    )


def ulash(ilova, baza):
    global _baza
    _baza = baza
    ilova.add_handler(CommandHandler("top", top))
    ilova.add_handler(CommandHandler("ega", ega))
    ilova.add_handler(CommandHandler("coin", coin))
