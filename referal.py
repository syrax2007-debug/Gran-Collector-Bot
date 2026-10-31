import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes
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


async def ref_yozish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # /start ref_123 : faqat YANGI foydalanuvchiga taklif qilgan odam yoziladi
    if update.effective_chat.type != "private":
        return
    f = update.effective_user
    users = _baza["users"]
    if await users.find_one({"_id": f.id}, {"_id": 1}) is not None:
        return
    if not context.args or not context.args[0].startswith("ref_"):
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
        {"_id": f.id, "ref_tolangan": {"$ne": True}},
        {"$set": {"ref_tolangan": True}},
    )
    if r.modified_count == 0:
        await q.answer("Allaqachon hisoblangan", show_alert=True)
        return
    await users.update_one({"_id": egasi}, {"$inc": {"coins": S.ol('referal_tanga')}})
    await haftalik.qosh(_baza, egasi, "ref", 1)
    try:
        await q.edit_message_text("✅ Rahmat ! Taklif hisoblandi 🫶")
    except Exception:
        pass
    await q.answer("✅")
    try:
        await context.bot.send_message(
            egasi,
            f"🎉 {f.first_name} havolangiz orqali qo'shildi !\n"
            f"💰 Tanga : +{S.ol('referal_tanga')}",
        )
    except Exception:
        pass


def ulash(ilova, baza):
    global _baza
    _baza = baza
    ilova.add_handler(CommandHandler("start", ref_yozish), group=-1)
    ilova.add_handler(CommandHandler("start", ref_xabar), group=1)
    ilova.add_handler(CallbackQueryHandler(ref_tekshir, pattern=r"^rt$"))
