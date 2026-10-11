import asyncio
import html
from pymongo import ReturnDocument

# Daraja emojilari (xohlagancha almashtiring)
DARAJA_EMOJI = {
    "common": "🍀",
    "rare": "💎",
    "epic": "🔮",
    "legendary": "👑",
    "special": "💠",
}
MAKS_XABAR = 6  # kolleksiya ko'pi bilan shuncha xabarga bo'linadi

_qulf = asyncio.Lock()


def manba_kalit(s):
    # Bo'sh joy va harf farqini hisobga olmaydi
    return " ".join(str(s).split()).casefold()


async def keyingi_raqam(baza):
    d = await baza["counters"].find_one_and_update(
        {"_id": "personaj"},
        {"$inc": {"n": 1}},
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )
    return d["n"]


async def raqam_tuzat(baza):
    # Raqami yo'q personajlarga yuklangan tartibida raqam beradi
    personajlar = baza["characters"]
    if await personajlar.find_one({"raqam": {"$exists": False}}) is None:
        return
    async with _qulf:
        yetishmaydi = [
            p["_id"]
            async for p in personajlar.find(
                {"raqam": {"$exists": False}}, {"_id": 1}
            ).sort("_id", 1)
        ]
        for pid in yetishmaydi:
            n = await keyingi_raqam(baza)
            await personajlar.update_one(
                {"_id": pid, "raqam": {"$exists": False}},
                {"$set": {"raqam": n}},
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
