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
    "ruletka_limit": (7, 0, 50, "Ruletka: ketma-ket urinish (keyin tanaffus)"),
    "ruletka_aralik": (180, 0, 86400, "Ruletka: urinishlar orasi (soniya)"),
    "ruletka_tanaffus": (10, 0, 240, "Ruletka: tanaffus (soat)"),
    "ruletka_jekpot": (350, 0, 1000000, "Ruletka: jekpot 7️⃣7️⃣7️⃣"),
    "ruletka_uchta": (150, 0, 1000000, "Ruletka: uchta bir xil"),
    "ruletka_ikkita": (50, 0, 1000000, "Ruletka: ikkita bir xil"),
    "referal_tanga": (500, 0, 1000000, "Referal tangasi"),
    # 🎁 /claim
    "claim_common": (70, 0, 1000, "ELITA vazni"),
    "claim_rare": (20, 0, 1000, "SUPER vazni"),
    "claim_epic": (6, 0, 1000, "MEGA vazni"),
    "claim_legendary": (4, 0, 1000, "ULTRA vazni"),
    # 🃏 9 karta
    "oyin_kunlik": (5, 1, 20, "Kunlik urinish soni"),
    "oyin_narx_bosh": (100, 1, 1000000, "1-urinish narxi"),
    "oyin_narx_qadam": (50, 0, 1000000, "Har urinishda narx oshishi"),
    # 🎰 Slot
    "slot_narx": (150, 0, 1000000, "Pullik aylantirish narxi"),
    "s_w": (3, 0, 100, "👑 ULTRA waifu ehtimoli (%)"),
    "s_m": (4, 0, 100, "🔮 MEGA waifu ehtimoli (%)"),
    "s_s": (6, 0, 100, "🌟 SUPER waifu ehtimoli (%)"),
    "s_e": (9, 0, 100, "🍀 ELITA waifu ehtimoli (%)"),
    "s_j": (5, 0, 100, "💎💎💎 ehtimoli (%)"),
    "s_a": (7, 0, 100, "🔥🔥🔥 ehtimoli (%)"),
    "s_b": (11, 0, 100, "🪙🪙🪙 ehtimoli (%)"),
    "s_c": (16, 0, 100, "🌸🌸🌸 ehtimoli (%)"),
    "sov_j": (300, 0, 1000000, "💎💎💎 sovrini"),
    "sov_a": (150, 0, 1000000, "🔥🔥🔥 sovrini"),
    "sov_b": (100, 0, 1000000, "🪙🪙🪙 sovrini"),
    "sov_c": (60, 0, 1000000, "🌸🌸🌸 sovrini"),
    # 🏆 Haftalik
    "hafta_2": (1111, 0, 10000000, "2-o'rin sovrini"),
    "hafta_3": (777, 0, 10000000, "3-o'rin sovrini"),
    # 🔁 Trade
    "narx_common": (500, 1, 100000000, "ELITA narxi"),
    "narx_rare": (1500, 1, 100000000, "SUPER narxi"),
    "narx_epic": (3500, 1, 100000000, "MEGA narxi"),
    "narx_legendary": (8000, 1, 100000000, "ULTRA narxi"),
    "narx_special": (12000, 1, 100000000, "COLLECTOR narxi"),
    "narx_max": (25000, 1, 100000000, "MAX narxi"),
    "trade_limit": (5, 0, 100, "Kunlik almashish soni"),
    "trade_muddat": (10, 1, 120, "Taklif muddati (daqiqa)"),
    # 🎁 Sovga va tanga ulashish
    "yangi_soat": (24, 0, 720, "Yangi foydalanuvchi cheklovi (soat, 0 = o'chiq)"),
    "sovga_limit": (5, 0, 100, "Kunlik sovga soni"),
    "sovga_collector": (1, 0, 1, "COLLECTOR/MAX sovga qilishni taqiqlash (1 = ha, 0 = yo'q)"),
    "coin_limit": (1000, 0, 100000000, "Kunlik tanga ulashish limiti"),
    # 🏪 Do'kon (o'yinchilar bir-biriga waifu sotadi)
    "bozor_min": (70, 1, 100000, "Eng kam narx (% : daraja narxidan)"),
    "bozor_min_col": (80, 1, 100000, "COLLECTOR eng kam narx (% : daraja narxidan)"),
    "bozor_max": (110, 0, 1000000, "Eng ko'p narx (% : daraja narxidan, 0 = cheksiz)"),
    "bozor_limit": (3, 0, 100, "Bitta odamning e'lonlari soni (0 = yopiq)"),
    # 📦 Sandiq (omadli qutilar)
    "quti_common": (475, 1, 100000000, "ELITA qutisi narxi"),
    "quti_rare": (1425, 1, 100000000, "SUPER qutisi narxi"),
    "quti_epic": (3325, 1, 100000000, "MEGA qutisi narxi"),
    "quti_legendary": (7600, 1, 100000000, "ULTRA qutisi narxi"),
    "qlimit_common": (10, 0, 1000, "ELITA qutisi : kunlik limit (0 = yopiq)"),
    "qlimit_rare": (5, 0, 1000, "SUPER qutisi : kunlik limit (0 = yopiq)"),
    "qlimit_epic": (3, 0, 1000, "MEGA qutisi : kunlik limit (0 = yopiq)"),
    "qlimit_legendary": (1, 0, 1000, "ULTRA qutisi : kunlik limit (0 = yopiq)"),
}

# Panel bo'limlari: (kalit, nomi, [sozlamalar])
BOLIMLAR = [
    ("chiqish", "🎴 Chiqish",
     ["oraliq", "event_foiz", "w_common", "w_rare", "w_epic", "w_legendary", "w_special"]),
    ("bonus", "🎁 Bonuslar",
     ["xush_tanga", "kunlik_bonus", "kunlik_qosh", "kunlik_seriya",
      "ruletka_limit", "ruletka_aralik", "ruletka_tanaffus",
      "ruletka_jekpot", "ruletka_uchta", "ruletka_ikkita", "referal_tanga"]),
    ("claim", "🎁 /claim",
     ["claim_common", "claim_rare", "claim_epic", "claim_legendary"]),
    ("oyin", "🃏 9 karta", ["oyin_kunlik", "oyin_narx_bosh", "oyin_narx_qadam"]),
    ("slot", "🎰 Slot",
     ["slot_narx", "s_w", "s_m", "s_s", "s_e", "s_j", "s_a", "s_b", "s_c",
      "sov_j", "sov_a", "sov_b", "sov_c"]),
    ("hafta", "🏆 Haftalik", ["hafta_2", "hafta_3"]),
    ("trade", "🔁 Trade va narx",
     ["narx_common", "narx_rare", "narx_epic", "narx_legendary", "narx_special", "narx_max",
      "trade_limit", "trade_muddat"]),
    ("sovga", "🎁 Sovga va ulashish",
     ["yangi_soat", "sovga_limit", "sovga_collector", "coin_limit"]),
    ("bozor", "🏪 Do'kon (savdo)",
     ["bozor_min", "bozor_min_col", "bozor_max", "bozor_limit"]),
    ("sandiq", "📦 Sandiq",
     ["quti_common", "quti_rare", "quti_epic", "quti_legendary",
      "qlimit_common", "qlimit_rare", "qlimit_epic", "qlimit_legendary"]),
]
SLOT_KALITLAR = ("s_w", "s_m", "s_s", "s_e", "s_j", "s_a", "s_b", "s_c")
CLAIM_KALITLAR = ("claim_common", "claim_rare", "claim_epic", "claim_legendary")
CHIQISH_KALITLAR = ("w_common", "w_rare", "w_epic", "w_legendary", "w_special")

# ---- 9 karta: har bir kartaning sovrini shu urinish narxining foizi.
# 200 = "2x" (narxning ikki baravari), qolganlari narxdan kam. Waifu kartasi SUPER beradi.
OYIN_FOIZLAR = [200, 10, 15, 20, 30, 35, 40, 50]
OYIN_DARAJA = "rare"

# ---- Bir martalik yangilash (v10): yangi narx pog'onasiga mos hamma raqam.
# Bazada saqlangan eski qiymatlar shu kalitlar uchun bir marta yangilanadi, keyin
# /panel dan o'zgartirganingiz saqlanib qoladi.
MIGR_NOMI = "migr_v10"
MIGR_KALITLAR = (
    "kunlik_bonus", "kunlik_qosh", "ruletka_limit", "ruletka_aralik", "ruletka_tanaffus",
    "ruletka_jekpot", "ruletka_uchta", "ruletka_ikkita", "referal_tanga", "claim_common", "claim_rare", "claim_epic", "claim_legendary",
    "slot_narx", "s_w", "s_m", "s_s", "s_e", "s_j", "s_a", "s_b", "s_c",
    "sov_j", "sov_a", "sov_b", "sov_c",
    "narx_common", "narx_rare", "narx_epic", "narx_legendary", "narx_special", "narx_max",
    "bozor_max", "bozor_limit",
    "quti_common", "quti_rare", "quti_epic", "quti_legendary",
)
_migr_tayyor = False

YANGILASH_ORALIGI = 15  # soniya
_qiymat = {}
_oxirgi = 0.0


def standart(kalit):
    return RO[kalit][0]


def ol(kalit):
    # Hozirgi qiymat (bazadan o'qilgan bo'lsa shu, bo'lmasa standart)
    v = _qiymat.get(kalit)
    return RO[kalit][0] if v is None else v


async def migratsiya(baza):
    # Bir marta: eski saqlangan qiymatlarni yangi standartga almashtiradi
    global _migr_tayyor
    if _migr_tayyor:
        return
    try:
        if await baza["sozlamalar"].find_one({"_id": MIGR_NOMI}) is None:
            await baza["sozlamalar"].update_one(
                {"_id": "panel"},
                {"$set": {k: RO[k][0] for k in MIGR_KALITLAR}},
                upsert=True,
            )
            await baza["sozlamalar"].update_one(
                {"_id": MIGR_NOMI}, {"$set": {"t": time.time()}}, upsert=True
            )
            logging.info("Sozlamalar yangi narx pog'onasiga o'tkazildi (v10)")
        _migr_tayyor = True
    except Exception as xato:
        logging.warning("Sozlamalarni yangilab bo'lmadi: %s", xato)


async def yangila(baza, majbur=False):
    # Bazadan o'qiydi, lekin har safar emas (har 15 soniyada)
    global _qiymat, _oxirgi
    hozir = time.time()
    if not majbur and hozir - _oxirgi < YANGILASH_ORALIGI:
        return
    _oxirgi = hozir
    await migratsiya(baza)
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
    # w/m/s/e = ULTRA/MEGA/SUPER/ELITA waifu (tanga 0), j/a/b/c = tanga sovrinlari
    w, m, s, e, j, a, b, c = (ol(k) for k in SLOT_KALITLAR)
    n = max(0, 100 - (w + m + s + e + j + a + b + c))
    return [
        ("w", w, 0), ("m", m, 0), ("s", s, 0), ("e", e, 0),
        ("j", j, ol("sov_j")), ("a", a, ol("sov_a")),
        ("b", b, ol("sov_b")), ("c", c, ol("sov_c")), ("n", n, 0),
    ]


def oyin_sovrinlar(narx):
    # 9 kartadagi tanga sovrinlari. 5 ga yaxlitlanadi; 100% dan kam bo'lganlari narxdan doim kam
    r = []
    for f in OYIN_FOIZLAR:
        v = max(5, round(narx * f / 100 / 5) * 5)
        if f < 100:
            v = min(v, narx - 5)
        r.append(v)
    return r


def oyin_narx(ishlatilgan):
    return ol("oyin_narx_bosh") + ol("oyin_narx_qadam") * ishlatilgan


DARAJA_NOM = (
    ("common", "ELITA"), ("rare", "SUPER"), ("epic", "MEGA"),
    ("legendary", "ULTRA"), ("special", "COLLECTOR"),
)


def iqtisod():
    # Hamma daromad manbalarining hozirgi sozlamalar bo'yicha hisobi (/iqtisod)
    narx = {k: ol("narx_" + k) for k, _ in DARAJA_NOM}
    # Kunlik bonus: 7 kunlik seriya
    hafta_bonus = sum(
        ol("kunlik_bonus") + ol("kunlik_qosh") * (min(i, ol("kunlik_seriya")) - 1)
        for i in range(1, 8)
    )
    # Ruletka: 64 holatdan 1 jekpot, 3 uchta bir xil, 36 ikkita bir xil
    rul_bir = (
        ol("ruletka_jekpot") + 3 * ol("ruletka_uchta") + 36 * ol("ruletka_ikkita")
    ) / 64
    # Ruletka: ketma-ket N ta urinish (har biri orasida aralik), keyin tanaffus
    partiya = max(ol("ruletka_limit"), 0)
    sikl = ol("ruletka_tanaffus") + max(partiya - 1, 0) * ol("ruletka_aralik") / 3600
    rul_soni_kun = partiya * (24 / sikl) if sikl > 0 else partiya * 24 * 3600 / max(ol("ruletka_aralik"), 1)
    rul_kun = rul_bir * rul_soni_kun
    # Slot: har bir aylantirish o'rtacha
    w, m, s_, e, j, a, b, c = (ol(k) for k in SLOT_KALITLAR)
    slot_waifu = (
        w * narx["legendary"] + m * narx["epic"] + s_ * narx["rare"] + e * narx["common"]
    ) / 100
    slot_tanga = (
        j * ol("sov_j") + a * ol("sov_a") + b * ol("sov_b") + c * ol("sov_c")
    ) / 100
    slot_jami = slot_waifu + slot_tanga
    slot_narx = ol("slot_narx")
    # 9 karta: har bir urinish
    oyin = []
    for i in range(ol("oyin_kunlik")):
        p = oyin_narx(i)
        ev = (sum(oyin_sovrinlar(p)) + narx[OYIN_DARAJA]) / 9
        oyin.append((p, ev))
    # /claim: kunlik waifuning o'rtacha qiymati
    vaznlar = [(k, ol("claim_" + k)) for k in ("common", "rare", "epic", "legendary")]
    jami_vazn = sum(v for _, v in vaznlar) or 1
    claim_ev = sum(narx[k] * v for k, v in vaznlar) / jami_vazn
    # Kunlik tanga (faqat tanga): bonus + ruletka + slotning tanga qismi
    tanga_kun = hafta_bonus / 7 + rul_kun + slot_tanga
    qiymat_kun = tanga_kun + slot_waifu
    kunlar = {k: (narx[k] / tanga_kun if tanga_kun > 0 else float("inf")) for k, _ in DARAJA_NOM}
    ogoh = []
    if slot_narx and slot_jami > slot_narx:
        ogoh.append(f"Slot o'yinchiga foydali: qaytim {slot_jami / slot_narx * 100:.0f}% (100% dan oshmasin)")
    for p, ev in oyin:
        if ev > p * 1.05:
            ogoh.append(f"9 karta {p} 🪙 urinishda qaytim {ev / p * 100:.0f}% (foydali)")
    mx = ol("bozor_max")
    for k in ("common", "rare", "epic", "legendary"):
        qutu = ol("quti_" + k)
        yuqori = narx[k] * (mx if mx > 0 else 1000) / 100
        if qutu < yuqori:
            ogoh.append(
                f"{dict(DARAJA_NOM)[k]} qutisi ({qutu}) do'kon eng baland narxidan ({int(yuqori)}) arzon: "
                "quti ochib sotib foyda qilish mumkin"
            )
    if mx <= 0:
        ogoh.append("Do'kon eng baland narxi cheksiz: oddiy waifu COLLECTOR narxida turishi mumkin")
    if narx["legendary"] >= narx["special"]:
        ogoh.append("COLLECTOR narxi ULTRA dan yuqori bo'lishi kerak")
    return {
        "narx": narx, "hafta_bonus": hafta_bonus, "rul_bir": rul_bir, "rul_kun": rul_kun, "rul_soni_kun": rul_soni_kun,
        "slot_waifu": slot_waifu, "slot_tanga": slot_tanga, "slot_jami": slot_jami,
        "slot_narx": slot_narx, "oyin": oyin, "claim_ev": claim_ev,
        "tanga_kun": tanga_kun, "qiymat_kun": qiymat_kun, "kunlar": kunlar, "ogoh": ogoh,
    }


def iqtisod_matni():
    d = iqtisod()
    n = d["narx"]
    t = ["📊 Iqtisod hisoboti (hozirgi sozlamalar)\n"]
    t.append("💰 Asosiy narxlar : " + " • ".join(f"{nom} {n[k]}" for k, nom in DARAJA_NOM))
    t.append("\n🪙 Kunlik daromad (har kuni hamma imkoniyatni ishlatsa):")
    t.append(f"• Kunlik bonus : {d['hafta_bonus'] / 7:.0f}  (haftada {d['hafta_bonus']})")
    t.append(f"• Ruletka : {d['rul_kun']:.0f}  (bir aylantirish {d['rul_bir']:.1f}, kuniga ~{d['rul_soni_kun']:.0f} ta)")
    t.append(f"• Bepul slot (tanga qismi) : {d['slot_tanga']:.0f}")
    t.append(f"➜ Jami tanga : {d['tanga_kun']:.0f} kuniga  (haftada {d['tanga_kun'] * 7:.0f})")
    t.append(f"• Bepul slotdagi waifu qiymati : {d['slot_waifu']:.0f}")
    t.append(f"• /claim waifusining o'rtacha qiymati : {d['claim_ev']:.0f}")
    t.append("\n⏳ Faqat tanga bilan nechta kunda yig'iladi:")
    for k, nom in DARAJA_NOM:
        kun = d["kunlar"][k]
        t.append(f"• {nom} ({n[k]}) : " + (f"{kun:.0f} kun" if kun != float("inf") else "yig'ib bo'lmaydi"))
    t.append(f"\n🎰 Slot : narx {d['slot_narx']}, o'rtacha qaytim {d['slot_jami']:.0f} "
             f"({(d['slot_jami'] / d['slot_narx'] * 100) if d['slot_narx'] else 0:.0f}%)")
    t.append("🃏 9 karta (urinish : o'rtacha qaytim) : " + " • ".join(
        f"{p} : {ev:.0f} ({ev / p * 100:.0f}%)" for p, ev in d["oyin"]
    ))
    if d["ogoh"]:
        t.append("\n⚠️ Ogohlantirishlar:")
        t += [f"• {x}" for x in d["ogoh"]]
    else:
        t.append("\n✅ Ogohlantirish yo'q")
    return "\n".join(t)


def vaqt_matni(soniya):
    # 5 soat 12 daqiqa ko'rinishida
    daq = max(1, int(soniya // 60) + (1 if soniya % 60 else 0))
    soat, daq = divmod(daq, 60)
    if soat and daq:
        return f"{soat} soat {daq} daqiqa"
    return f"{soat} soat" if soat else f"{daq} daqiqa"


async def yangi_qulf(baza, uid):
    # Yangi foydalanuvchi bo'lsa, cheklov tugashigacha qolgan soniya; aks holda 0.
    # Eski foydalanuvchilarda "qoshildi" yo'q, ular cheklanmaydi.
    soat = ol("yangi_soat")
    if soat <= 0:
        return 0
    try:
        u = await baza["users"].find_one({"_id": uid}) or {}
    except Exception as xato:
        logging.warning("Yangi foydalanuvchini tekshirib bo'lmadi: %s", xato)
        return 0
    t = u.get("qoshildi")
    if not isinstance(t, (int, float)):
        return 0
    return max(0, t + soat * 3600 - time.time())


_korilgan = set()


async def belgila(baza, uid):
    # Foydalanuvchi birinchi marta buyruq bergan vaqtni saqlaydi (faqat yangi hujjatga)
    if uid in _korilgan:
        return
    _korilgan.add(uid)
    try:
        # Waifusi bor odam eski o'yinchi (masalan, faqat guruhda topib o'ynagan): cheklanmaydi
        if await baza["collection"].find_one({"user_id": uid}) is not None:
            return
        await baza["users"].update_one(
            {"_id": uid}, {"$setOnInsert": {"qoshildi": time.time()}}, upsert=True
        )
    except Exception as xato:
        _korilgan.discard(uid)
        logging.warning("Qo'shilgan vaqtni yozib bo'lmadi: %s", xato)


async def _yangila_ishlovchi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        await yangila(_baza)
    except Exception as xato:
        logging.warning("Sozlamani yangilab bo'lmadi: %s", xato)
    # Faqat buyruq yoki tugma bosganlar: guruhda shunchaki yozganlar bazaga kirmaydi
    try:
        u = update.effective_user
        if u is None or u.is_bot:
            return
        m = update.message
        buyruq = bool(m and m.text and m.text.startswith("/")) or (
            update.callback_query is not None
        )
        if buyruq:
            await belgila(_baza, u.id)
    except Exception as xato:
        logging.warning("Foydalanuvchini belgilab bo'lmadi: %s", xato)


_baza = None


def ulash(ilova, baza):
    global _baza
    _baza = baza
    # Hamma ishlovchilardan oldin: sozlamalar doim yangi bo'ladi
    ilova.add_handler(TypeHandler(Update, _yangila_ishlovchi), group=-6)
