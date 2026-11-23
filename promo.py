"""MAX waifu uchun 1 martalik promo kodlar.

Admin (shaxsiy chatda):
  /maxkod            - tasodifiy MAX waifu uchun kod
  /maxkod 4821       - aniq MAX waifu (raqami) uchun kod
  /maxkodlar         - hali ishlatilmagan kodlar
  /maxkod_ochir KOD  - kodni bekor qilish
Admin kodni *AB7K2* ko'rinishida asosiy guruh xabariga yashiradi. Guruhda
kodni birinchi yozgan odam MAX waifuni oladi (kod bir marta ishlaydi).
"""
import html
import logging
import random
import re
import time

from telegram.ext import (
    CommandHandler, ContextTypes, MessageHandler, filters,
)

from royxat import ism_belgi

HARFLAR = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # O, I, 0, 1 yo'q (adashmaslik uchun)
TOKEN = re.compile(r"[A-Za-z0-9]{5}")
FAOL_YANGILASH = 60  # soniya


def ulash(ilova, baza, ADMIN_ID, RASMIY_GURUH, yulduz_matni):
    promo = baza["promo"]
    chars = baza["characters"]
    holat = {"faol": set(), "t": 0.0}

    async def faollar(majbur=False):
        # Xotirada saqlaymiz, har xabarda bazaga murojaat qilmaslik uchun
        if majbur or time.time() - holat["t"] > FAOL_YANGILASH:
            s = set()
            async for d in promo.find({"ishlatdi": None}, {"_id": 1}):
                s.add(d["_id"])
            holat["faol"], holat["t"] = s, time.time()
        return holat["faol"]

    def admin_shaxsiy(update):
        u, c = update.effective_user, update.effective_chat
        return bool(u and u.id == ADMIN_ID and c and c.type == "private")

    async def maxkod(update, context: ContextTypes.DEFAULT_TYPE):
        if not admin_shaxsiy(update):
            return
        m = update.message
        p = None
        arg = " ".join(context.args).strip().lstrip("#")
        if arg:
            if not arg.isdigit():
                await m.reply_text("Raqam yozing: /maxkod 4821")
                return
            p = await chars.find_one({"raqam": int(arg)})
            if not p:
                await m.reply_text("Bunday raqamli waifu yo'q.")
                return
            if str(p.get("rarity", "")).lower() != "max":
                await m.reply_text("Bu waifu MAX emas. Promo kod faqat MAX uchun.")
                return
        else:
            soni = await chars.count_documents({"rarity": {"$in": ["max", "Max", "MAX"]}})
            if not soni:
                await m.reply_text("Bazada MAX waifu yo'q. Avval /yuklash bilan MAX yuklang.")
                return
            p = await chars.find_one(
                {"rarity": {"$in": ["max", "Max", "MAX"]}}, skip=random.randrange(soni)
            )
        for _ in range(20):
            kod = "".join(random.choice(HARFLAR) for _ in range(5))
            if not await promo.find_one({"_id": kod}):
                break
        await promo.insert_one(
            {"_id": kod, "char_id": p["_id"], "t": time.time(), "ishlatdi": None}
        )
        await faollar(True)
        await m.reply_text(
            f"🔑 Promo kod: <code>{kod}</code>\n"
            f"👑 Waifu: {ism_belgi(p)} (№ {p.get('raqam', '?')})\n\n"
            f"Guruhga yashirish uchun nusxa: <code>*{kod}*</code>\n"
            "Kodni birinchi yozgan odam waifuni oladi. Kod 1 marta ishlaydi.",
            parse_mode="HTML",
        )

    async def maxkodlar(update, context):
        if not admin_shaxsiy(update):
            return
        qator = []
        async for d in promo.find({"ishlatdi": None}).sort("t", -1).limit(30):
            p = await chars.find_one({"_id": d["char_id"]})
            qator.append(
                f"<code>{d['_id']}</code> — {ism_belgi(p) if p else '?'}"
                f" (№ {p.get('raqam', '?') if p else '?'})"
            )
        await update.message.reply_text(
            "🔑 <b>Faol kodlar:</b>\n" + ("\n".join(qator) if qator else "Yo'q"),
            parse_mode="HTML",
        )

    async def maxkod_ochir(update, context):
        if not admin_shaxsiy(update):
            return
        kod = (context.args[0] if context.args else "").strip().upper().strip("*")
        r = await promo.delete_one({"_id": kod, "ishlatdi": None}) if kod else None
        await faollar(True)
        await update.message.reply_text(
            "🗑 Kod o'chirildi" if r and r.deleted_count else "Bunday faol kod topilmadi."
        )

    async def guruh_xabar(update, context):
        m = update.effective_message
        c = update.effective_chat
        if not m or not m.text or not c or (c.username or "").lower() != RASMIY_GURUH:
            return
        u = update.effective_user
        if not u or u.is_bot:
            return
        faol = await faollar()
        if not faol:
            return
        for t in TOKEN.findall(m.text)[:10]:
            kod = t.upper()
            if kod not in faol:
                continue
            d = await promo.find_one_and_update(
                {"_id": kod, "ishlatdi": None},
                {"$set": {"ishlatdi": u.id, "vaqt": time.time()}},
            )
            if not d:  # boshqasi tezroq olgan
                faol.discard(kod)
                continue
            faol.discard(kod)
            p = await chars.find_one({"_id": d["char_id"]})
            if not p:
                continue
            await baza["users"].update_one(
                {"_id": u.id}, {"$set": {"name": u.first_name}}, upsert=True
            )
            await baza["collection"].insert_one({"user_id": u.id, "char_id": p["_id"]})
            try:
                await m.delete()  # kod boshqalarga ko'rinmasin
            except Exception:
                pass
            try:
                await context.bot.send_photo(
                    c.id, p["file_id"],
                    caption=(
                        "👑 <b>PROMO KOD TOPILDI!</b>\n\n"
                        f"🫧 <a href=\"tg://user?id={u.id}\">{html.escape(u.first_name or 'Foydalanuvchi')}</a> "
                        "MAX waifuni qo'lga kiritdi!\n"
                        f"🗽 Ismi : {ism_belgi(p)}\n"
                        f"🎗️ RANK : {yulduz_matni(p)}\n"
                        f"🔢 Raqam : {p.get('raqam', '?')}"
                    ),
                    parse_mode="HTML",
                )
            except Exception as xato:
                logging.warning("Promo e'lon xato: %s", xato)
            return

    ilova.add_handler(CommandHandler("maxkod", maxkod))
    ilova.add_handler(CommandHandler("maxkodlar", maxkodlar))
    ilova.add_handler(CommandHandler("maxkod_ochir", maxkod_ochir))
    # Guruh xabarlarini sanashga halal bermaydi (alohida guruh, to'xtatmaydi)
    ilova.add_handler(
        MessageHandler(filters.ChatType.GROUPS & filters.TEXT & ~filters.COMMAND, guruh_xabar),
        group=-4,
    )
