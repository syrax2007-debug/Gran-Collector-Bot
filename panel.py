import html
import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters,
)
from stil import stil
import sozlama as S
import adminplus

# /panel : botning hamma sozlamasini bot ichidan o'zgartirish (faqat admin, shaxsiy chatda)
_baza = None
_admin_id = 0
_kutish = {}  # {admin_id: sozlama kaliti} - yangi qiymat kutilyapti
BOLIM = {k: (nom, royxat) for k, nom, royxat in S.BOLIMLAR}


def _admin(update):
    u = update.effective_user
    c = update.effective_chat
    return bool(u) and u.id == _admin_id and c is not None and c.type == "private"


def _tugma(matn, data):
    return InlineKeyboardButton(stil(matn), callback_data=data)


# ---------- oraliq: avvalgi /oraliq tizimi bilan bir xil ----------
async def _ol(kalit):
    if kalit == "oraliq":
        return await adminplus.oraliq_ol()
    return S.ol(kalit)


def _std(kalit):
    return adminplus._oraliq_asl if kalit == "oraliq" else S.standart(kalit)


def _nom(kalit):
    return "Chiqish oralig'i (xabar soni)" if kalit == "oraliq" else S.RO[kalit][3]


def _chegara(kalit):
    return (10, 5000) if kalit == "oraliq" else (S.RO[kalit][1], S.RO[kalit][2])


# ---------- Ko'rinishlar ----------
def bosh_menyu():
    qatorlar, juft = [], []
    for k, nom, _ in S.BOLIMLAR:
        juft.append(_tugma(nom, f"pn:s:{k}"))
        if len(juft) == 2:
            qatorlar.append(juft); juft = []
    if juft:
        qatorlar.append(juft)
    return (
        "⚙️ Sozlamalar paneli\n\nBo'limni tanlang. Qiymat o'zgartirilsa, "
        "bot darrov yangisini ishlatadi, kodga tegish shart emas.",
        InlineKeyboardMarkup(qatorlar),
    )


async def bolim_korinishi(bk):
    nom, royxat = BOLIM[bk]
    qatorlar, matn = [], [f"⚙️ {nom}\n"]
    for k in royxat:
        v = await _ol(k)
        belgi = "" if v == _std(k) else " ✏️"
        matn.append(f"▫️ {_nom(k)} : <b>{v}</b>{belgi}")
        qatorlar.append([_tugma(f"{_nom(k)} • {v}", f"pn:e:{k}")])
    if bk == "slot":
        n = 100 - sum(S.ol(k) for k in S.SLOT_KALITLAR)
        matn.append(f"\n❌ Belgilar mos kelmasligi : <b>{n}%</b> (qolgan ulush)")
    if bk == "claim":
        jami = sum(S.ol(k) for k in S.CLAIM_KALITLAR) or 1
        matn.append("\nAmaldagi ulush : " + " • ".join(
            f"{S.RO[k][3].split()[0]} {S.ol(k) / jami * 100:.1f}%" for k in S.CLAIM_KALITLAR
        ))
    qatorlar.append([_tugma("⬅️ Orqaga", "pn:m")])
    return "\n".join(matn), InlineKeyboardMarkup(qatorlar)


def bolimi(kalit):
    for bk, _, royxat in S.BOLIMLAR:
        if kalit in royxat:
            return bk
    return S.BOLIMLAR[0][0]


# ---------- Buyruq va tugmalar ----------
async def panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _admin(update):
        return
    _kutish.pop(update.effective_user.id, None)
    matn, tugma = bosh_menyu()
    await update.message.reply_text(matn, reply_markup=tugma)


async def tugma(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if q.from_user.id != _admin_id:
        await q.answer("Bu faqat admin uchun", show_alert=True)
        return
    qismlar = q.data.split(":")
    amal = qismlar[1]
    if amal == "m":
        _kutish.pop(q.from_user.id, None)
        matn, t = bosh_menyu()
        await q.edit_message_text(matn, reply_markup=t)
    elif amal == "s":
        _kutish.pop(q.from_user.id, None)
        matn, t = await bolim_korinishi(qismlar[2])
        await q.edit_message_text(matn, parse_mode="HTML", reply_markup=t)
    elif amal == "e":
        k = qismlar[2]
        if k != "oraliq" and k not in S.RO:
            await q.answer("Noma'lum sozlama", show_alert=True)
            return
        _kutish[q.from_user.id] = k
        kam, kop = _chegara(k)
        v = await _ol(k)
        t = InlineKeyboardMarkup([
            [_tugma("♻️ Standartga qaytarish", f"pn:r:{k}")],
            [_tugma("❌ Bekor", f"pn:s:{bolimi(k)}")],
        ])
        await q.edit_message_text(
            f"✏️ {html.escape(_nom(k))}\n\n"
            f"Hozirgi : <b>{v}</b>\nStandart : {_std(k)}\nChegara : {kam} — {kop}\n\n"
            "Yangi qiymatni yozing :",
            parse_mode="HTML", reply_markup=t,
        )
    elif amal == "r":
        k = qismlar[2]
        await _standartga(k)
        _kutish.pop(q.from_user.id, None)
        matn, t = await bolim_korinishi(bolimi(k))
        await q.edit_message_text(
            f"♻️ {html.escape(_nom(k))} standartga qaytdi : {_std(k)}\n\n" + matn,
            parse_mode="HTML", reply_markup=t,
        )
    await q.answer()


async def _standartga(k):
    if k == "oraliq":
        await _baza["sozlamalar"].delete_one({"_id": "oraliq"})
        adminplus._oraliq = adminplus._oraliq_asl
    else:
        await S.tikla(_baza, k)


async def _saqla(k, v):
    if k == "oraliq":
        await _baza["sozlamalar"].update_one(
            {"_id": "oraliq"}, {"$set": {"son": v}}, upsert=True
        )
        adminplus._oraliq = v
    else:
        await S.saqla(_baza, k, v)


async def matn_qabul(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Faqat admin yangi qiymat kutilayotgan paytda ishlaydi
    if not _admin(update):
        return
    k = _kutish.get(update.effective_user.id)
    if not k:
        return
    xabar = update.message
    matn = (xabar.text or "").strip().replace(" ", "")
    if not matn.lstrip("-").isdigit():
        await xabar.reply_text("❌ Faqat son yozing")
        return
    v = int(matn)
    kam, kop = _chegara(k)
    if k == "oraliq":
        xato = None if kam <= v <= kop else f"{kam} dan {kop} gacha son yozing"
    else:
        xato = S.tekshir(k, v)
    if xato:
        await xabar.reply_text(f"❌ {xato}")
        return
    eski = await _ol(k)
    await _saqla(k, v)
    _kutish.pop(update.effective_user.id, None)
    matn2, t = await bolim_korinishi(bolimi(k))
    await xabar.reply_text(
        f"✅ {html.escape(_nom(k))} : {eski} ➜ <b>{v}</b>\n\n" + matn2,
        parse_mode="HTML", reply_markup=t,
    )


def ulash(ilova, baza, admin_id):
    global _baza, _admin_id
    _baza = baza
    _admin_id = admin_id
    ilova.add_handler(CommandHandler("panel", panel))
    ilova.add_handler(CallbackQueryHandler(tugma, pattern=r"^pn:"))
    ilova.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE, matn_qabul
        ),
        group=-2,
    )
