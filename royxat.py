import asyncio
import html
import random

# Daraja emojilari (xohlagancha almashtiring)
DARAJA_EMOJI = {
    "common": "💠",  # ELITA
    "rare": "🌟",  # SUPER
    "epic": "💎",  # MEGA
    "legendary": "🔥",  # ULTRA
    "special": "⛩️",  # COLLECTOR
    "max": "👑",  # MAX
}
MAKS_XABAR = 6  # kolleksiya ko'pi bilan shuncha xabarga bo'linadi
RAQAM_MIN = 100
RAQAM_MAX = 9999

_qulf = asyncio.Lock()


def manba_kalit(s):
    # Bo'sh joy va harf farqini hisobga olmaydi
    return " ".join(str(s).split()).casefold()


async def keyingi_raqam(baza):
    # 100 dan 9999 gacha tasodifiy, band bo'lmagan raqam
    personajlar = baza["characters"]
    for _ in range(100):
        n = random.randint(RAQAM_MIN, RAQAM_MAX)
        if await personajlar.find_one({"raqam": n}, {"_id": 1}) is None:
            return n
    # Deyarli to'lgan bo'lsa: bo'sh raqamlarni topamiz
    band = {
        d["raqam"]
        async for d in personajlar.find(
            {"raqam": {"$gte": RAQAM_MIN, "$lte": RAQAM_MAX}}, {"raqam": 1}
        )
    }
    bosh = [x for x in range(RAQAM_MIN, RAQAM_MAX + 1) if x not in band]
    if bosh:
        return random.choice(bosh)
    # Hammasi band bo'lsa, oxirgisidan davom etamiz
    oxirgi = await personajlar.find_one({}, sort=[("raqam", -1)])
    if oxirgi and "raqam" in oxirgi:
        return oxirgi["raqam"] + 1
    return RAQAM_MAX + 1


async def raqam_tuzat(baza):
    # Raqami yo'q yoki 100 dan kichik (eski ketma-ket) personajlarga
    # tasodifiy raqam beradi
    personajlar = baza["characters"]
    shart = {
        "$or": [
            {"raqam": {"$exists": False}},
            {"raqam": {"$lt": RAQAM_MIN}},
        ]
    }
    if await personajlar.find_one(shart, {"_id": 1}) is None:
        return
    async with _qulf:
        yetishmaydi = [
            p["_id"]
            async for p in personajlar.find(shart, {"_id": 1}).sort("_id", 1)
        ]
        for pid in yetishmaydi:
            n = await keyingi_raqam(baza)
            await personajlar.update_one(
                {"_id": pid}, {"$set": {"raqam": n}}
            )


async def guruhlar_tuz(baza, sanash, royxat):
    # Manba bo'yicha guruhlaydi: [(sarlavha, [qatorlar]), ...]
    jami = {}
    async for d in baza["characters"].find({}, {"anime": 1}):
        k = manba_kalit(d.get("anime", ""))
        jami[k] = jami.get(k, 0) + 1

    gruppalar = {}
    for p in royxat:
        k = manba_kalit(p.get("anime", ""))
        nom = " ".join(str(p.get("anime", "")).split()) or "Boshqa"
        g = gruppalar.setdefault(k, {"nom": nom, "royxat": []})
        g["royxat"].append(p)

    natija = []
    for k in sorted(gruppalar):
        g = gruppalar[k]
        g["royxat"].sort(key=lambda p: p.get("raqam", 0))
        sarlavha = (
            f"{html.escape(g['nom'])} "
            f"[{len(g['royxat'])}/{jami.get(k, len(g['royxat']))}]"
        )
        qatorlar = []
        for p in g["royxat"]:
            belgi = DARAJA_EMOJI.get(str(p.get("rarity", "")).lower(), "🔸")
            qatorlar.append(
                f"⤷〔{belgi}〕 {p.get('raqam', '?')} "
                f"{html.escape(str(p['name']))} ×{sanash[p['_id']]}"
            )
        natija.append((sarlavha, qatorlar))
    return natija


def qismlarga_bol(guruhlar, maks=3500):
    # Uzun ro'yxatni bir nechta xabarga bo'ladi
    qismlar = []
    joriy = ""
    for sarlavha, qatorlar in guruhlar:
        boshi = f"➤ {sarlavha}\n"
        yangi_blok = True
        for q in qatorlar:
            kerak = (boshi if yangi_blok else "") + q + "\n"
            ajratgich = "\n" if (joriy and yangi_blok) else ""
            if joriy and len(joriy) + len(ajratgich) + len(kerak) > maks:
                qismlar.append(joriy.rstrip())
                joriy = ""
                kerak = boshi + q + "\n"
                ajratgich = ""
            joriy += ajratgich + kerak
            yangi_blok = False
    if joriy:
        qismlar.append(joriy.rstrip())
    return qismlar

#yangi joy
async def kolleksiya_malumot(baza, user_id, maks=800):
    # Foydalanuvchi kolleksiyasini sahifalarga bo'lib beradi
    idlar = [
        d["char_id"]
        async for d in baza["collection"].find({"user_id": user_id})
    ]
    if not idlar:
        return None
    await raqam_tuzat(baza)
    sanash = {}
    for pid in idlar:
        sanash[pid] = sanash.get(pid, 0) + 1
    royxat = [
        p
        async for p in baza["characters"].find({"_id": {"$in": list(sanash)}})
    ]
    guruhlar = await guruhlar_tuz(baza, sanash, royxat)
    return {
        "jami": len(idlar),
        "royxat": royxat,
        "qismlar": qismlarga_bol(guruhlar, maks),
    }


def kolleksiya_izohi(ism, jami, qismlar, sahifa):
    # Rasm izohi: sarlavha + sahifa matni + sahifa raqami
    matn = (
        "✨━ ━━━━━━━━ ━✨\n"
        f"🫧 {html.escape(ism)} kolleksiyasi |🧧 Jami : {jami} ta Waifu!\n\n"
        + qismlar[sahifa]
    )
    if len(qismlar) > 1:
        matn += f"\n\n📄 {sahifa + 1}/{len(qismlar)}"
    return matn
