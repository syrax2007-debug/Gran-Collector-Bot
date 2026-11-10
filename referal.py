import asyncio
import logging
import time
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes, TypeHandler
from stil import stil
import haftalik
import sozlama as S

KANAL_ID = "@Grab_Collector"
GURUH_ID = "@Grab_Collector_Chat"
KANAL_URL = "https://t.me/Grab_Collector"
GURUH_URL = "https://t.me/Grab_Collector_Chat"
REFERAL_TANGA = 250  # har bir shartni bajargan do'st uchun

_baza = None


async def a_zomi(bot, chat, user_id):
    # True: a'zo, False: a'zo emas, None: tekshirib bo'lmadi
    try:
        m = await bot.get_chat_member(chat, user_id)
    except Exception as xato:
        logging.warning("A'zolikni tekshirib bo'lmadi (%s): %s", chat, xato)
        return None
    if m.status == "restricted":
        return bool(getattr(m, "is_member", False))
    return m.status in ("member", "administrator", "creator")


KUTISH_SOAT = 5  # tasdiqlangandan keyin tanga shuncha soatdan so'ng beriladi (fermerlikdan himoya)
_vazifa = None


async def _yangi_odam(uid):
    # Waifusi bo'lishi mumkin (guruhda o'ynagan), lekin botga shaxsiy /start bosmagan
    # va hali hech kim taklif qilmagan bo'lishi kerak
    u = await _baza["users"].find_one({"_id": uid})
    if u is None:
        return True
    return not (u.get("referrer") or u.get("ref_tolangan") or u.get("start_bosgan"))


async def ref_yozish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # /start ref_123 : faqat YANGI foydalanuvchiga taklif qilgan odam yoziladi
    if update.effective_chat.type != "private":
        return
    f = update.effective_user
    users = _baza["users"]
    if not context.args or not context.args[0].startswith("ref_"):
        return
    if not await _yangi_odam(f.id):
        return
    try:
        egasi = int(context.args[0][4:])
    except ValueError:
        return
    if egasi == f.id:
        return
    if await users.find_one({"_id": egasi}, {"_id": 1}) is None:
        return
    await users.update_one(
        {"_id": f.id},
        {"$set": {"referrer": egasi, "name": f.first_name}},
        upsert=True,
    )


async def ref_xabar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Taklif bilan kelgan, lekin hali hisoblanmagan odamga eslatma
    if update.effective_chat.type != "private":
        return
    f = update.effective_user
    u = await _baza["users"].find_one({"_id": f.id}) or {}
    if not u.get("referrer") or u.get("ref_tolangan"):
        return
    tugma = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(stil("📢 Kanal"), url=KANAL_URL),
            InlineKeyboardButton(stil("💬 Guruh"), url=GURUH_URL),
        ],
        [InlineKeyboardButton(stil("✅ Tekshirish"), callback_data="rt")],
    ])
    await update.message.reply_text(
        "🤝 Siz do'stingiz taklifi bilan keldingiz !\n\n"
        "📢 Kanalga va 💬 guruhga qo'shiling, keyin ✅ Tekshirish tugmasini bosing.",
        reply_markup=tugma,
    )


async def ref_tekshir(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    f = q.from_user
    users = _baza["users"]
    u = await users.find_one({"_id": f.id}) or {}
    egasi = u.get("referrer")
    if not egasi:
        await q.answer("Sizda taklif havolasi yo'q", show_alert=True)
        return
    if u.get("ref_tolangan"):
        await q.answer("Allaqachon hisoblangan", show_alert=True)
        return
    kanalda = await a_zomi(context.bot, KANAL_ID, f.id)
    guruhda = await a_zomi(context.bot, GURUH_ID, f.id)
    if kanalda is None or guruhda is None:
        await q.answer("Hozir tekshirib bo'lmadi. Keyinroq urinib ko'ring", show_alert=True)
        return
    if not (kanalda and guruhda):
        qolgan = []
        if not kanalda:
            qolgan.append("📢 Kanalga")
        if not guruhda:
            qolgan.append("💬 Guruhga")
        await q.answer(" va ".join(qolgan) + " qo'shiling !", show_alert=True)
        return
    r = await users.update_one(
        {"_id": f.id, "ref_tolangan": {"$ne": True}, "ref_tasdiq": {"$exists": False}},
        {"$set": {"ref_tasdiq": time.time()}},
    )
    if r.modified_count == 0:
        await q.answer("Allaqachon qabul qilingan", show_alert=True)
        return
    if await _baza["collection"].find_one({"user_id": f.id}) is not None:
        # Waifusi bor (haqiqiy o'yinchi): tanga darhol beriladi
        await _tolash(context.bot, {"_id": f.id, "referrer": egasi, "name": f.first_name})
        try:
            await q.edit_message_text("✅ Rahmat ! Taklif hisoblandi 🫶")
        except Exception:
            pass
        await q.answer("✅")
        return
    try:
        await q.edit_message_text(
            "✅ Rahmat ! Taklif qabul qilindi 🫶\n\n"
            f"⏳ Taklif qilgan do'stingiz tangasini {KUTISH_SOAT} soatdan keyin oladi.\n"
            "📢 Kanal va 💬 guruhda qolishingiz kifoya."
        )
    except Exception:
        pass
    await q.answer("✅")
    try:
        fon_boshlash(context.bot)
    except Exception as xato:
        logging.warning("Referal to'lov vazifasini yoqib bo'lmadi: %s", xato)


async def _tolash(bot, d):
    # Taklifchiga tanga beradi (bir marta). d: taklif qilingan odamning hujjati
    users = _baza["users"]
    uid, egasi = d["_id"], d["referrer"]
    r = await users.update_one(
        {"_id": uid, "ref_tolangan": {"$ne": True}}, {"$set": {"ref_tolangan": True}}
    )
    if r.modified_count == 0:
        return False
    tanga = S.ol("referal_tanga")
    await users.update_one({"_id": egasi}, {"$inc": {"coins": tanga}})
    await haftalik.qosh(_baza, egasi, "ref", 1)
    try:
        await bot.send_message(
            egasi,
            f"🎉 {d.get('name') or 'Do`st'} havolangiz orqali qo'shildi !\n💰 Tanga : +{tanga}",
        )
    except Exception:
        pass
    return True


async def tolov_qil(bot):
    # Kutish muddati o'tgan, hali to'lanmagan takliflarni to'laydi (kanal va guruhda qolgan bo'lsa)
    users = _baza["users"]
    chegara = time.time() - KUTISH_SOAT * 3600
    royxat = [
        d async for d in users.find(
            {"ref_tasdiq": {"$lt": chegara}, "ref_tolangan": {"$ne": True},
             "ref_bekor": {"$ne": True}, "referrer": {"$exists": True}}
        ).limit(50)
    ]
    for d in royxat:
        uid, egasi = d["_id"], d["referrer"]
        kanalda = await a_zomi(bot, KANAL_ID, uid)
        guruhda = await a_zomi(bot, GURUH_ID, uid)
        if kanalda is None or guruhda is None:
            continue  # keyingi safar qayta uriniladi
        if not (kanalda and guruhda):
            await users.update_one({"_id": uid}, {"$set": {"ref_bekor": True}})
            continue
        await _tolash(bot, d)


async def _sikl(bot):
    while True:
        try:
            await tolov_qil(bot)
        except Exception as xato:
            logging.warning("Referal to'lovida xato: %s", xato)
        await asyncio.sleep(600)


def fon_boshlash(bot):
    global _vazifa
    if _vazifa is None or _vazifa.done():
        _vazifa = asyncio.get_running_loop().create_task(_sikl(bot))


async def _kutilgan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        fon_boshlash(context.bot)
    except Exception as xato:
        logging.warning("Referal vazifasini yoqib bo'lmadi: %s", xato)


def ulash(ilova, baza):
    global _baza
    _baza = baza
    ilova.add_handler(CommandHandler("start", ref_yozish), group=-1)
    ilova.add_handler(CommandHandler("start", ref_xabar), group=1)
    ilova.add_handler(CallbackQueryHandler(ref_tekshir, pattern=r"^rt$"))
    ilova.add_handler(TypeHandler(Update, _kutilgan, block=False), group=-4)
