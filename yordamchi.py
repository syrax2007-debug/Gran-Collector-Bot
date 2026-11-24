"""Yordamchi roli: waifu yuklaydi, admin tasdiqlaydi.

Admin buyruqlari (shaxsiy chatda):
  /yordamchi ID        - yordamchi qo'shish (yoki odam xabariga reply)
  /yordamchi_ochir ID  - olib tashlash
  /yordamchilar        - ro'yxat
  /kutilmoqda          - tasdiq kutayotgan waifular
/yordamchi - tugmali panel: yordamchilar, har biriga ruxsatlar.
Standart: faqat ELITA..ULTRA yuklaydi, hammasi admin tasdig'idan o'tadi.
Ruxsatlar: collector, max, event (event buyruqlari), tasdiqsiz (darrov chiqadi).
"""
import html
import logging
import re
import time

from bson import ObjectId
from telegram import InlineKeyboardButton as T, InlineKeyboardMarkup as M
from telegram.ext import (
    ApplicationHandlerStop, CallbackQueryHandler, CommandHandler, MessageHandler, filters,
)

from royxat import keyingi_raqam, raqam_tuzat

BAZA_DARAJALAR = ["common", "rare", "epic", "legendary"]
RUXSATLAR = {
    "collector": "⛩️ COLLECTOR yuklash",
    "max": "👑 MAX yuklash",
    "event": "🎪 Event boshqarish",
    "tasdiqsiz": "⚡ Tasdiqsiz yuklash",
}
_baza = None
_ids = None  # xotirada: {yordamchi ID: ruxsatlar to'plami}


async def yordamchilar_ol():
    global _ids
    if _ids is None:
        _ids = {}
        async for d in _baza["yordamchilar"].find({}):
            _ids[d["_id"]] = set(d.get("ruxsat") or [])
    return _ids


async def yordamchi_mi(uid):
    return uid in await yordamchilar_ol()


async def ruxsat_bor(uid, nom):
    return nom in (await yordamchilar_ol()).get(uid, ())


async def darajalar(uid):
    r = list(BAZA_DARAJALAR)
    p = (await yordamchilar_ol()).get(uid, set())
    if "collector" in p:
        r.append("special")
    if "max" in p:
        r.append("max")
    return r


def _k(s):
    return html.escape(str(s))


def _klav(kalit):
    return M([
        [T("✅ Tasdiqlash", callback_data=f"yq:ok:{kalit}"),
         T("🏷 Daraja", callback_data=f"yq:d:{kalit}")],
        [T("❌ Rad etish", callback_data=f"yq:no:{kalit}")],
    ])


def _matn(doc, NODIRLIK):
    n = NODIRLIK.get(doc["rarity"], (doc["rarity"], 0))[0]
    return (
        "🆕 <b>Yordamchi waifu yukladi</b>\n"
        f"👤 Ism : {_k(doc['name'])}\n"
        f"🎬 Manba : {_k(doc['anime'])}\n"
        f"🏷 Daraja : {n}\n"
        + (f"🎪 Event : {_k(doc['event'])}\n" if doc.get("event") else "")
        + f"🧑‍💻 Yukladi : <a href=\"tg://user?id={doc['yukladi']}\">{_k(doc.get('yukladi_ism') or doc['yukladi'])}</a>"
        f" (<code>{doc['yukladi']}</code>)"
    )


async def tasdiqla_hujjat(baza, doc):
    """Waifuni o'yinga qo'shadi, raqamini qaytaradi."""
    await raqam_tuzat(baza)
    raqam = await keyingi_raqam(baza)
    h = {
        "name": doc["name"], "anime": doc["anime"], "rarity": doc["rarity"],
        "file_id": doc["file_id"], "raqam": raqam, "yukladi": doc["yukladi"],
    }
    if doc.get("event"):
        h["event"] = doc["event"]
    await baza["characters"].insert_one(h)
    return raqam


def ulash(ilova, baza, ADMIN_ID, NODIRLIK):
    global _baza
    _baza = baza
    kut = baza["kutilmoqda"]
    holat = {"qosh": False}

    def admin(update):
        u, c = update.effective_user, update.effective_chat
        return bool(u and u.id == ADMIN_ID and c and c.type == "private")

    async def adminga(bot, doc):
        await bot.send_photo(
            ADMIN_ID, doc["file_id"], caption=_matn(doc, NODIRLIK),
            parse_mode="HTML", reply_markup=_klav(str(doc["_id"])),
        )

    # Yuklash moduli chaqiradi
    global kutilmoqdaga
    async def kutilmoqdaga(bot, hujjat):
        if "tasdiqsiz" in (await yordamchilar_ol()).get(hujjat["yukladi"], ()):
            raqam = await tasdiqla_hujjat(baza, hujjat)
            try:
                await bot.send_message(
                    ADMIN_ID,
                    f"⚡ Yordamchi <code>{hujjat['yukladi']}</code> tasdiqsiz yukladi:\n"
                    f"{_k(hujjat['name'])} ({NODIRLIK.get(hujjat['rarity'], (hujjat['rarity'],))[0]}) — № {raqam}",
                    parse_mode="HTML",
                )
            except Exception:
                pass
            return raqam
        hujjat["t"] = time.time()
        r = await kut.insert_one(hujjat)
        hujjat["_id"] = r.inserted_id
        try:
            await adminga(bot, hujjat)
        except Exception as xato:
            logging.warning("Adminga yuborib bo'lmadi: %s", xato)
        return None

    # ---------- admin paneli: /yordamchi ----------
    async def ism_ol(uid):
        d = await baza["users"].find_one({"_id": uid})
        return (d or {}).get("name") or str(uid)

    async def bosh_korinish():
        ids = await yordamchilar_ol()
        klav = []
        for uid, p in sorted(ids.items()):
            soni = await kut.count_documents({"yukladi": uid})
            klav.append([T(
                f"👤 {await ism_ol(uid)} · {len(p)} ruxsat" + (f" · ⏳{soni}" if soni else ""),
                callback_data=f"yp:u:{uid}",
            )])
        klav.append([T("➕ Yordamchi qo'shish", callback_data="yp:a")])
        return (
            "👥 <b>Yordamchilar</b>\n\nYordamchini bosib ruxsatlarini o'zgartiring."
            if ids else "👥 <b>Yordamchilar</b>\n\nHali yo'q. Qo'shish uchun ➕ ni bosing.",
            M(klav),
        )

    async def odam_korinish(uid):
        p = (await yordamchilar_ol()).get(uid)
        if p is None:
            return await bosh_korinish()
        klav = [
            [T(("✅ " if k in p else "⬜ ") + nom, callback_data=f"yp:t:{uid}:{k}")]
            for k, nom in RUXSATLAR.items()
        ]
        klav.append([T("🗑 Yordamchilikdan olish", callback_data=f"yp:x:{uid}")])
        klav.append([T("⬅️ Orqaga", callback_data="yp:m")])
        return (
            f"👤 <b>{_k(await ism_ol(uid))}</b>\n🆔 <code>{uid}</code>\n\n"
            "Doim: ELITA, SUPER, MEGA, ULTRA yuklash (admin tasdig'i bilan).\n"
            "Qo'shimcha ruxsatlar (bosib yoqing/o'chiring):\n\n"
            "⚡ <i>Tasdiqsiz</i> yoqilsa, yuklagani sizning ko'rishingizsiz o'yinga tushadi.",
            M(klav),
        )

    async def panel(update, context):
        if not admin(update):
            return
        uid = None
        r = update.message.reply_to_message
        if r and r.from_user and not r.from_user.is_bot:
            uid = r.from_user.id
        elif context.args and re.fullmatch(r"\d{5,15}", context.args[0]):
            uid = int(context.args[0])
        if uid and uid != ADMIN_ID:
            await _qosh(context.bot, uid)
            matn, k = await odam_korinish(uid)
        else:
            matn, k = await bosh_korinish()
        await update.message.reply_text(matn, parse_mode="HTML", reply_markup=k)

    async def _qosh(bot, uid):
        ids = await yordamchilar_ol()
        if uid in ids:
            return False
        await baza["yordamchilar"].update_one(
            {"_id": uid}, {"$set": {"t": time.time(), "ruxsat": []}}, upsert=True
        )
        ids[uid] = set()
        try:
            await bot.send_message(
                uid, "👥 Siz yordamchi bo'ldingiz. Waifu yuklash: /yuklash\n"
                "Yuklaganlaringiz admin tasdig'idan keyin o'yinga chiqadi."
            )
        except Exception:
            pass
        return True

    async def panel_tugma(update, context):
        q = update.callback_query
        if q.from_user.id != ADMIN_ID:
            await q.answer("Faqat admin uchun", show_alert=True)
            return
        d = q.data.split(":")
        amal = d[1]
        ids = await yordamchilar_ol()
        await q.answer()
        if amal == "m":
            holat["qosh"] = False
            matn, k = await bosh_korinish()
        elif amal == "u":
            matn, k = await odam_korinish(int(d[2]))
        elif amal == "t":
            uid, nom = int(d[2]), d[3]
            if uid in ids and nom in RUXSATLAR:
                ids[uid] ^= {nom}
                await baza["yordamchilar"].update_one(
                    {"_id": uid}, {"$set": {"ruxsat": sorted(ids[uid])}}
                )
            matn, k = await odam_korinish(uid)
        elif amal == "x":
            uid = int(d[2])
            matn = f"🗑 <code>{uid}</code> ni yordamchilikdan olasizmi?"
            k = M([[T("✅ Ha, olish", callback_data=f"yp:X:{uid}"),
                    T("⬅️ Yo'q", callback_data=f"yp:u:{uid}")]])
        elif amal == "X":
            uid = int(d[2])
            await baza["yordamchilar"].delete_one({"_id": uid})
            ids.pop(uid, None)
            matn, k = await bosh_korinish()
        elif amal == "a":
            holat["qosh"] = True
            matn = ("➕ Yordamchi ID raqamini yuboring (masalan <code>123456789</code>) "
                    "yoki shu odamning xabarini menga forward qiling.")
            k = M([[T("⬅️ Bekor", callback_data="yp:m")]])
        else:
            return
        try:
            await q.edit_message_text(matn, parse_mode="HTML", reply_markup=k)
        except Exception:
            pass

    async def qosh_matn(update, context):
        # Faqat "➕ Qo'shish" bosilgandan keyin keladigan xabarni ushlaydi
        if not holat["qosh"] or not admin(update):
            return
        m = update.message
        uid = None
        fo = getattr(m, "forward_origin", None)
        su = getattr(fo, "sender_user", None)
        if su:
            uid = su.id
        elif m.text and re.fullmatch(r"\d{5,15}", m.text.strip()):
            uid = int(m.text.strip())
        if not uid:
            await m.reply_text("ID raqam yuboring yoki xabarni forward qiling (yashirin profil bo'lsa, ID yozing).")
            raise ApplicationHandlerStop
        holat["qosh"] = False
        if uid == ADMIN_ID:
            await m.reply_text("Siz adminsiz.")
            raise ApplicationHandlerStop
        await _qosh(context.bot, uid)
        matn, k = await odam_korinish(uid)
        await m.reply_text(matn, parse_mode="HTML", reply_markup=k)
        raise ApplicationHandlerStop

    async def kutilmoqda(update, context):
        if not admin(update):
            return
        n = await kut.count_documents({})
        if not n:
            await update.message.reply_text("✅ Tasdiq kutayotgan waifu yo'q.")
            return
        await update.message.reply_text(f"⏳ Kutilmoqda: {n} ta. Birinchi 10 tasi yuboriladi:")
        async for d in kut.find({}).sort("t", 1).limit(10):
            try:
                await adminga(context.bot, d)
            except Exception as xato:
                logging.warning("Kutilmoqdani yuborib bo'lmadi: %s", xato)

    # ---------- tasdiq tugmalari ----------
    async def tugma(update, context):
        q = update.callback_query
        if q.from_user.id != ADMIN_ID:
            await q.answer("Faqat admin uchun", show_alert=True)
            return
        d = q.data.split(":")
        amal, kalit = d[1], d[2]
        try:
            oid = ObjectId(kalit)
        except Exception:
            await q.answer("Xato")
            return
        doc = await kut.find_one({"_id": oid})
        if not doc:
            await q.answer("Bu allaqachon ko'rib chiqilgan", show_alert=True)
            try:
                await q.edit_message_reply_markup(None)
            except Exception:
                pass
            return
        await q.answer()
        if amal == "ok":
            r = await kut.find_one_and_delete({"_id": oid})  # ikki marta bosilmasin
            if not r:
                return
            raqam = await tasdiqla_hujjat(baza, doc)
            await q.edit_message_caption(
                f"✅ Tasdiqlandi — № {raqam}\n" + _matn(doc, NODIRLIK).split("\n", 1)[1],
                parse_mode="HTML",
            )
            try:
                await context.bot.send_message(
                    doc["yukladi"], f"✅ {doc['name']} tasdiqlandi (№ {raqam})"
                )
            except Exception:
                pass
        elif amal == "no":
            r = await kut.find_one_and_delete({"_id": oid})
            if not r:
                return
            await q.edit_message_caption(
                "❌ Rad etildi\n" + _matn(doc, NODIRLIK).split("\n", 1)[1], parse_mode="HTML"
            )
            try:
                await context.bot.send_message(doc["yukladi"], f"❌ {doc['name']} rad etildi")
            except Exception:
                pass
        elif amal == "d":
            dl = await darajalar(doc["yukladi"])
            qator = [T(NODIRLIK[k][0], callback_data=f"yq:s:{kalit}:{k}") for k in dl]
            klav = _qator(qator, 2) + [[T("⬅️ Orqaga", callback_data=f"yq:b:{kalit}")]]
            await q.edit_message_reply_markup(M(klav))
        elif amal == "s":
            k = d[3]
            if k in await darajalar(doc["yukladi"]):
                await kut.update_one({"_id": oid}, {"$set": {"rarity": k}})
                doc["rarity"] = k
            await q.edit_message_caption(_matn(doc, NODIRLIK), parse_mode="HTML", reply_markup=_klav(kalit))
        elif amal == "b":
            await q.edit_message_reply_markup(_klav(kalit))

    ilova.add_handler(CommandHandler("yordamchi", panel))
    ilova.add_handler(CommandHandler("yordamchilar", panel))
    ilova.add_handler(CommandHandler("kutilmoqda", kutilmoqda))
    ilova.add_handler(CallbackQueryHandler(tugma, pattern=r"^yq:"))
    ilova.add_handler(CallbackQueryHandler(panel_tugma, pattern=r"^yp:"))
    # group=-7: faqat ➕ bosilgach xabarni ushlaydi, boshqa hammasiga tegmaydi
    ilova.add_handler(
        MessageHandler(filters.ChatType.PRIVATE & ~filters.COMMAND, qosh_matn), group=-7
    )


def _qator(tugmalar, n):
    return [tugmalar[i:i + n] for i in range(0, len(tugmalar), n)]


async def kutilmoqdaga(bot, hujjat):  # ulash() ichida qayta belgilanadi
    raise RuntimeError("yordamchi.ulash() chaqirilmagan")
