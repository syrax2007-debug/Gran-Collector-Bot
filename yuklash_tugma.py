"""Tugmali /yuklash (faqat admin, shaxsiy chatda).

Oqim: /yuklash -> rasm -> ism -> anime (bosh harf -> tugma) -> daraja ->
(Collector/Max: emoji) -> (Collector: event, event emoji) -> tasdiqlash.
Anime, event va emojilar bazadagi waifularning o'zidan yig'iladi, shuning
uchun alohida ro'yxat saqlash shart emas. Eski "rasm + /yuklash Ism | ..."
usuli o'zgarmagan.
"""
import html
import logging

from telegram import InlineKeyboardButton as T, InlineKeyboardMarkup as M
from telegram.ext import (
    ApplicationHandlerStop, CallbackQueryHandler, CommandHandler,
    MessageHandler, filters,
)

from royxat import keyingi_raqam, manba_kalit, raqam_tuzat

KALIT = "yt"  # context.user_data kaliti


def _k(s):
    return html.escape(str(s))


def _emoji_mi(t):
    t = (t or "").strip()
    return 0 < len(t) <= 12 and not any(c.isalnum() for c in t)


def _qator(tugmalar, n):
    return [tugmalar[i:i + n] for i in range(0, len(tugmalar), n)]


def ulash(ilova, baza, ADMIN_ID, NODIRLIK, nodirlik_kaliti):
    chars = baza["characters"]
    TARTIB = ["common", "rare", "epic", "legendary", "special", "max"]

    def holat(context):
        return context.user_data.get(KALIT)

    def admin_mi(update):
        u = update.effective_user
        c = update.effective_chat
        return bool(u and u.id == ADMIN_ID and c and c.type == "private")

    async def animelar():
        # {kalit: ko'rinadigan nom}
        d = {}
        async for p in chars.find({}, {"anime": 1}):
            nom = " ".join(str(p.get("anime", "")).split())
            if nom:
                d.setdefault(manba_kalit(nom), nom)
        return d

    async def eventlar():
        # [(event nomi, emoji yoki "")]
        d = {}
        async for p in chars.find({"event": {"$exists": True}}, {"event": 1, "event_emoji": 1}):
            e = " ".join(str(p.get("event", "")).split())
            if e and (e not in d or not d[e]):
                d[e] = p.get("event_emoji") or ""
        return sorted(d.items())

    async def emojilar():
        s = []
        async for p in chars.find({"emoji": {"$exists": True}}, {"emoji": 1}):
            e = p.get("emoji")
            if e and e not in s:
                s.append(e)
        return s[:24]

    def bekor_qatori():
        return [T("❌ Bekor", callback_data="yt:x")]

    async def yuborish(update, matn, klav=None):
        # Tugmadan kelsa tahrir qiladi, matndan kelsa yangi xabar yuboradi
        mk = M(klav) if klav else None
        q = update.callback_query
        if q:
            try:
                await q.edit_message_text(matn, parse_mode="HTML", reply_markup=mk)
                return
            except Exception:
                pass
            await q.message.reply_text(matn, parse_mode="HTML", reply_markup=mk)
        else:
            await update.message.reply_text(matn, parse_mode="HTML", reply_markup=mk)

    # ---------- Qadamlar ----------
    async def q_harf(update, st):
        st["qadam"] = "harf"
        an = await animelar()
        harflar = sorted({n[0].upper() for n in an.values()})
        klav = _qator([T(h, callback_data=f"yt:h:{h}") for h in harflar], 6)
        klav.append([T("✍️ Yangi anime", callback_data="yt:an")])
        klav.append(bekor_qatori())
        await yuborish(
            update,
            f"🎴 <b>{_k(st['ism'])}</b>\n\n2️⃣ Anime nomining <b>bosh harfi</b>ni tanlang:",
            klav,
        )

    async def q_daraja(update, st):
        st["qadam"] = "daraja"
        klav = _qator(
            [T(NODIRLIK[k][0], callback_data=f"yt:d:{k}") for k in TARTIB], 2
        )
        klav.append(bekor_qatori())
        await yuborish(
            update,
            f"🎴 <b>{_k(st['ism'])}</b> · {_k(st['anime'])}\n\n3️⃣ Darajani tanlang:",
            klav,
        )

    async def q_emoji(update, st):
        st["qadam"] = "emoji"
        em = await emojilar()
        klav = _qator([T(e, callback_data=f"yt:e:{i}") for i, e in enumerate(em)], 6)
        st["emojilar"] = em
        klav.append(bekor_qatori())
        await yuborish(
            update,
            f"🎴 <b>{_k(st['ism'])}</b> ({NODIRLIK[st['daraja']][0]})\n\n"
            "4️⃣ Waifu uchun <b>1 ta emoji</b> yuboring"
            + (" yoki saqlanganidan tanlang:" if em else ":"),
            klav,
        )

    async def q_event(update, st):
        st["qadam"] = "event"
        ev = await eventlar()
        st["eventlar"] = ev
        klav = _qator([T(n, callback_data=f"yt:v:{i}") for i, (n, _) in enumerate(ev)], 2)
        klav.append([T("✍️ Yangi event", callback_data="yt:ev")])
        klav.append(bekor_qatori())
        await yuborish(update, "5️⃣ <b>Event</b> nomini tanlang yoki yangisini yozing:", klav)

    async def q_event_emoji(update, st):
        st["qadam"] = "event_emoji"
        await yuborish(
            update,
            f"🎪 Event: <b>{_k(st['event'])}</b>\n\n6️⃣ Event uchun <b>1 ta emoji</b> yuboring:",
            [bekor_qatori()],
        )

    async def q_tasdiq(update, st):
        st["qadam"] = "tasdiq"
        n = NODIRLIK[st["daraja"]][0]
        matn = (
            "📝 <b>Tekshiring:</b>\n"
            f"👤 Ism : {_k(st['ism'])}{' ' + st['emoji'] if st.get('emoji') else ''}\n"
            f"🎬 Manba : {_k(st['anime'])}\n"
            f"🏷 Daraja : {n}\n"
            + (f"🎪 Event : {st.get('event_emoji', '')} {_k(st['event'])}\n" if st.get("event") else "")
        )
        klav = [
            [T("✅ Yuklash", callback_data="yt:ok"), T("✏️ Qayta", callback_data="yt:re")],
            bekor_qatori(),
        ]
        await yuborish(update, matn, klav)

    async def saqla(update, st):
        await raqam_tuzat(baza)
        raqam = await keyingi_raqam(baza)
        h = {
            "name": st["ism"], "anime": st["anime"], "rarity": st["daraja"],
            "file_id": st["file_id"], "raqam": raqam,
        }
        if st.get("event"):
            h["event"] = st["event"]
        if st.get("event_emoji"):
            h["event_emoji"] = st["event_emoji"]
        if st.get("emoji"):
            h["emoji"] = st["emoji"]
        await chars.insert_one(h)
        jami = await chars.count_documents({})
        await yuborish(
            update,
            f"✅ {_k(st['ism'])} ({NODIRLIK[st['daraja']][0]}) qo'shildi !\n"
            + (f"⛩️ Event : {_k(st['event'])}\n" if st.get("event") else "")
            + f"🔢 Raqam : {raqam} | 🎴 Jami : {jami}",
            [[T("➕ Yana yuklash", callback_data="yt:new")]],
        )

    # ---------- Buyruq va xabarlar ----------
    async def boshlash(update, context):
        if not admin_mi(update):
            return
        context.user_data[KALIT] = {"qadam": "rasm"}
        await update.message.reply_text(
            "📸 Waifu rasmini yuboring.\n(Bekor qilish: /yuklash_bekor)"
        )
        raise ApplicationHandlerStop

    async def bekor_buyruq(update, context):
        if not admin_mi(update):
            return
        context.user_data.pop(KALIT, None)
        await update.message.reply_text("❌ Bekor qilindi")

    async def rasm(update, context):
        st = holat(context)
        if not admin_mi(update) or not st or st["qadam"] != "rasm":
            return
        st["file_id"] = update.message.photo[-1].file_id
        st["qadam"] = "ism"
        await update.message.reply_text("1️⃣ Waifu <b>ismini</b> yozing:", parse_mode="HTML")
        raise ApplicationHandlerStop

    async def matn(update, context):
        st = holat(context)
        if not admin_mi(update) or not st:
            return
        t = " ".join((update.message.text or "").split())
        q = st["qadam"]
        if q == "ism":
            if not t or len(t) > 80:
                await update.message.reply_text("Ism 1–80 belgi bo'lishi kerak.")
            else:
                st["ism"] = t
                await q_harf(update, st)
        elif q == "anime_yangi":
            if not t or len(t) > 80:
                await update.message.reply_text("Anime nomi 1–80 belgi bo'lishi kerak.")
            else:
                st["anime"] = t
                await q_daraja(update, st)
        elif q == "emoji":
            if not _emoji_mi(t):
                await update.message.reply_text("Faqat 1 ta emoji yuboring (harf yoki raqam emas).")
            else:
                st["emoji"] = t
                await keyin_emoji(update, st)
        elif q == "event_yangi":
            if not t or len(t) > 60:
                await update.message.reply_text("Event nomi 1–60 belgi bo'lishi kerak.")
            else:
                st["event"] = t
                await q_event_emoji(update, st)
        elif q == "event_emoji":
            if not _emoji_mi(t):
                await update.message.reply_text("Faqat 1 ta emoji yuboring.")
            else:
                st["event_emoji"] = t
                await q_tasdiq(update, st)
        else:
            return
        raise ApplicationHandlerStop

    async def keyin_emoji(update, st):
        if st["daraja"] == "special":
            await q_event(update, st)
        else:
            await q_tasdiq(update, st)

    async def tugma(update, context):
        q = update.callback_query
        if not admin_mi(update):
            await q.answer()
            return
        d = q.data.split(":")
        amal = d[1]
        st = holat(context)
        if amal == "x":
            context.user_data.pop(KALIT, None)
            await q.answer()
            await yuborish(update, "❌ Bekor qilindi")
            return
        if amal == "new":
            context.user_data[KALIT] = {"qadam": "rasm"}
            await q.answer()
            await q.message.reply_text("📸 Waifu rasmini yuboring.")
            return
        if not st:
            await q.answer("Eskirgan. /yuklash ni qayta yozing", show_alert=True)
            return
        await q.answer()
        if amal == "h":  # bosh harf tanlandi
            h = d[2]
            an = await animelar()
            nomlar = sorted(n for n in an.values() if n[0].upper() == h)
            st["animelar"] = nomlar
            klav = [[T(n[:40], callback_data=f"yt:a:{i}")] for i, n in enumerate(nomlar)]
            klav.append([T("⬅️ Harflar", callback_data="yt:hb"), T("✍️ Yangi", callback_data="yt:an")])
            klav.append(bekor_qatori())
            await yuborish(update, f"2️⃣ <b>{_k(h)}</b> harfidagi animelar:", klav)
        elif amal == "hb":
            await q_harf(update, st)
        elif amal == "a":
            try:
                st["anime"] = st["animelar"][int(d[2])]
            except Exception:
                await q_harf(update, st)
                return
            await q_daraja(update, st)
        elif amal == "an":
            st["qadam"] = "anime_yangi"
            await yuborish(update, "✍️ Yangi <b>anime nomini</b> yozing:", [bekor_qatori()])
        elif amal == "d":
            if d[2] not in NODIRLIK:
                return
            st["daraja"] = d[2]
            for k in ("emoji", "event", "event_emoji"):
                st.pop(k, None)
            if d[2] in ("special", "max"):
                await q_emoji(update, st)
            else:
                await q_tasdiq(update, st)
        elif amal == "e":
            try:
                st["emoji"] = st["emojilar"][int(d[2])]
            except Exception:
                return
            await keyin_emoji(update, st)
        elif amal == "v":
            try:
                n, em = st["eventlar"][int(d[2])]
            except Exception:
                return
            st["event"] = n
            if em:
                st["event_emoji"] = em
                await q_tasdiq(update, st)
            else:
                await q_event_emoji(update, st)
        elif amal == "ev":
            st["qadam"] = "event_yangi"
            await yuborish(update, "✍️ Yangi <b>event nomini</b> yozing:", [bekor_qatori()])
        elif amal == "re":
            st["qadam"] = "ism"
            await yuborish(update, "1️⃣ Waifu <b>ismini</b> qayta yozing:")
        elif amal == "ok":
            if st.get("qadam") != "tasdiq":
                return
            context.user_data.pop(KALIT, None)
            try:
                await saqla(update, st)
            except Exception as xato:
                logging.warning("Tugmali yuklash xato: %s", xato)
                await yuborish(update, "⚠️ Yuklashda xato. /yuklash ni qayta boshlang.")

    private = filters.ChatType.PRIVATE
    # Oddiy "/yuklash" (rasmsiz). Rasm+izoh usuli eski ishlovchida qoladi.
    ilova.add_handler(CommandHandler("yuklash", boshlash, filters=private & filters.UpdateType.MESSAGE), group=-2)
    ilova.add_handler(CommandHandler("yuklash_bekor", bekor_buyruq, filters=private), group=-2)
    ilova.add_handler(MessageHandler(private & filters.PHOTO & ~filters.CaptionRegex(r"^/(yuklash|upload)"), rasm), group=-2)
    ilova.add_handler(MessageHandler(private & filters.TEXT & ~filters.COMMAND, matn), group=-2)
    ilova.add_handler(CallbackQueryHandler(tugma, pattern=r"^yt:"), group=-2)
