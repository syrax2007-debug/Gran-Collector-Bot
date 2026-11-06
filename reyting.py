import html
import math
import re
from collections import Counter
from datetime import datetime, timedelta, timezone
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes
import ismlar
import sozlama as S

# ---------- Sozlamalar ----------
TOP_SONI = 10  # /top da nechta odam ko'rsatiladi
EGA_SONI = 5  # /ega da nechta ega ko'rsatiladi
WAIFU_RO_SONI = 30  # /waifu ism : bir xil ismlilar ro'yxatidagi eng ko'p qator
# Kunlik ulashish limiti /panel dan o'zgartiriladi (sozlama.py: coin_limit)
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


# ---------- /ega : waifu egalari (faqat raqam bo'yicha, sahifalar bilan) ----------
async def _waifu_raqamda(raqam):
    return await _baza["characters"].find_one({"raqam": raqam})


async def _ega_korinishi(p, sahifa, bot, chat_id):
    sanash = Counter()
    async for d in _baza["collection"].find({"char_id": p["_id"]}):
        sanash[d["user_id"]] += 1
    tartib = sorted(sanash.items(), key=lambda x: (-x[1], x[0]))
    jami_ega = len(tartib)
    sahifalar = max(1, math.ceil(jami_ega / EGA_SONI))
    sahifa = max(0, min(sahifa, sahifalar - 1))
    qism = tartib[sahifa * EGA_SONI:(sahifa + 1) * EGA_SONI]
    xarita = (
        await ismlar.ol(_baza, [u for u, _ in qism], bot, chat_id) if qism else {}
    )
    if qism:
        qatorlar = "\n".join(
            f"{nishon(sahifa * EGA_SONI + i)} {toza(xarita[u])} — ×{n}"
            for i, (u, n) in enumerate(qism)
        )
    else:
        qatorlar = "Hali hech kimda yo'q"
    daraja = DARAJA.get(str(p["rarity"]).lower(), str(p["rarity"]))
    matn = (
        f"🗽 Ismi : {toza(p['name'])}\n"
        f"🎗️ Daraja : {daraja}\n"
        f"👀 Manba : {toza(p['anime'])}\n"
        f"🔢 Raqam : {p.get('raqam', '?')}\n\n"
        f"👑 Egalari ({jami_ega} kishi) • {sahifa + 1}/{sahifalar}:\n{qatorlar}"
    )
    tugma = None
    if sahifalar > 1:
        r = p.get("raqam")
        tugma = InlineKeyboardMarkup([[
            InlineKeyboardButton("◀️", callback_data=f"eg:{r}:{(sahifa - 1) % sahifalar}"),
            InlineKeyboardButton(f"{sahifa + 1}/{sahifalar}", callback_data="eg:n"),
            InlineKeyboardButton("▶️", callback_data=f"eg:{r}:{(sahifa + 1) % sahifalar}"),
        ]])
    return matn, tugma


async def ega(update: Update, context: ContextTypes.DEFAULT_TYPE):
    xabar = update.message
    s = " ".join(context.args).strip().lstrip("#") if context.args else ""
    if not s.isdigit():
        await xabar.reply_text(
            "👑 Waifu egalari\n\n"
            "Faqat waifu raqami bilan ishlaydi:\n"
            "<code>/ega 4821</code>\n\n"
            "Raqamini bilmasangiz, avval qidiring : <code>/waifu ism</code>",
            parse_mode="HTML",
        )
        return
    p = await _waifu_raqamda(int(s))
    if not p:
        await xabar.reply_text("🔍 Bunday raqamli waifu topilmadi")
        return
    matn, tugma = await _ega_korinishi(
        p, 0, context.bot, update.effective_chat.id
    )
    await xabar.reply_photo(
        photo=p["file_id"], caption=matn, parse_mode="HTML", reply_markup=tugma
    )


async def ega_tugma(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    qismlar = q.data.split(":")
    if qismlar[1] == "n":
        await q.answer()
        return
    p = await _waifu_raqamda(int(qismlar[1]))
    if not p:
        await q.answer("Waifu topilmadi", show_alert=True)
        return
    matn, tugma = await _ega_korinishi(
        p, int(qismlar[2]), context.bot, q.message.chat_id
    )
    try:
        await q.edit_message_caption(
            caption=matn, parse_mode="HTML", reply_markup=tugma
        )
    except Exception:
        pass
    await q.answer()



# ---------- /waifu : waifu haqida to'liq ma'lumot ----------
YULDUZ = {"common": 1, "rare": 2, "epic": 3, "legendary": 4, "special": 5, "max": 6}


async def waifu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    xabar = update.message
    if not context.args:
        await xabar.reply_text(
            "🗽 Waifu haqida ma'lumot\n\n"
            "Ismi yoki raqami bilan qidiring:\n"
            "<code>/waifu Rem</code>  yoki  <code>/waifu 4821</code>",
            parse_mode="HTML",
        )
        return
    s = " ".join(context.args).strip().lstrip("#")
    personajlar = _baza["characters"]
    p = None
    if s.isdigit():
        p = await personajlar.find_one({"raqam": int(s)})
    if not p:
        # Bir xil ismli waifular ko'p bo'lishi mumkin (turli manba): hammasini ko'rsatamiz
        topilgan = [
            d async for d in personajlar.find(
                {"name": {"$regex": f"^{re.escape(s)}$", "$options": "i"}}
            ).limit(WAIFU_RO_SONI + 1)
        ]
        if not topilgan:
            topilgan = [
                d async for d in personajlar.find(
                    {"name": {"$regex": re.escape(s), "$options": "i"}}
                ).limit(WAIFU_RO_SONI + 1)
            ]
        if not topilgan:
            await xabar.reply_text("🔍 Bunday waifu topilmadi")
            return
        if len(topilgan) > 1:
            topilgan.sort(key=lambda d: (str(d["name"]).lower(), d.get("raqam") or 0))
            ortiqcha = len(topilgan) > WAIFU_RO_SONI
            royxat = "\n".join(
                f"• {toza(d['name'])} · {toza(d['anime'])} · "
                f"{DARAJA.get(str(d['rarity']).lower(), str(d['rarity']))} — "
                f"<code>{d.get('raqam', '?')}</code>"
                for d in topilgan[:WAIFU_RO_SONI]
            )
            await xabar.reply_text(
                f"🔎 {min(len(topilgan), WAIFU_RO_SONI)}"
                f"{'+' if ortiqcha else ''} ta waifu topildi. Raqami bilan yozing:\n\n"
                f"{royxat}\n\n<code>/waifu raqam</code>"
                + ("\n\nℹ️ Ro'yxat uzun: ismni aniqroq yozing" if ortiqcha else ""),
                parse_mode="HTML",
            )
            return
        p = topilgan[0]


    sanash = Counter()
    async for d in _baza["collection"].find({"char_id": p["_id"]}):
        sanash[d["user_id"]] += 1
    k = str(p["rarity"]).lower()
    yulduz = YULDUZ.get(k, 1)
    qator = [
        f"🗽 Ismi : {toza(p['name'])}",
        f"🔢 Raqam : {p.get('raqam', '?')}",
        f"🎗️ Daraja : {DARAJA.get(k, str(p['rarity']))}  "
        + "★" * yulduz + "☆" * (6 - yulduz),
        f"👀 Manba : {toza(p['anime'])}",
    ]
    if p.get("event"):
        qator.append(f"🎪 Event : {toza(p['event'])}")
    if ("narx_" + k) in S.RO:
        qator.append(f"💰 Daraja narxi : 🪙 {S.ol('narx_' + k)}")
    qator.append(
        f"👥 Egalari : {len(sanash)} kishi • jami {sum(sanash.values())} ta nusxa"
    )
    elonlar = [d async for d in _baza["bozor"].find({"c": p["_id"]})]
    if elonlar:
        qator.append(
            f"🏪 Do'konda : {len(elonlar)} ta e'lon • eng arzoni "
            f"🪙 {min(d['narx'] for d in elonlar)}"
        )
    else:
        qator.append("🏪 Do'konda : yo'q")
    qator.append(f"\n👑 Egalarini ko'rish : /ega {p.get('raqam', '')}")
    await xabar.reply_photo(
        photo=p["file_id"], caption="\n".join(qator), parse_mode="HTML"
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
        f"Kunlik limit : {S.ol('coin_limit')} 🪙"
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

    qulf = await S.yangi_qulf(_baza, yub.id)
    if qulf:
        await xabar.reply_text(
            f"🔒 Yangi foydalanuvchilar {S.ol('yangi_soat')} soat tanga ulasha olmaydi.\n"
            f"⏳ Qolgan vaqt : {S.vaqt_matni(qulf)}"
        )
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
    if ishlatilgan + n > S.ol("coin_limit"):
        qoldi = max(S.ol("coin_limit") - ishlatilgan, 0)
        await xabar.reply_text(
            f"⏳ Kunlik limit : {S.ol('coin_limit')} 🪙\n"
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
    ilova.add_handler(CallbackQueryHandler(ega_tugma, pattern=r"^eg:"))
    ilova.add_handler(CommandHandler("waifu", waifu))
    ilova.add_handler(CommandHandler("coin", coin))
