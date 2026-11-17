import logging
import random
from datetime import datetime, timedelta, timezone
import sandiq
import sozlama as S

# Slot 5x3 : 5 baraban, 3 qator, 10 chiziq. Mini App'da "O'yin" bo'limida.
# Belgilar: 0 Sakura, 1 Dango, 2 Hanafuda, 3 ELITA, 4 SUPER, 5 MEGA (oddiy o'yin: tanga),
# 6 ULTRA, 7 COLLECTOR (faqat waifu bonusida), 8 BONUS scatter, 9 WILD (hamma joyda),
# 10 TANGA (💰, tanga yig'ish bonusi uchun)
#
# Rejimlar (stavkaga qarab):
#   50 / 100  : tanga bonusi (6+ ta 💰), waifu scatter yo'q
#   250 / 500 : waifu bonusi (3+ ta 🎁), 💰 yo'q
#   1000      : ikkalasi ham
TOSHKENT = timezone(timedelta(hours=5))
STAVKALAR = (50, 100, 250, 500, 1000)
TANGA_BONUS = (50, 100, 1000)
WAIFU_BONUS = (250, 500, 1000)
SCATTER, WILD, TANGA = 8, 9, 10

TANGA_VAZN = 17
SC_VAZN = 4.0
WILD_VAZN = 4.0
ASOS = (28, 24, 19, 11, 7, 4.5)

# 3, 4, 5 ta : chiziq stavkasiga (stavka / 10) ko'paytiriladi
TOLOV = {0: (7, 23, 86), 1: (9, 29, 110), 2: (13, 46, 185),
         3: (20, 92, 350), 4: (31, 147, 649), 5: (55, 279, 1852)}
# Har stavka uchun tanga qaytimini sozlovchi koeffitsient (sim bilan hisoblangan)
KOEF = {50: 0.713, 100: 0.713, 250: 0.456, 500: 0.521, 1000: 0.778}

# Waifu bonusi
BONUS_ASOS = (5, 8, 12)
BONUS_QOSH = {250: 2, 500: 3, 1000: 5}
BONUS_MAX = 2
BONUS_CHIZIQ = 5
BVAZN = (0, 0, 0, 41, 26, 16, 11, 6, 0, 5, 0)
BVAZN_1000 = (0, 0, 0, 37, 26, 17, 12, 7, 0, 5, 0)

# Tanga yig'ish bonusi (Hold & Spin)
TB_QAYTA = 3          # har yangi 💰 dan keyin qayta aylanishlar
TB_EHTIMOL = 0.06    # bo'sh katakka 💰 tushish ehtimoli (har qayta aylanishda)
TB_TOLA_X = 5         # barcha 15 katak to'lsa : jami yutuq shuncha marta
# 💰 qiymatlari: (stavkaga ko'paytma, og'irlik) va jekpotlar
TB_QIYMAT = ((0.5, 32), (1, 30), (2, 15), (3, 8), (5, 4), (10, 1.5))
TB_JEKPOT = (("ELITA", "common", 0.6), ("SUPER", "rare", 0.3),
             ("MEGA", "epic", 0.1), ("ULTRA", "legendary", 0.03))

CHIZIQLAR = ((1, 1, 1, 1, 1), (0, 0, 0, 0, 0), (2, 2, 2, 2, 2), (0, 1, 2, 1, 0), (2, 1, 0, 1, 2),
             (0, 0, 1, 2, 2), (2, 2, 1, 0, 0), (1, 0, 0, 0, 1), (1, 2, 2, 2, 1), (0, 1, 0, 1, 0))
DARAJA = {3: "common", 4: "rare", 5: "epic", 6: "legendary", 7: "special"}
NOM = {3: "ELITA", 4: "SUPER", 5: "MEGA", 6: "ULTRA", 7: "COLLECTOR"}


def bugun():
    return datetime.now(TOSHKENT).strftime("%Y-%m-%d")


def vazn(stavka):
    # Oddiy o'yin belgilari og'irligi (11 ta)
    return ASOS + (0, 0,
                   SC_VAZN if stavka in WAIFU_BONUS else 0, WILD_VAZN,
                   TANGA_VAZN if stavka in TANGA_BONUS else 0)


def tuz(rng, w):
    return [rng.choices(range(11), weights=w, k=5) for _ in range(3)]


def chiziqlar(g, stavka, bonus=False):
    # Chiziq yutuqlari, WILD (9) belgilar o'rnini bosadi.
    # Oddiy o'yin: 0..5 uchun tanga. Bonus: 3..7 uchun waifu (WILD faqat 3..5 o'rnini bosadi)
    chiq = {"tanga": 0.0, "chiziq": [], "kataklar": {}, "eng": None}
    eng_son = 7 if bonus else 5
    kam = 3 if bonus else 0
    wild_max = 5
    k = KOEF.get(stavka, 1.0)
    for li, ln in enumerate(CHIZIQLAR):
        # chiziqdagi birinchi WILD bo'lmagan belgi
        belgi = None
        for c in range(5):
            x = g[ln[c]][c]
            if x != WILD:
                belgi = x
                break
        if belgi is None:
            belgi = eng_son if not bonus else 5  # hammasi WILD : eng yuqori oddiy belgi
        if belgi < kam or belgi > eng_son:
            continue
        n = 0
        while n < 5:
            x = g[ln[n]][n]
            if x == belgi or (x == WILD and belgi <= wild_max):
                n += 1
            else:
                break
        if n < 3:
            continue
        if bonus:
            yutuq = 0
        else:
            yutuq = TOLOV[belgi][n - 3] * stavka / 10 * k
        chiq["tanga"] += yutuq
        chiq["chiziq"].append({"li": li, "s": belgi, "n": n, "yutuq": yutuq})
        for c in range(n):
            chiq["kataklar"][f"{ln[c]},{c}"] = "win"
        if chiq["eng"] is None or belgi > chiq["eng"]:
            chiq["eng"] = belgi
    return chiq


def belgilar(g, x):
    return [f"{r},{c}" for r in range(3) for c in range(5) if g[r][c] == x]


def scatterlar(g):
    return belgilar(g, SCATTER)


def bonus_soni(scatter_soni, stavka):
    if scatter_soni < 3 or stavka not in WAIFU_BONUS:
        return 0
    return BONUS_ASOS[min(scatter_soni, 5) - 3] + BONUS_QOSH.get(stavka, 0)


def bonus_aylanish(rng, stavka=250):
    # Bitta waifu bonus aylanish: (g, kataklar, waifu belgilari)
    g = tuz(rng, BVAZN_1000 if stavka == 1000 else BVAZN)
    ch = chiziqlar(g, 10, bonus=True)
    kat = dict(ch["kataklar"])
    # Bonusda faqat dastlabki BONUS_CHIZIQ ta chiziq faol
    kat, bor = {}, set()
    for li, ln in enumerate(CHIZIQLAR[:BONUS_CHIZIQ]):
        for q in ch["chiziq"]:
            if q["li"] == li:
                bor.add(q["s"])
                for c in range(q["n"]):
                    kat[f"{ln[c]},{c}"] = "win"
    return g, kat, sorted(bor, reverse=True)[:BONUS_MAX]


def jekpot_summa(daraja, stavka):
    # Jekpot = waifu narxi (stavka 100 da), stavkaga mutanosib; panel foizi bilan
    return int(round(S.ol("narx_" + daraja) * stavka / 100 * S.ol("slot5_jekpot_foiz") / 100))


def tanga_qiymat(rng, stavka):
    # Bitta 💰 qiymati: {"v": tanga, "jp": jekpot nomi yoki None}
    ro = [(("x", m), w) for m, w in TB_QIYMAT] + [(("jp", n, d), w) for n, d, w in TB_JEKPOT]
    t = rng.choices([x for x, _ in ro], weights=[w for _, w in ro], k=1)[0]
    if t[0] == "x":
        return {"v": int(round(t[1] * stavka)), "jp": None}
    return {"v": jekpot_summa(t[2], stavka), "jp": t[1]}


def tanga_bonusi(rng, g, stavka):
    # Hold & Spin. Boshlang'ich 💰 lar qotadi, 3 ta qayta aylanish;
    # yangi 💰 tushsa qayta aylanishlar yana 3 ga qaytadi.
    qot = {}
    boshi = []
    for r in range(3):
        for c in range(5):
            if g[r][c] == TANGA:
                q = tanga_qiymat(rng, stavka)
                qot[(r, c)] = q
                boshi.append({"r": r, "c": c, **q})
    qadamlar = []
    qoldi = TB_QAYTA
    while qoldi > 0 and len(qot) < 15:
        yangi = []
        for r in range(3):
            for c in range(5):
                if (r, c) not in qot and rng.random() < TB_EHTIMOL:
                    q = tanga_qiymat(rng, stavka)
                    qot[(r, c)] = q
                    yangi.append({"r": r, "c": c, **q})
        qadamlar.append(yangi)
        qoldi = TB_QAYTA if yangi else qoldi - 1
    tola = len(qot) == 15
    jami = sum(q["v"] for q in qot.values())
    if tola:
        jami *= TB_TOLA_X
    return {"boshi": boshi, "qadamlar": qadamlar, "tola": tola, "x": TB_TOLA_X if tola else 1,
            "jami": jami, "soni": len(qot)}


async def oyna(baza, uid, stavka, rng=None):
    # (kod, malumot). kod: ok, stavka, tanga_yetmaydi, limit, xato
    if stavka not in STAVKALAR:
        return "stavka", {}
    rng = rng or random.SystemRandom()
    users = baza["users"]
    b = bugun()
    lim = S.ol("slot5_kunlik")
    await users.update_one(
        {"_id": uid, "s5_sana": {"$ne": b}}, {"$set": {"s5_sana": b, "s5_soni": 0}}
    )
    r = await users.update_one(
        {"_id": uid, "coins": {"$gte": stavka}, "s5_sana": b,
         "s5_soni": {"$lt": lim if lim > 0 else 10 ** 9}},
        {"$inc": {"coins": -stavka, "s5_soni": 1}},
    )
    if r.modified_count == 0:
        u = await users.find_one({"_id": uid}) or {}
        if lim > 0 and u.get("s5_soni", 0) >= lim:
            return "limit", {"limit": lim}
        if u.get("coins", 0) < stavka:
            return "tanga_yetmaydi", {"coins": u.get("coins", 0)}
        return "xato", {}
    try:
        g = tuz(rng, vazn(stavka))
        ch = chiziqlar(g, stavka)
        sc = scatterlar(g)
        for j in sc:
            ch["kataklar"][j] = "sc"
        chiziq_tanga = int(round(ch["tanga"]))
        jami = chiziq_tanga
        # Tanga yig'ish bonusi
        tb = None
        tanga_kat = belgilar(g, TANGA)
        if stavka in TANGA_BONUS and len(tanga_kat) >= 6:
            tb = tanga_bonusi(rng, g, stavka)
            jami += tb["jami"]
        # Waifu bonusi
        bonus = None
        waifular = []
        n = bonus_soni(len(sc), stavka)
        if n:
            ruxsat = stavka >= S.ol("slot5_waifu_min")
            spinlar = []
            for _ in range(n):
                bg, kat, daraja = bonus_aylanish(rng, stavka)
                spin = {"g": bg, "kataklar": kat, "waifular": []}
                for belgi in daraja:
                    soni = await baza["characters"].count_documents(sandiq.shart(DARAJA[belgi]))
                    if not ruxsat or soni == 0:
                        # Waifu berilmaydi yoki bu darajada yo'q: narxiga teng tanga
                        q = S.ol("narx_" + DARAJA[belgi])
                        jami += q
                        spin["waifular"].append({"belgi": belgi, "p": None, "tanga": q})
                        continue
                    p = await baza["characters"].find_one(
                        sandiq.shart(DARAJA[belgi]), skip=rng.randrange(soni)
                    )
                    await baza["collection"].insert_one({"user_id": uid, "char_id": p["_id"]})
                    spin["waifular"].append({"belgi": belgi, "p": p, "tanga": 0})
                    waifular.append({"belgi": belgi, "p": p})
                spinlar.append(spin)
            bonus = {"soni": n, "scatter": len(sc), "spinlar": spinlar, "ruxsat": ruxsat}
        if jami:
            await users.update_one({"_id": uid}, {"$inc": {"coins": jami}})
    except Exception as xato:
        logging.warning("Slot 5x3 xatosi, stavka qaytarildi: %s", xato)
        await users.update_one({"_id": uid}, {"$inc": {"coins": stavka, "s5_soni": -1}})
        return "xato", {}
    u = await users.find_one({"_id": uid}) or {}
    return "ok", {
        "g": g, "res": ch, "chiziq_tanga": chiziq_tanga, "tanga": jami, "coins": u.get("coins", 0),
        "bonus": bonus, "tb": tb, "waifular": waifular,
    }
