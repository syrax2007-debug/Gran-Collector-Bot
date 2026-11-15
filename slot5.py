import logging
import random
from datetime import datetime, timedelta, timezone
import sandiq
import sozlama as S

# Slot 5x3 : 5 baraban, 3 qator, 10 chiziq. Mini App'da "O'yin" bo'limida.
# Belgilar: 0 Sakura, 1 Dango, 2 Hanafuda, 3 ELITA, 4 SUPER, 5 MEGA (oddiy o'yin: tanga),
# 6 ULTRA, 7 COLLECTOR (faqat bonusda: waifu), 8 BONUS scatter (o'z belgisi)
TOSHKENT = timezone(timedelta(hours=5))
STAVKALAR = (50, 100, 250, 500)
VAZN = (30, 26, 20, 12, 8, 5, 0, 0, 4.0)
# Bonusda faqat waifu belgilari aylanadi (ELITA..COLLECTOR), daraja kamayib borgan sari kam tushadi
BVAZN = (0, 0, 0, 41, 26, 16, 11, 6, 0)
# 3, 4, 5 ta : chiziq stavkasiga (stavka / 10) ko'paytiriladi
TOLOV = {0: (7, 23, 86),
    1: (9, 29, 110),
    2: (13, 46, 185),
    3: (20, 92, 350),
    4: (31, 147, 649),
    5: (55, 279, 1852)}
# Bonus : 3 / 4 / 5+ scatter (🎁) -> bepul aylanishlar
BONUS_ASOS = (5, 8, 12)
BONUS_QOSH = {50: 0, 100: 1, 250: 2, 500: 3}
SCATTER = 8
BONUS_MAX = 2
BONUS_CHIZIQ = 5  # bonusda faol chiziqlar soni  # bitta aylanishda ko'pi bilan nechta waifu
CHIZIQLAR = ((1, 1, 1, 1, 1), (0, 0, 0, 0, 0), (2, 2, 2, 2, 2), (0, 1, 2, 1, 0), (2, 1, 0, 1, 2),
             (0, 0, 1, 2, 2), (2, 2, 1, 0, 0), (1, 0, 0, 0, 1), (1, 2, 2, 2, 1), (0, 1, 0, 1, 0))
DARAJA = {3: "common", 4: "rare", 5: "epic", 6: "legendary", 7: "special"}
NOM = {3: "ELITA", 4: "SUPER", 5: "MEGA", 6: "ULTRA", 7: "COLLECTOR"}


def bugun():
    return datetime.now(TOSHKENT).strftime("%Y-%m-%d")


def tuz(rng, vazn=None):
    return [rng.choices(range(9), weights=vazn or VAZN, k=5) for _ in range(3)]


def chiziqlar(g, stavka):
    # Oddiy chiziq yutuqlari. Natija: tanga, chiziqlar, yutgan kataklar, eng yaxshi belgi
    chiq = {"tanga": 0.0, "chiziq": [], "kataklar": {}, "eng": None}
    for li, ln in enumerate(CHIZIQLAR):
        birinchi = g[ln[0]][0]
        if birinchi > 5:
            continue
        n = 1
        while n < 5 and g[ln[n]][n] == birinchi:
            n += 1
        if n < 3:
            continue
        yutuq = TOLOV[birinchi][n - 3] * stavka / 10
        chiq["tanga"] += yutuq
        chiq["chiziq"].append({"li": li, "s": birinchi, "n": n, "yutuq": yutuq})
        for c in range(n):
            chiq["kataklar"][f"{ln[c]},{c}"] = "win"
        if chiq["eng"] is None or birinchi > chiq["eng"]:
            chiq["eng"] = birinchi
    return chiq


def scatterlar(g):
    return [f"{r},{c}" for r in range(3) for c in range(5) if g[r][c] == SCATTER]


def bonus_soni(scatter_soni, stavka):
    if scatter_soni < 3:
        return 0
    return BONUS_ASOS[min(scatter_soni, 5) - 3] + BONUS_QOSH.get(stavka, 0)


def bonus_aylanish(rng):
    # Bitta bonus aylanish: (g, kataklar, waifu belgilari). Faqat chiziqdagi 3+ bir xil waifu belgisi sovrin
    g = tuz(rng, BVAZN)
    kat, belgilar = {}, []
    for ln in CHIZIQLAR[:BONUS_CHIZIQ]:
        birinchi = g[ln[0]][0]
        n = 1
        while n < 5 and g[ln[n]][n] == birinchi:
            n += 1
        if n < 3:
            continue
        belgilar.append(birinchi)
        for c in range(n):
            kat[f"{ln[c]},{c}"] = "win"
    # Bir aylanishda bir xil belgi uchun bitta waifu, eng yuqori daraja birinchi
    bor = sorted(set(belgilar), reverse=True)
    return g, kat, bor[:BONUS_MAX]


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
        g = tuz(rng)
        ch = chiziqlar(g, stavka)
        sc = scatterlar(g)
        for j in sc:
            ch["kataklar"][j] = "sc"
        # Tanga faqat oddiy o'yindagi chiziqlardan
        jami = int(round(ch["tanga"]))
        bonus = None
        waifular = []
        n = bonus_soni(len(sc), stavka)
        if n:
            ruxsat = stavka >= S.ol("slot5_waifu_min")
            spinlar = []
            for _ in range(n):
                bg, kat, daraja = bonus_aylanish(rng)
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
        "g": g, "res": ch, "tanga": jami, "coins": u.get("coins", 0),
        "bonus": bonus, "waifular": waifular,
    }
