import asyncio
import html
import logging
import random
import time
from datetime import datetime, timedelta, timezone
from telegram import Update
from telegram.ext import CommandHandler, ContextTypes, TypeHandler
import ismlar

# ---------- Sozlamalar ----------
TOSHKENT = timezone(timedelta(hours=5))
KANAL = "@Grab_Collector"  # e'lon shu kanalga chiqadi (bot kanalda admin bo'lishi shart)
SOAT = 21  # hafta yakshanba kuni shu soatda yopiladi (Toshkent vaqti)
# Har bir toifa: (bazadagi maydon, belgi, sarlavha, birlik)
TOIFALAR = [
    ("waifu", "🎴", "Eng ko'p waifu topganlar", "ta"),
    ("coin", "🪙", "Eng ko'p tanga ishlaganlar", "🪙"),
    ("ref", "👥", "Eng ko'p do'st taklif qilganlar", "ta"),
]
# Sovrinlar (uchala toifada bir xil): 1-o'rin Collector waifu, 2-o'rin va 3-o'rin tanga
MUKOFOT_TANGA = {2: 1111, 3: 777}
COLLECTOR_YOQ_TANGA = 3333  # Collector waifu umuman bo'lmasa, 1-o'rin shuni oladi
COLLECTOR_KALITLAR = ["special", "Special", "SPECIAL"]
MEDAL = {1: "🥇", 2: "🥈", 3: "🥉"}

_baza = None
_admin_id = 0
_vazifa = None


# ---------- Hafta hisobi ----------
def hozir():
    return datetime.now(TOSHKENT)


def hafta_id(dt=None):
    # Hafta yakshanba 21:00 dan keyingi yakshanba 21:00 gacha
    dt = (dt or hozir()) + timedelta(hours=24 - SOAT)
    y, h, _ = dt.isocalendar()
    return f"{y}-{h:02d}"


def hafta_raqami(hid):
    return int(hid.split("-")[1])


async def qosh(baza, uid, maydon, n):
    # Hafta hisoblagichiga qo'shadi. Xato bo'lsa, asosiy ishga xalaqit bermaydi.
    if not n:
        return
    try:
        hid = hafta_id()
        await baza["haftalik"].update_one(
            {"_id": f"{hid}:{uid}"},
            {
                "$set": {"hafta": hid, "uid": uid, f"t_{maydon}": time.time()},
                "$inc": {maydon: n},
            },
            upsert=True,
        )
    except Exception as xato:
        logging.warning("Haftalik hisobda xato: %s", xato)


async def reyting(baza, hid, soni=3):
    # {maydon: [(uid, qiymat), ...]} - eng yaxshi 3 tadan
    taqiq = set()
    try:
        async for d in baza["banlar"].find({}):
            taqiq.add(d["_id"])
    except Exception:
        pass
    natija = {}
    for maydon, _, _, _ in TOIFALAR:
        royxat = []
        async for d in baza["haftalik"].find({"hafta": hid, maydon: {"$gte": 1}}):
            if d["uid"] in taqiq:
                continue
            royxat.append((d["uid"], d[maydon], d.get(f"t_{maydon}", 0)))
        # Teng bo'lsa, avval shu songa yetgan odam yuqori turadi
        royxat.sort(key=lambda x: (-x[1], x[2]))
        natija[maydon] = [(u, q) for u, q, _ in royxat[:soni]]
    return natija


def _bog(uid, ism):
    return f'<a href="tg://user?id={uid}">{html.escape(str(ism))}</a>'


def _qiymat(q, birlik):
    return f"{q} {birlik}"


def sovrin_matni():
    return (
        f"🥇 Collector waifu\n"
        f"🥈 {MUKOFOT_TANGA[2]} 🪙\n"
        f"🥉 {MUKOFOT_TANGA[3]} 🪙"
    )


def matn_tuz(natija, ismlar_, sarlavha):
    qismlar = [sarlavha, "✨━ ━━━━━━━━━ ━✨"]
    bor = False
    for maydon, belgi, nom, birlik in TOIFALAR:
        qismlar.append(f"\n{belgi} {nom}")
        royxat = natija.get(maydon, [])
        if not royxat:
            qismlar.append("➖ Hali hech kim")
        for i, (uid, q) in enumerate(royxat, 1):
            bor = True
            qismlar.append(
                f"{MEDAL[i]} {_bog(uid, ismlar_.get(uid, 'Foydalanuvchi'))}"
                f" — {_qiymat(q, birlik)}"
            )
    return "\n".join(qismlar), bor


# ---------- Sovrin berish ----------
async def _sovrin_ber(baza, uid, orin):
    # {"tur": "waifu", "p": personaj} yoki {"tur": "tanga", "miqdor": n}
    if orin == 1:
        shart = {"rarity": {"$in": COLLECTOR_KALITLAR}}
        soni = await baza["characters"].count_documents(shart)
        if soni:
            p = await baza["characters"].find_one(
                shart, skip=random.randrange(soni)
            )
            await baza["collection"].insert_one(
                {"user_id": uid, "char_id": p["_id"]}
            )
            return {"tur": "waifu", "p": p}
        await baza["users"].update_one(
            {"_id": uid}, {"$inc": {"coins": COLLECTOR_YOQ_TANGA}}, upsert=True
        )
        return {"tur": "tanga", "miqdor": COLLECTOR_YOQ_TANGA, "zaxira": True}
    miqdor = MUKOFOT_TANGA[orin]
    await baza["users"].update_one(
        {"_id": uid}, {"$inc": {"coins": miqdor}}, upsert=True
    )
    return {"tur": "tanga", "miqdor": miqdor}


async def tugat(bot, hid):
    # Haftani yopadi: sovrinlarni beradi va kanalga e'lon qiladi
    baza = _baza
    natija = await reyting(baza, hid)
    idlar = [u for royxat in natija.values() for u, _ in royxat]
    if not idlar:
        return
    ismlar_ = await ismlar.ol(baza, idlar, bot)
    matn, _ = matn_tuz(
        natija, ismlar_, f"🏆 HAFTALIK TOPLAR — {hafta_raqami(hid)}-HAFTA"
    )
    sovrinlar = []  # (uid, toifa, orin, sovrin)
    for maydon, belgi, nom, _ in TOIFALAR:
        for orin, (uid, _) in enumerate(natija[maydon], 1):
            try:
                s = await _sovrin_ber(baza, uid, orin)
            except Exception as xato:
                logging.warning("Sovrin berishda xato: %s", xato)
                continue
            sovrinlar.append((uid, f"{belgi} {nom}", orin, s))
    matn += "\n\n🎁 Sovrinlar (har bir toifada)\n" + sovrin_matni()
    matn += "\n\n🚀 Yangi hafta boshlandi! Hammaga omad !"
    # Kanalga e'lon
    try:
        await bot.send_message(
            KANAL, matn, parse_mode="HTML", disable_web_page_preview=True
        )
    except Exception as xato:
        logging.warning("Kanalga e'lon yuborib bo'lmadi: %s", xato)
        try:
            await bot.send_message(
                _admin_id,
                "⚠️ Haftalik e'lonni kanalga yuborib bo'lmadi "
                "(bot kanalda admin ekanini tekshiring). Matn pastda, "
                "sovrinlar allaqachon berilgan:\n\n" + matn,
                parse_mode="HTML", disable_web_page_preview=True,
            )
        except Exception:
            pass
    # G'oliblarga shaxsiy xabar
    for uid, toifa, orin, s in sovrinlar:
        if s["tur"] == "waifu":
            p = s["p"]
            tarif = f"⛩️ Collector waifu : {html.escape(p['name'])} ({p.get('raqam', '?')})"
        else:
            tarif = f"💰 Tanga : +{s['miqdor']}"
        try:
            await bot.send_message(
                uid,
                f"🎉 Tabriklaymiz! Haftalik {MEDAL[orin]} {orin}-o'rin\n"
                f"{toifa}\n{tarif}",
                parse_mode="HTML",
            )
        except Exception:
            pass
    # Collector waifu yo'qligi haqida adminni ogohlantirish
    if any(s.get("zaxira") for _, _, _, s in sovrinlar):
        try:
            await bot.send_message(
                _admin_id,
                "⚠️ Haftalik 1-o'rin uchun Collector waifu topilmadi, "
                f"o'rniga {COLLECTOR_YOQ_TANGA} tanga berildi. "
                "Collector waifu yuklab qo'ying.",
            )
        except Exception:
            pass


async def tekshir(bot):
    sz = _baza["sozlamalar"]
    avval = hafta_id(hozir() - timedelta(days=7))
    await sz.update_one(
        {"_id": "haftalik"}, {"$setOnInsert": {"tugatilgan": ""}}, upsert=True
    )
    d = await sz.find_one({"_id": "haftalik"}) or {}
    if d.get("tugatilgan") == avval:
        return
    # Faqat bitta jarayon haftani yopadi
    r = await sz.update_one(
        {"_id": "haftalik", "tugatilgan": {"$ne": avval}},
        {"$set": {"tugatilgan": avval}},
    )
    if r.modified_count == 0:
        return
    await tugat(bot, avval)


async def sikl(bot):
    while True:
        try:
            await tekshir(bot)
        except Exception:
            logging.exception("Haftalik tekshiruvda xato")
        await asyncio.sleep(60)


def fon_boshlash(bot):
    # Bir marta ishga tushiradi (qayta chaqirilsa ham bitta vazifa ishlaydi)
    global _vazifa
    if _vazifa is None or _vazifa.done():
        _vazifa = asyncio.get_running_loop().create_task(sikl(bot))


async def _kutilgan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Birinchi kelgan xabarda fon vazifasini yoqadi
    try:
        fon_boshlash(context.bot)
    except Exception as xato:
        logging.warning("Haftalik vazifani yoqib bo'lmadi: %s", xato)


async def haftalik_buyruq(update: Update, context: ContextTypes.DEFAULT_TYPE):
    hid = hafta_id()
    natija = await reyting(_baza, hid)
    idlar = [u for royxat in natija.values() for u, _ in royxat]
    ismlar_ = await ismlar.ol(_baza, idlar, context.bot) if idlar else {}
    matn, _ = matn_tuz(natija, ismlar_, f"📊 {hafta_raqami(hid)}-HAFTA REYTINGI")
    # Hafta tugashigacha qancha vaqt qoldi
    hozir_ = hozir()
    kun = (6 - hozir_.weekday()) % 7
    tugash = hozir_.replace(hour=SOAT, minute=0, second=0, microsecond=0) + timedelta(days=kun)
    if tugash <= hozir_:
        tugash += timedelta(days=7)
    qolgan = tugash - hozir_
    soat = int(qolgan.total_seconds() // 3600)
    matn += (
        f"\n\n🎁 Sovrinlar\n{sovrin_matni()}"
        f"\n\n⏳ Hafta tugashiga : {soat // 24} kun {soat % 24} soat"
    )
    await update.message.reply_text(
        matn, parse_mode="HTML", disable_web_page_preview=True
    )


def ulash(ilova, baza, admin_id):
    global _baza, _admin_id
    _baza = baza
    _admin_id = admin_id
    ilova.add_handler(TypeHandler(Update, _kutilgan, block=False), group=-5)
    ilova.add_handler(CommandHandler(["haftalik", "hafta"], haftalik_buyruq))
