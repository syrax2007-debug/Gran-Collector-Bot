"""Topishmoq: aralashtirilgan waifu ismini topish (faqat asosiy guruh).

Qoidalar (hammasi /panel -> Topishmoq dan o'zgaradi):
- Har N ta xabardan keyin (standart 10) topishmoq chiqadi.
- Topishmoq M daqiqa turadi (standart 8). Shu paytda guruh xabarlari
  hech narsaga sanalmaydi (waifu chiqishi, MAX, event, keyingi topishmoq).
- Birinchi to'g'ri yozgan odam tanga oladi. Topilsa K1 daqiqa (3) kutiladi,
  topilmasa yopiladi va K2 daqiqa (2) kutiladi, keyin yana N ta xabar sanaladi.
- Topishmoq chiqishidan oldin ketma-ket 6 ta xabar yozgan odam keyingi
  3 ta topishmoqda qatnasha olmaydi (o'zi sanab chiqarib olmasligi uchun).
Holat xotirada turadi: bot qayta ishga tushsa, hisob 0 dan boshlanadi.
"""
import asyncio
import html
import logging
import random
import re
import time

from telegram.ext import CommandHandler, MessageHandler, filters

import sozlama as S

_h = {
    "hisob": 0,         # topishmoqqacha sanalgan xabarlar
    "kut": 0.0,         # shu vaqtgacha xabarlar sanalmaydi (kutish)
    "faol": None,       # hozirgi topishmoq (dict) yoki None
    "uid": None,        # ketma-ket yozayotgan odam
    "seriya": 0,        # uning ketma-ket xabarlari
    "blok": {},         # {uid: nechta topishmoq o'tkazib yuboradi}
    "vazifa": None,
}
_qulf = asyncio.Lock()


def faol():
    return _h["faol"] is not None


def _norm(s):
    return "".join(c for c in str(s).casefold() if c.isalnum())


def aralashtir(ism):
    # Har bir so'z alohida aralashtiriladi; hech bo'lmasa bittasi o'zgaradi
    sozlar = [w for w in re.split(r"\s+", ism.strip()) if w]

    def bir(w):
        h = [c for c in w if c.isalnum()]
        if len(h) < 2 or len(set(h)) == 1:
            return h
        for _ in range(20):
            t = h[:]
            random.shuffle(t)
            if t != h:
                return t
        return h[::-1]

    natija = [bir(w) for w in sozlar]
    if all(a == [c for c in w if c.isalnum()] for a, w in zip(natija, sozlar)):
        natija = [x[::-1] for x in natija]
    return "   ".join(" ".join(c.upper() for c in w) for w in natija)


def ulash(ilova, baza, ADMIN_ID, RASMIY_GURUH):
    chars = baza["characters"]
    users = baza["users"]

    def asosiy(chat):
        return bool(chat) and (chat.username or "").lower() == RASMIY_GURUH

    async def tasodifiy_ism():
        soni = await chars.count_documents({})
        if not soni:
            return None
        for _ in range(8):
            p = await chars.find_one({}, skip=random.randrange(soni))
            if p and len(_norm(p.get("name", ""))) >= 3 and len(str(p["name"])) <= 40:
                return p
        return None

    async def ochish(bot, chat_id):
        p = await tasodifiy_ism()
        if not p:
            return False
        v = S.ol("topishmoq_vaqt")
        # Seriya: oxirgi 6+ ta xabar bitta odamniki bo'lsa, u 3 ta topishmoqni o'tkazadi
        if _h["uid"] and _h["seriya"] >= S.ol("topishmoq_seriya"):
            if S.ol("topishmoq_otkazish") > 0:
                _h["blok"][_h["uid"]] = S.ol("topishmoq_otkazish")
        blok = {u for u, n in _h["blok"].items() if n > 0}
        for u in list(_h["blok"]):
            _h["blok"][u] -= 1
            if _h["blok"][u] <= 0:
                del _h["blok"][u]
        _h["uid"], _h["seriya"], _h["hisob"] = None, 0, 0
        belgi = object()
        _h["faol"] = {"id": belgi, "ism": p["name"], "kalit": _norm(p["name"]), "blok": blok}
        mk = S.ol("topishmoq_mukofot")
        try:
            await bot.send_message(
                chat_id,
                "🧩 <b>TOPISHMOQ!</b>\n\n"
                "Harflar aralashib ketdi. Waifu ismini toping:\n\n"
                f"<code>{html.escape(aralashtir(p['name']))}</code>\n\n"
                f"⏳ {v} daqiqa" + (f" • 🪙 {mk} tanga" if mk else "") + "\n"
                "✍️ Javobni oddiy xabar qilib yozing",
                parse_mode="HTML",
            )
        except Exception as xato:
            logging.warning("Topishmoq yuborib bo'lmadi: %s", xato)
            _h["faol"] = None
            return False
        _h["vazifa"] = asyncio.get_running_loop().create_task(
            _tugat(bot, chat_id, belgi, v * 60)
        )
        return True

    async def _tugat(bot, chat_id, belgi, soniya):
        try:
            await asyncio.sleep(soniya)
        except asyncio.CancelledError:
            return
        async with _qulf:
            f = _h["faol"]
            if not f or f["id"] is not belgi:
                return
            _h["faol"] = None
            _h["hisob"] = 0
            _h["kut"] = time.time() + S.ol("topishmoq_kut_topilmadi") * 60
        try:
            await bot.send_message(
                chat_id,
                f"⌛ Vaqt tugadi, hech kim topmadi.\n🗽 Javob : <b>{html.escape(f['ism'])}</b>",
                parse_mode="HTML",
            )
        except Exception as xato:
            logging.warning("Topishmoq yopilishini yuborib bo'lmadi: %s", xato)

    async def xabar(update, context):
        m = update.effective_message
        c = update.effective_chat
        u = update.effective_user
        if not m or not u or u.is_bot or not asosiy(c) or not S.ol("topishmoq_yoq"):
            return
        async with _qulf:
            f = _h["faol"]
            if f:
                # Javob tekshiruvi (faqat matn)
                if not m.text or u.id in f["blok"]:
                    return
                if _norm(m.text) != f["kalit"]:
                    return
                mk = S.ol("topishmoq_mukofot")
                if mk:
                    r = await users.update_one({"_id": u.id}, {"$inc": {"coins": mk}})
                    if r.matched_count == 0:
                        try:
                            await m.reply_text("🔍 Tanga olish uchun avval botga /start bosing.")
                        except Exception:
                            pass
                        return
                _h["faol"] = None
                if _h["vazifa"]:
                    _h["vazifa"].cancel()
                _h["hisob"] = 0
                _h["kut"] = time.time() + S.ol("topishmoq_kut_topildi") * 60
                ism = html.escape(u.first_name or "Foydalanuvchi")
                try:
                    await m.reply_text(
                        f"🎉 <a href=\"tg://user?id={u.id}\">{ism}</a> topdi!\n"
                        f"🗽 Javob : <b>{html.escape(f['ism'])}</b>"
                        + (f"\n🪙 +{mk} tanga" if mk else ""),
                        parse_mode="HTML",
                    )
                except Exception as xato:
                    logging.warning("Topishmoq g'olibini yozib bo'lmadi: %s", xato)
                return
            # Faol emas: sanash (kutish tugagan bo'lsa)
            if time.time() < _h["kut"]:
                return
            if _h["uid"] == u.id:
                _h["seriya"] += 1
            else:
                _h["uid"], _h["seriya"] = u.id, 1
            _h["hisob"] += 1
            if _h["hisob"] >= S.ol("topishmoq_xabar"):
                await ochish(context.bot, c.id)

    async def buyruq(update, context):
        u = update.effective_user
        if not u or u.id != ADMIN_ID or not asosiy(update.effective_chat):
            return
        async with _qulf:
            if _h["faol"]:
                await update.message.reply_text("🧩 Topishmoq hozir ochiq.")
                return
            await ochish(context.bot, update.effective_chat.id)

    ilova.add_handler(CommandHandler("topishmoq", buyruq))
    # group=3: boshqa ishlovchilardan keyin; to'xtatmaydi
    ilova.add_handler(
        MessageHandler(
            filters.ChatType.GROUPS & ~filters.COMMAND & ~filters.StatusUpdate.ALL, xabar
        ),
        group=3,
    )
