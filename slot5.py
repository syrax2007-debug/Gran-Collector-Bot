import logging
import random
from datetime import datetime, timedelta, timezone
import sandiq
import sozlama as S

# Slot 5x3 : 5 baraban, 3 qator, 10 chiziq. Mini App'da "O'yin" bo'limida.
# Belgilar: 0 Sakura, 1 Dango, 2 Hanafuda, 3 ELITA, 4 SUPER, 5 MEGA, 6 ULTRA (scatter), 7 COLLECTOR (scatter)
TOSHKENT = timezone(timedelta(hours=5))
STAVKALAR = (50, 100, 250, 500)
VAZN = (24, 21, 18, 15, 11, 8, 1.15, 0.53)
# 3, 4, 5 ta : chiziq stavkasiga (stavka / 10) ko'paytiriladi
TOLOV = {0: (10, 30, 100), 1: (12, 38, 145), 2: (15, 58, 240),
         3: (19, 96, 380), 4: (29, 145, 670), 5: (48, 290, 1900)}
# Scatter : umumiy stavkaga ko'paytiriladi (3, 4, 5 ta)
SCATTER = {6: (10, 30, 100), 7: (30, 100, 500)}
CHIZIQLAR = ((1, 1, 1, 1, 1), (0, 0, 0, 0, 0), (2, 2, 2, 2, 2), (0, 1, 2, 1, 0), (2, 1, 0, 1, 2),
             (0, 0, 1, 2, 2), (2, 2, 1, 0, 0), (1, 0, 0, 0, 1), (1, 2, 2, 2, 1), (0, 1, 0, 1, 0))
DARAJA = {3: "common", 4: "rare", 5: "epic", 6: "legendary", 7: "special"}
NOM = {3: "ELITA", 4: "SUPER", 5: "MEGA", 6: "ULTRA", 7: "COLLECTOR"}


def bugun():
    return datetime.now(TOSHKENT).strftime("%Y-%m-%d")


def tuz(rng):
    return [rng.choices(range(8), weights=VAZN, k=5) for _ in range(3)]


def baholash(g, stavka):
    # g[qator][ustun]. Natija: tanga, chiziqlar, scatterlar, waifu belgilari, yutgan kataklar
    chiq = {"tanga": 0.0, "chiziq": [], "scatter": [], "waifu": [], "kataklar": {}}
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
        if (n == 5 and birinchi in (3, 4)) or (n >= 4 and birinchi == 5):
            chiq["waifu"].append(birinchi)
    for s in (6, 7):
        joylar = [f"{r},{c}" for r in range(3) for c in range(5) if g[r][c] == s]
        if len(joylar) >= 3:
            yutuq = SCATTER[s][min(len(joylar), 5) - 3] * stavka
            chiq["tanga"] += yutuq
            chiq["scatter"].append({"s": s, "soni": len(joylar), "yutuq": yutuq})
            for j in joylar:
                chiq["kataklar"][j] = "sc"
            chiq["waifu"].append(s)
    return chiq


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
        res = baholash(g, stavka)
        waifular, qoshimcha = [], 0
        ruxsat = stavka >= S.ol("slot5_waifu_min")
        for belgi in res["waifu"]:
            if not ruxsat:
                continue
            soni = await baza["characters"].count_documents(sandiq.shart(DARAJA[belgi]))
            if soni == 0:
                # Bu darajada waifu yo'q: narxiga teng tanga beriladi
                qoshimcha += S.ol("narx_" + DARAJA[belgi])
                continue
            p = await baza["characters"].find_one(
                sandiq.shart(DARAJA[belgi]), skip=rng.randrange(soni)
            )
            await baza["collection"].insert_one({"user_id": uid, "char_id": p["_id"]})
            waifular.append({"belgi": belgi, "p": p})
        jami = int(round(res["tanga"])) + qoshimcha
        if jami:
            await users.update_one({"_id": uid}, {"$inc": {"coins": jami}})
    except Exception as xato:
        logging.warning("Slot 5x3 xatosi, stavka qaytarildi: %s", xato)
        await users.update_one({"_id": uid}, {"$inc": {"coins": stavka, "s5_soni": -1}})
        return "xato", {}
    u = await users.find_one({"_id": uid}) or {}
    return "ok", {
        "g": g, "res": res, "waifular": waifular, "tanga": jami,
        "coins": u.get("coins", 0), "ruxsat": ruxsat,
    }
