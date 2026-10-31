import logging
import time
from telegram import Update
from telegram.ext import ContextTypes, TypeHandler

# Botning hamma sozlamalari shu yerda. Qiymatlar bazada saqlanadi (sozlamalar, _id "panel"),
# o'zgartirish /panel orqali. Bazada yo'q bo'lsa, shu yerdagi standart ishlatiladi.
# Har bir sozlama: kalit: (standart, eng kam, eng ko'p, nomi)
RO = {
    # 🎴 Chiqish
    "event_foiz": (20, 0, 100, "Event ulushi (%)"),
    "w_common": (60, 0, 1000, "ELITA chiqish vazni"),
    "w_rare": (25, 0, 1000, "SUPER chiqish vazni"),
    "w_epic": (10, 0, 1000, "MEGA chiqish vazni"),
    "w_legendary": (5, 0, 1000, "ULTRA chiqish vazni"),
    "w_special": (0, 0, 1000, "COLLECTOR chiqish vazni"),
    # 🎁 Bonuslar
    "xush_tanga": (222, 0, 100000, "Xush kelibsiz tangasi"),
    "kunlik_bonus": (50, 0, 100000, "Kunlik bonus (boshlang'ich)"),
    "kunlik_qosh": (10, 0, 10000, "Kunlik bonus: har kun qo'shimcha"),
    "kunlik_seriya": (6, 1, 60, "Kunlik bonus: eng ko'p seriya kuni"),
    "ruletka_limit": (3, 0, 50, "Ruletka: kunlik urinish"),
    "ruletka_jekpot": (300, 0, 1000000, "Ruletka: jekpot 7️⃣7️⃣7️⃣"),
    "ruletka_uchta": (100, 0, 1000000, "Ruletka: uchta bir xil"),
    "ruletka_ikkita": (15, 0, 1000000, "Ruletka: ikkita bir xil"),
    "referal_tanga": (250, 0, 1000000, "Referal tangasi"),
    # 🎁 /claim
    "claim_common": (45, 0, 1000, "ELITA vazni"),
    "claim_rare": (25, 0, 1000, "SUPER vazni"),
    "claim_epic": (15, 0, 1000, "MEGA vazni"),
    "claim_legendary": (5, 0, 1000, "ULTRA vazni"),
    # 🃏 9 karta
    "oyin_kunlik": (5, 1, 20, "Kunlik urinish soni"),
    "oyin_narx_bosh": (100, 1, 1000000, "1-urinish narxi"),
    "oyin_narx_qadam": (50, 0, 1000000, "Har urinishda narx oshishi"),
    # 🎰 Slot
    "slot_narx": (100, 0, 1000000, "Pullik aylantirish narxi"),
    "s_w": (3, 0, 100, "ULTRA waifu ehtimoli (%)"),
    "s_j": (5, 0, 100, "💎💎💎 ehtimoli (%)"),
    "s_a": (8, 0, 100, "🔥🔥🔥 ehtimoli (%)"),
    "s_b": (12, 0, 100, "🪙🪙🪙 ehtimoli (%)"),
    "s_c": (17, 0, 100, "🌸🌸🌸 ehtimoli (%)"),
    "sov_j": (300, 0, 1000000, "💎💎💎 sovrini"),
    "sov_a": (150, 0, 1000000, "🔥🔥🔥 sovrini"),
    "sov_b": (100, 0, 1000000, "🪙🪙🪙 sovrini"),
    "sov_c": (60, 0, 1000000, "🌸🌸🌸 sovrini"),
    # 🏆 Haftalik
    "hafta_2": (1111, 0, 10000000, "2-o'rin sovrini"),
    "hafta_3": (777, 0, 10000000, "3-o'rin sovrini"),
    # 🔁 Trade
    "narx_common": (600, 1, 100000000, "ELITA narxi"),
    "narx_rare": (1800, 1, 100000000, "SUPER narxi"),
    "narx_epic": (5000, 1, 100000000, "MEGA narxi"),
    "narx_legendary": (12000, 1, 100000000, "ULTRA narxi"),
    "narx_special": (30000, 1, 100000000, "COLLECTOR narxi"),
    "narx_max": (80000, 1, 100000000, "MAX narxi"),
    "trade_limit": (5, 0, 100, "Kunlik almashish soni"),
    "trade_muddat": (10, 1, 120, "Taklif muddati (daqiqa)"),
}

# Panel bo'limlari: (kalit, nomi, [sozlamalar])
BOLIMLAR = [
    ("chiqish", "🎴 Chiqish",
     ["oraliq", "event_foiz", "w_common", "w_rare", "w_epic", "w_legendary", "w_special"]),
    ("bonus", "🎁 Bonuslar",
     ["xush_tanga", "kunlik_bonus", "kunlik_qosh", "kunlik_seriya",
      "ruletka_limit", "ruletka_jekpot", "ruletka_uchta", "ruletka_ikkita", "referal_tanga"]),
    ("claim", "🎁 /claim",
     ["claim_common", "claim_rare", "claim_epic", "claim_legendary"]),
    ("oyin", "🃏 9 karta", ["oyin_kunlik", "oyin_narx_bosh", "oyin_narx_qadam"]),
    ("slot", "🎰 Slot",
     ["slot_narx", "s_w", "s_j", "s_a", "s_b", "s_c", "sov_j", "sov_a", "sov_b", "sov_c"]),
    ("hafta", "🏆 Haftalik", ["hafta_2", "hafta_3"]),
    ("trade", "🔁 Trade va narx",
     ["narx_common", "narx_rare", "narx_epic", "narx_legendary", "narx_special", "narx_max",
      "trade_limit", "trade_muddat"]),
]
SLOT_KALITLAR = ("s_w", "s_j", "s_a", "s_b", "s_c")
CLAIM_KALITLAR = ("claim_common", "claim_rare", "claim_epic", "claim_legendary")
CHIQISH_KALITLAR = ("w_common", "w_rare", "w_epic", "w_legendary", "w_special")

YANGILASH_ORALIGI = 15  # soniya
_qiymat = {}
_oxirgi = 0.0


def standart(kalit):
    return RO[kalit][0]


def ol(kalit):
    # Hozirgi qiymat (bazadan o'qilgan bo'lsa shu, bo'lmasa standart)
    v = _qiymat.get(kalit)
    return RO[kalit][0] if v is None else v


async def yangila(baza, majbur=False):
    # Bazadan o'qiydi, lekin har safar emas (har 15 soniyada)
    global _qiymat, _oxirgi
    hozir = time.time()
    if not majbur and hozir - _oxirgi < YANGILASH_ORALIGI:
        return
    _oxirgi = hozir
    try:
        d = await baza["sozlamalar"].find_one({"_id": "panel"}) or {}
    except Exception as xato:
        logging.warning("Sozlamalarni o'qib bo'lmadi: %s", xato)
        return
    yangi = {}
    for k, v in d.items():
        if k in RO and isinstance(v, int) and not isinstance(v, bool):
            yangi[k] = v
    _qiymat = yangi


def tekshir(kalit, qiymat):
    # None - yaroqli, aks holda xato matni
    _, kam, kop, _ = RO[kalit]
    if not kam <= qiymat <= kop:
        return f"{kam} dan {kop} gacha son yozing"
    if kalit in SLOT_KALITLAR:
        jami = sum(qiymat if k == kalit else ol(k) for k in SLOT_KALITLAR)
        if jami > 100:
            return f"Slot ehtimollari yig'indisi 100 dan oshmasin (hozir {jami}). Boshqasini kamaytiring"
    if kalit in CLAIM_KALITLAR:
        if sum(qiymat if k == kalit else ol(k) for k in CLAIM_KALITLAR) <= 0:
            return "Kamida bitta daraja 0 dan katta bo'lishi kerak"
    if kalit in CHIQISH_KALITLAR:
        if sum(qiymat if k == kalit else ol(k) for k in CHIQISH_KALITLAR) <= 0:
            return "Kamida bitta daraja 0 dan katta bo'lishi kerak"
    return None


async def saqla(baza, kalit, qiymat):
    await baza["sozlamalar"].update_one(
        {"_id": "panel"}, {"$set": {kalit: qiymat}}, upsert=True
    )
    _qiymat[kalit] = qiymat


async def tikla(baza, kalit):
    # Standartga qaytaradi
    await baza["sozlamalar"].update_one(
        {"_id": "panel"}, {"$unset": {kalit: ""}}, upsert=True
    )
    _qiymat.pop(kalit, None)


# ---- ko'p ishlatiladigan hisoblar
def slot_natijalar():
    # (belgi, ehtimol %, tanga). "n" = belgilar mos kelmadi (qolgan ulush)
    w, j, a, b, c = (ol(k) for k in SLOT_KALITLAR)
    n = max(0, 100 - (w + j + a + b + c))
    return [
        ("w", w, 0), ("j", j, ol("sov_j")), ("a", a, ol("sov_a")),
        ("b", b, ol("sov_b")), ("c", c, ol("sov_c")), ("n", n, 0),
    ]


async def _yangila_ishlovchi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        await yangila(_baza)
    except Exception as xato:
        logging.warning("Sozlamani yangilab bo'lmadi: %s", xato)


_baza = None


def ulash(ilova, baza):
    global _baza
    _baza = baza
    # Hamma ishlovchilardan oldin: sozlamalar doim yangi bo'ladi
    ilova.add_handler(TypeHandler(Update, _yangila_ishlovchi), group=-6)
