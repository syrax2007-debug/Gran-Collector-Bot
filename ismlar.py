import logging
from telegram import Update
from telegram.ext import ContextTypes, TypeHandler

# Foydalanuvchi ismlarini eslab qoladi: /top, /ega, /coin da
# ID raqami o'rniga ism chiqishi uchun.
NOMA = "Foydalanuvchi"  # ism umuman topilmasa
TG_LIMIT = 15  # bir so'rovda Telegramdan ko'pi bilan nechta ism so'raladi

_baza = None
_kesh = {}  # {id: ism} - bazaga ortiqcha yozmaslik uchun


async def ism_yangila(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Har bir xabar, tugma va so'rovda odamning hozirgi ismini saqlaydi
    try:
        f = update.effective_user
        if not f or f.is_bot:
            return
        ism = (f.first_name or "").strip() or NOMA
        if _kesh.get(f.id) == ism:
            return
        _kesh[f.id] = ism
        await _baza["ismlar"].update_one(
            {"_id": f.id}, {"$set": {"name": ism}}, upsert=True
        )
    except Exception as xato:
        logging.warning("Ismni saqlab bo'lmadi: %s", xato)


async def _telegramdan(bot, chat_id, uid):
    # Guruh a'zosi yoki botga yozgan odamning ismini Telegramdan olamiz
    try:
        if chat_id and chat_id < 0:
            m = await bot.get_chat_member(chat_id, uid)
            return (m.user.first_name or "").strip() or None
        c = await bot.get_chat(uid)
        return (c.first_name or "").strip() or None
    except Exception:
        return None


async def ol(baza, idlar, bot=None, chat_id=None):
    # {id: ism} qaytaradi. Har bir ID uchun albatta ism bo'ladi
    idlar = list(dict.fromkeys(idlar))
    natija = {}
    async for d in baza["ismlar"].find({"_id": {"$in": idlar}}):
        if d.get("name"):
            natija[d["_id"]] = d["name"]
    qolgan = [i for i in idlar if i not in natija]
    if qolgan:
        async for u in baza["users"].find({"_id": {"$in": qolgan}}):
            if u.get("name"):
                natija[u["_id"]] = u["name"]
    if bot is not None:
        topilmadi = [i for i in idlar if i not in natija][:TG_LIMIT]
        for i in topilmadi:
            ism = await _telegramdan(bot, chat_id, i)
            if ism:
                natija[i] = ism
                _kesh[i] = ism
                await baza["ismlar"].update_one(
                    {"_id": i}, {"$set": {"name": ism}}, upsert=True
                )
    for i in idlar:
        natija.setdefault(i, NOMA)
    return natija


def ulash(ilova, baza):
    global _baza
    _baza = baza
    # group=-3: boshqa hamma ishlovchilardan oldin, ularga xalaqit bermaydi
    ilova.add_handler(TypeHandler(Update, ism_yangila), group=-3)
