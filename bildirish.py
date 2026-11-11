import asyncio
import logging
import time
from datetime import datetime, timedelta, timezone
from telegram import InlineKeyboardMarkup, Update
from telegram.ext import CommandHandler, ContextTypes, TypeHandler
import sandiq
import bozor
import sozlama as S
import qoshimcha

# Mini App : kunlik waifu (web) va doimiy bildirishnomalar.
# Bildirishnomalar yopilmaydi: har safar bazadagi hozirgi holat bo'yicha qayta tuziladi.
TOSHKENT = timezone(timedelta(hours=5))
NOM = {"common": "ELITA", "rare": "SUPER", "epic": "MEGA", "legendary": "ULTRA"}


def _vaqt(soniya):
    return S.vaqt_matni(soniya).upper()


def bugun():
    return datetime.now(TOSHKENT).strftime("%Y-%m-%d")


def ertagacha():
    # Tashkent yarim tungigacha qolgan soniya
    h = datetime.now(TOSHKENT)
    t = (h + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return max(60, int((t - h).total_seconds()))


def veb_tayyor(u):
    return u.get("veb_claim_sana") != bugun()


async def veb_claim(baza, uid):
    # (kod, personaj). kod: ok, olingan, waifu_yoq
    users = baza["users"]
    b = bugun()
    r = await users.update_one(
        {"_id": uid, "veb_claim_sana": {"$ne": b}}, {"$set": {"veb_claim_sana": b}}
    )
    if r.modified_count == 0:
        return "olingan", None
    try:
        p = await qoshimcha._claim_personaji()
        if p is None:
            raise RuntimeError("waifu yo'q")
        await baza["collection"].insert_one({"user_id": uid, "char_id": p["_id"]})
    except Exception:
        # Xato bo'lsa bugungi huquq qaytariladi
        await users.update_one({"_id": uid}, {"$set": {"veb_claim_sana": ""}})
        return "waifu_yoq", None
    return "ok", p


def _qosh(r, tur, belgi, matn):
    r.append({"t": tur, "i": belgi, "m": matn})


async def royxat(baza, u, slot, tolangan, kutilmoqda, bot=False):
    # tur: ok (tayyor), kut (kutilmoqda), info (ma'lumot), ogoh (cheklov)
    r = []
    uid, b, hozir = u["_id"], bugun(), time.time()
    ert = _vaqt(ertagacha())

    # Web kunlik waifu
    if veb_tayyor(u):
        _qosh(r, "ok", "🎁", ("MINI APP : KUNLIK WAIFU TAYYOR (PROFILDAGI TUGMA)" if bot else "KUNLIK WAIFU TAYYOR : PROFILDAGI TUGMANI BOSING"))
    else:
        _qosh(r, "kut", "🎁", "KUNLIK WAIFU OLINDI. KEYINGISI " + ert + " DAN KEYIN")

    # Guruhdagi /claim va /kunlik
    if u.get("claim_sana") != b:
        _qosh(r, "ok", "🌟", "GURUHDA /claim : BUGUNGI WAIFU TAYYOR")
    else:
        _qosh(r, "kut", "🌟", "/claim OLINDI. KEYINGISI " + ert + " DAN KEYIN")
    if u.get("kunlik_sana") != b:
        _qosh(r, "ok", "📅", "GURUHDA /kunlik : BONUS TAYYOR" + (" (SERIYA " + str(u.get("kunlik_seriya", 0)) + " KUN)" if u.get("kunlik_seriya") else ""))
    else:
        _qosh(r, "kut", "📅", "/kunlik OLINDI (SERIYA " + str(u.get("kunlik_seriya", 1)) + " KUN). ERTAGA BONUS OSHADI")

    # Ruletka
    blok = u.get("rul_blok", 0) or 0
    limit_r = S.ol("ruletka_limit")
    if blok > hozir:
        _qosh(r, "kut", "🎰", "RULETKA TANAFFUSDA : " + _vaqt(blok - hozir) + " DAN KEYIN")
    else:
        n = 0 if blok else (u.get("rul_n", 0) or 0)
        oxirgi = u.get("rul_oxirgi", 0) or 0
        kut = oxirgi + S.ol("ruletka_aralik") - hozir
        qolgan = max(limit_r - n, 0) if limit_r else 0
        if kut > 0:
            _qosh(r, "kut", "🎰", "RULETKA : KEYINGI URINISH " + _vaqt(kut) + " DAN KEYIN (QOLDI " + str(qolgan) + ")")
        else:
            _qosh(r, "ok", "🎰", "RULETKA TAYYOR" + (" : " + str(qolgan) + " TA URINISH" if limit_r else ""))
    if limit_r:
        _qosh(r, "info", "ℹ️", "RULETKA : HAR " + _vaqt(S.ol("ruletka_aralik")) + " DA 1 TA, " + str(limit_r) + " TADAN KEYIN " + str(S.ol("ruletka_tanaffus")) + " SOAT TANAFFUS")

    # Slot va 9 kartali o'yin
    if slot is None:
        slot = {"free": u.get("slot_sana") != b, "bonus": "", "narx": S.ol("slot_narx")}
    if slot:
        if slot.get("free"):
            _qosh(r, "ok", "🎲", "SLOT : BUGUNGI BEPUL URINISH BOR")
        else:
            _qosh(r, "kut", "🎲", "SLOT : BEPUL URINISH ISHLATILDI. PULLIK URINISH 🪙 " + str(slot.get("narx", "")))
        if slot.get("bonus") == "bor":
            _qosh(r, "ok", "🎲", "SLOT : REFERAL BONUS URINISH BOR")
    ishl = u.get("oyin_soni", 0) if u.get("oyin_sana") == b else 0
    lim = S.ol("oyin_kunlik")
    if ishl < lim:
        _qosh(r, "ok", "🃏", "9 KARTALI O'YIN : BUGUN " + str(lim - ishl) + " / " + str(lim) + " URINISH QOLDI")
    else:
        _qosh(r, "kut", "🃏", "9 KARTALI O'YIN : LIMIT TUGADI. NARX 🪙 " + str(S.oyin_narx(ishl)))

    # Sandiq limitlari
    try:
        _, qutilar = await sandiq.holat(baza, uid)
        qism = []
        for q in qutilar:
            if q["limit"] > 0 and q["bor"]:
                qism.append(q["nom"] + " " + str(q["qolgan"]) + "/" + str(q["limit"]))
        if qism:
            _qosh(r, "info", "📦", "SANDIQ (BUGUN QOLDI) : " + " • ".join(qism))
    except Exception:
        pass

    # Do'kon
    try:
        mening = len(await bozor.elonlar(baza, uid))
        _qosh(r, "info", "🏪", "DO'KON : E'LONLARINGIZ " + str(mening) + " / " + str(S.ol("bozor_limit")))
    except Exception:
        pass

    # Referal
    if kutilmoqda:
        _qosh(r, "kut", "🤝", "REFERAL : " + str(kutilmoqda) + " TA DO'ST KUTILMOQDA (TEKSHIRUV YOKI KUTISH)")
    _qosh(r, "info", "🤝", "REFERAL : HAR DO'ST UCHUN 🪙 " + str(S.ol("referal_tanga")) + " (HOZIRGACHA " + str(tolangan) + " TA)")

    # Yangi foydalanuvchi cheklovi
    try:
        qulf = int(await S.yangi_qulf(baza, uid))
    except Exception:
        qulf = 0
    if qulf > 0:
        _qosh(r, "ogoh", "⏳", "YANGI FOYDALANUVCHI CHEKLOVI : " + _vaqt(qulf) + " DAN KEYIN SOVG'A, ALMASHISH VA DO'KON OCHILADI")
    return r


# ---------- Botdagi bildirishnomalar ----------
YANGI_KUN_OYNA = 2  # soat: yarim tundan keyin shu vaqt ichida "yangi kun" xabari yuboriladi
_oxirgi_kun = None
_baza = None
_mini = None
_vazifa = None


def _bot_matn(x):
    m = x["m"].lower()
    return f"{x['i']} {m[:1].upper() + m[1:]}"


async def holat_royxati(baza, uid):
    u = await baza["users"].find_one({"_id": uid}) or {"_id": uid}
    u.setdefault("_id", uid)
    tolangan = await baza["users"].count_documents({"referrer": uid, "ref_tolangan": True})
    kut = await baza["users"].count_documents(
        {"referrer": uid, "ref_tolangan": {"$ne": True}, "ref_bekor": {"$ne": True}}
    )
    return await royxat(baza, u, None, tolangan, kut, bot=True)


async def holat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await S.yangila(_baza)
    r = await holat_royxati(_baza, update.effective_user.id)
    await update.message.reply_text(
        "🔔 Holatingiz\n\n" + "\n".join(_bot_matn(x) for x in r)
        + "\n\n🔕 Kunlik eslatmani o'chirish/yoqish : /bildirish"
    )


async def bildirish_buyruq(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != "private":
        return
    uid = update.effective_user.id
    u = await _baza["users"].find_one({"_id": uid}) or {}
    ochiq = not u.get("bild_off")
    await _baza["users"].update_one(
        {"_id": uid}, {"$set": {"bild_off": ochiq}}, upsert=True
    )
    await update.message.reply_text(
        "🔕 Kunlik eslatma o'chirildi. Yoqish : /bildirish" if ochiq
        else "🔔 Kunlik eslatma yoqildi. Har kuni bir marta tayyor narsalar haqida xabar beraman."
    )


def _tayyorlar(u):
    # Faqat tez hisoblanadigan "tayyor" narsalar (hamma foydalanuvchiga yuboriladi)
    b = bugun()
    q = []
    if veb_tayyor(u):
        q.append("🎁 Mini App : kunlik waifu")
    if u.get("claim_sana") != b:
        q.append("🌟 Guruhda /claim : kunlik waifu")
    if u.get("kunlik_sana") != b:
        q.append("📅 Guruhda /kunlik : kunlik bonus")
    if u.get("slot_sana") != b:
        q.append("🎲 Slot : bepul urinish")
    if (u.get("oyin_soni", 0) if u.get("oyin_sana") == b else 0) < S.ol("oyin_kunlik"):
        q.append("🃏 9 kartali o'yin : bugungi urinishlar")
    return q


async def _yuborish(bot, u, matn, jim=False):
    # Xabar yuboradi. Bot bloklangan bo'lsa, eslatmalar o'chiriladi
    try:
        await bot.send_message(
            u["_id"], matn, disable_notification=jim,
            reply_markup=InlineKeyboardMarkup([[_mini()]]) if _mini else None,
        )
        return True
    except Exception as xato:
        t = str(xato).lower()
        if "blocked" in t or "forbidden" in t or "deactivated" in t:
            await _baza["users"].update_one({"_id": u["_id"]}, {"$set": {"bild_off": True}})
        else:
            logging.warning("Eslatma yuborilmadi: %s", xato)
        return False


async def _yangi_kun(bot):
    # 00:00 da qaytadigan limitlar: kunlik waifu, /claim, /kunlik, slot, 9 kartali o'yin, sandiq
    global _oxirgi_kun
    b = bugun()
    if _oxirgi_kun == b or datetime.now(TOSHKENT).hour >= YANGI_KUN_OYNA:
        return
    users = _baza["users"]
    while True:
        royxat_ = [
            d async for d in users.find(
                {"start_bosgan": True, "bild_off": {"$ne": True}, "bild_sana": {"$ne": b}}
            ).limit(100)
        ]
        if not royxat_:
            _oxirgi_kun = b
            return
        for u in royxat_:
            await users.update_one({"_id": u["_id"]}, {"$set": {"bild_sana": b}})
            q = _tayyorlar(u)
            if q:
                # Oddiy (tovushli) xabar: odamlar 00:00 ni kutadi
                await _yuborish(
                    bot, u,
                    "🌙 Yangi kun ! Limitlar yangilandi :\n\n" + "\n".join(q)
                    + "\n📦 Sandiq : kunlik limitlar yangilandi"
                    + "\n\n🔕 O'chirish : /bildirish",
                )
            await asyncio.sleep(0.06)


async def _vaqtli(bot):
    # Vaqtga bog'liq limitlar o'z vaqtida: ruletka tanaffusi va yangi foydalanuvchi cheklovi tugashi
    users = _baza["users"]
    hozir = time.time()
    asos = {"start_bosgan": True, "bild_off": {"$ne": True}}
    # Ruletka: tanaffus tugadi, yana urinish mumkin
    async for u in users.find(dict(asos, rul_blok={"$gt": hozir - 172800, "$lt": hozir})).limit(100):
        if u.get("rul_xabar") == u.get("rul_blok"):
            continue
        await users.update_one({"_id": u["_id"]}, {"$set": {"rul_xabar": u["rul_blok"]}})
        await _yuborish(
            bot, u,
            "🎰 Ruletka tanaffusi tugadi !\n"
            f"Yana {S.ol('ruletka_limit')} tagacha urinish mumkin : /ruletka",
        )
        await asyncio.sleep(0.06)
    # Yangi foydalanuvchi cheklovi tugadi (faqat oxirgi 2 kun ichida tugaganlarga)
    soat = S.ol("yangi_soat")
    if soat > 0:
        async for u in users.find(dict(
            asos, qoshildi={"$gt": hozir - soat * 3600 - 172800, "$lt": hozir - soat * 3600}
        )).limit(100):
            if u.get("qulf_xabar"):
                continue
            await users.update_one({"_id": u["_id"]}, {"$set": {"qulf_xabar": True}})
            await _yuborish(
                bot, u,
                "✅ Yangi foydalanuvchi cheklovi tugadi !\n"
                "Endi sovg'a, almashish va do'kondan to'liq foydalanishingiz mumkin.",
            )
            await asyncio.sleep(0.06)


async def _eslatma(bot):
    await _yangi_kun(bot)
    await _vaqtli(bot)


async def _sikl(bot):
    while True:
        try:
            await _eslatma(bot)
        except Exception as xato:
            logging.warning("Eslatma siklida xato: %s", xato)
        await asyncio.sleep(60)


async def _kutilgan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global _vazifa
    try:
        if _vazifa is None or _vazifa.done():
            _vazifa = asyncio.get_running_loop().create_task(_sikl(context.bot))
    except Exception as xato:
        logging.warning("Eslatma vazifasini yoqib bo'lmadi: %s", xato)


def ulash(ilova, baza, mini_tugma=None):
    global _baza, _mini
    _baza, _mini = baza, mini_tugma
    ilova.add_handler(CommandHandler("holat", holat))
    ilova.add_handler(CommandHandler("bildirish", bildirish_buyruq))
    ilova.add_handler(TypeHandler(Update, _kutilgan, block=False), group=-8)
