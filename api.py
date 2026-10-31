import os
import hmac
import json
import time
import random
import hashlib
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qsl
from aiohttp import web, ClientSession
from bson import ObjectId
from pymongo import AsyncMongoClient
from main import ilova as telegram_bot
import haftalik
import sozlama as S

BOT_TOKEN = os.environ["BOT_TOKEN"]
MONGO_URI = os.environ["MONGO_URI"]
# Mini App sahifasi turgan manzil (faqat shu sayt API'dan foydalana oladi)
RUXSAT_ETILGAN = os.environ.get(
    "ALLOWED_ORIGIN", "https://syrax2007-debug.github.io"
)
TOSHKENT = timezone(timedelta(hours=5))

# ---------- O'yin sozlamalari ----------
# Hamma raqam /panel dan o'zgartiriladi (sozlama.py). Sovrinlar shu urinish narxining foizi
OYIN_FOIZLAR = [20, 30, 40, 50, 60, 70, 80, 90]


def oyin_narx(ishlatilgan):
    # ishlatilgan = bugun nechta urinish bo'lgan; shu urinish narxi
    return S.ol("oyin_narx_bosh") + S.ol("oyin_narx_qadam") * ishlatilgan


def oyin_sovrinlar(narx):
    # 5 ga yaxlitlaymiz, doim narxdan kam
    return [min(narx - 5, max(5, round(narx * f / 100 / 5) * 5)) for f in OYIN_FOIZLAR]


# ---------- Slot sozlamalari ----------
# Faqat 3 ta bir xil belgi tushsa sovrin beriladi. Ehtimol va sovrinlar /panel da
# "w" = ULTRA waifu, "n" = belgilar mos kelmadi
SLOT_BELGILAR = ["w", "j", "a", "b", "c"]
SLOT_DARAJA = "legendary"  # ULTRA


def bugun():
    return datetime.now(TOSHKENT).strftime("%Y-%m-%d")


def bot_nomi():
    try:
        return telegram_bot.bot.username
    except Exception:
        return os.environ.get("BOT_USERNAME", "")


def tekshir(init_data):
    # Telegram yuborgan ma'lumot haqiqiyligini tekshiradi
    juftlar = dict(parse_qsl(init_data, keep_blank_values=True))
    olingan = juftlar.pop("hash", None)
    if not olingan or "user" not in juftlar:
        return None
    matn = "\n".join(f"{k}={v}" for k, v in sorted(juftlar.items()))
    kalit = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
    hisob = hmac.new(kalit, matn.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(hisob, olingan):
        return None
    if time.time() - int(juftlar.get("auth_date", "0")) > 86400:
        return None
    return json.loads(juftlar["user"])


@web.middleware
async def cors(request, handler):
    if request.method == "OPTIONS":
        javob = web.Response(status=204)
    else:
        try:
            javob = await handler(request)
        except web.HTTPException as xato:
            javob = xato
    javob.headers["Access-Control-Allow-Origin"] = RUXSAT_ETILGAN
    javob.headers["Access-Control-Allow-Headers"] = "X-Init-Data, Content-Type"
    javob.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return javob


def kartochka_json(p):
    return {
        "id": str(p["_id"]),
        "name": p["name"],
        "anime": p["anime"],
        "rarity": p["rarity"],
        "raqam": p.get("raqam"),
        "image": f"/api/photo/{p['_id']}",
    }


def slot_holat(u, tolangan):
    # bepul: kuniga 1 ta; bonus: har bir to'langan referal uchun 1 ta, kuniga ko'pi bilan 1 ta
    b = bugun()
    bepul = u.get("slot_sana") != b
    jami = u.get("slot_bonus_jami", 0)
    if u.get("slot_bonus_sana") == b:
        bonus = "ishlatildi"
    elif tolangan > jami:
        bonus = "bor"
    else:
        bonus = "qulf"
    pullik = "ishlatildi" if u.get("slot_pullik_sana") == b else "bor"
    return {"free": bepul, "bonus": bonus, "pullik": pullik, "narx": S.ol("slot_narx")}


async def tolangan_soni(baza, uid):
    return await baza["users"].count_documents(
        {"referrer": uid, "ref_tolangan": True}
    )


async def foydalanuvchi_ol(baza, f):
    await baza["users"].update_one(
        {"_id": f["id"]},
        {"$set": {"name": f.get("first_name", "")}},
        upsert=True,
    )
    return await baza["users"].find_one({"_id": f["id"]})


async def bosh(request):
    return web.Response(text="OK")


async def kolleksiya_api(request):
    f = tekshir(request.headers.get("X-Init-Data", ""))
    if not f:
        raise web.HTTPUnauthorized(text="Ruxsat yo'q")
    baza = request.app["baza"]
    sanash = {}
    async for d in baza["collection"].find({"user_id": f["id"]}):
        sanash[d["char_id"]] = sanash.get(d["char_id"], 0) + 1
    royxat = []
    async for p in baza["characters"].find({"_id": {"$in": list(sanash)}}):
        x = kartochka_json(p)
        x["count"] = sanash[p["_id"]]
        royxat.append(x)
    return web.json_response(royxat)


async def rasm(request):
    try:
        oid = ObjectId(request.match_info["pid"])
    except Exception:
        raise web.HTTPNotFound()
    p = await request.app["baza"]["characters"].find_one({"_id": oid})
    if not p:
        raise web.HTTPNotFound()
    sess = request.app["sess"]
    async with sess.get(
        f"https://api.telegram.org/bot{BOT_TOKEN}/getFile",
        params={"file_id": p["file_id"]},
    ) as r:
        data = await r.json()
    if not data.get("ok"):
        raise web.HTTPNotFound()
    yol = data["result"]["file_path"]
    async with sess.get(
        f"https://api.telegram.org/file/bot{BOT_TOKEN}/{yol}"
    ) as r:
        baytlar = await r.read()
    return web.Response(
        body=baytlar,
        content_type="image/jpeg",
        headers={"Cache-Control": "public, max-age=86400"},
    )


async def me_api(request):
    f = tekshir(request.headers.get("X-Init-Data", ""))
    if not f:
        raise web.HTTPUnauthorized(text="Ruxsat yo'q")
    baza = request.app["baza"]
    await S.yangila(baza)
    u = await foydalanuvchi_ol(baza, f)
    ishlatilgan = u.get("oyin_soni", 0) if u.get("oyin_sana") == bugun() else 0

    sevimli = None
    if u.get("sevimli"):
        bor = await baza["collection"].find_one(
            {"user_id": f["id"], "char_id": u["sevimli"]}
        )
        p = (
            await baza["characters"].find_one({"_id": u["sevimli"]})
            if bor else None
        )
        if p:
            sevimli = kartochka_json(p)
        else:
            await baza["users"].update_one(
                {"_id": f["id"]}, {"$unset": {"sevimli": ""}}
            )

    users = baza["users"]
    tolangan = await users.count_documents(
        {"referrer": f["id"], "ref_tolangan": True}
    )
    kutilmoqda = await users.count_documents(
        {"referrer": f["id"], "ref_tolangan": {"$ne": True}}
    )
    nom = bot_nomi()
    return web.json_response({
        "coins": u.get("coins", 0),
        "free": False,
        "qolgan": max(S.ol("oyin_kunlik") - ishlatilgan, 0),
        "limit": S.ol("oyin_kunlik"),
        "replay_cost": oyin_narx(ishlatilgan),
        "sevimli": sevimli,
        "ref_link": f"https://t.me/{nom}?start=ref_{f['id']}" if nom else "",
        "ref_tolangan": tolangan,
        "ref_kutilmoqda": kutilmoqda,
        "ref_tanga": S.ol("referal_tanga"),
        "slot": slot_holat(u, tolangan),
    })


async def sevimli_api(request):
    f = tekshir(request.headers.get("X-Init-Data", ""))
    if not f:
        raise web.HTTPUnauthorized(text="Ruxsat yo'q")
    try:
        data = await request.json()
    except Exception:
        raise web.HTTPBadRequest(text="JSON kerak")
    baza = request.app["baza"]
    await foydalanuvchi_ol(baza, f)
    pid = data.get("id")
    if not pid:
        await baza["users"].update_one(
            {"_id": f["id"]}, {"$unset": {"sevimli": ""}}
        )
        return web.json_response({"sevimli": None})
    try:
        oid = ObjectId(pid)
    except Exception:
        raise web.HTTPBadRequest(text="id xato")
    bor = await baza["collection"].find_one(
        {"user_id": f["id"], "char_id": oid}
    )
    if not bor:
        raise web.HTTPForbidden(text="Bu waifu sizda yo'q")
    p = await baza["characters"].find_one({"_id": oid})
    if not p:
        raise web.HTTPNotFound(text="Topilmadi")
    await baza["users"].update_one(
        {"_id": f["id"]}, {"$set": {"sevimli": oid}}
    )
    return web.json_response({"sevimli": kartochka_json(p)})


async def oyin_api(request):
    f = tekshir(request.headers.get("X-Init-Data", ""))
    if not f:
        raise web.HTTPUnauthorized(text="Ruxsat yo'q")
    try:
        tanlov = int((await request.json()).get("pick"))
    except Exception:
        raise web.HTTPBadRequest(text="pick kerak")
    if not 0 <= tanlov <= 8:
        raise web.HTTPBadRequest(text="pick xato")

    baza = request.app["baza"]
    await S.yangila(baza)
    users = baza["users"]
    uid = f["id"]
    u = await foydalanuvchi_ol(baza, f)
    b = bugun()

    if u.get("oyin_sana") != b:
        await users.update_one(
            {"_id": uid}, {"$set": {"oyin_sana": b, "oyin_soni": 0}}
        )
        ishlatilgan = 0
    else:
        ishlatilgan = u.get("oyin_soni", 0)
    if ishlatilgan >= S.ol("oyin_kunlik"):
        return web.json_response({"error": "limit"}, status=429)

    # Hamma urinish pullik: 100, 150, 200, 250, 300
    narx = oyin_narx(ishlatilgan)
    r = await users.update_one(
        {"_id": uid, "coins": {"$gte": narx}},
        {"$inc": {"coins": -narx}},
    )
    if r.modified_count == 0:
        return web.json_response(
            {"error": "tanga_yetmaydi", "replay_cost": narx}, status=402
        )
    r = await users.update_one(
        {"_id": uid, "oyin_sana": b, "oyin_soni": ishlatilgan},
        {"$inc": {"oyin_soni": 1}},
    )
    if r.modified_count == 0:
        await users.update_one({"_id": uid}, {"$inc": {"coins": narx}})
        return web.json_response({"error": "limit"}, status=429)

    # Taxtani server tuzadi: 8 ta tanga (narxdan kam) + 1 ta Super waifu
    shart = {"rarity": {"$in": ["rare", "Rare"]}}
    nodir_soni = await baza["characters"].count_documents(shart)
    tangalar = oyin_sovrinlar(narx)
    if nodir_soni:
        sovrin = random.randrange(9)
        karta = tangalar[:]
        random.shuffle(karta)
        karta.insert(sovrin, None)
    else:
        sovrin = -1
        karta = tangalar + [oyin_sovrinlar(narx)[-1]]
        random.shuffle(karta)

    if tanlov == sovrin:
        p = await baza["characters"].find_one(
            shart, skip=random.randrange(nodir_soni)
        )
        await baza["collection"].insert_one(
            {"user_id": uid, "char_id": p["_id"]}
        )
        natija = dict(kartochka_json(p), tur="personaj")
    else:
        natija = {"tur": "tanga", "miqdor": karta[tanlov]}
        await users.update_one(
            {"_id": uid}, {"$inc": {"coins": karta[tanlov]}}
        )

    await haftalik.qosh(
        baza, uid, "coin",
        (natija["miqdor"] if natija["tur"] == "tanga" else 0) - narx,
    )
    u = await users.find_one({"_id": uid})
    return web.json_response({
        "natija": natija,
        "taxta": [
            {"tur": "personaj"} if i == sovrin
            else {"tur": "tanga", "miqdor": karta[i]}
            for i in range(9)
        ],
        "pullik": True,
        "narx": narx,
        "coins": u.get("coins", 0),
        "qolgan": max(S.ol("oyin_kunlik") - (ishlatilgan + 1), 0),
        "free": False,
        "replay_cost": oyin_narx(ishlatilgan + 1),
    })


async def slot_api(request):
    f = tekshir(request.headers.get("X-Init-Data", ""))
    if not f:
        raise web.HTTPUnauthorized(text="Ruxsat yo'q")
    baza = request.app["baza"]
    await S.yangila(baza)
    users = baza["users"]
    uid = f["id"]
    u = await foydalanuvchi_ol(baza, f)
    b = bugun()
    tolangan = await tolangan_soni(baza, uid)

    try:
        pullik_xohish = bool((await request.json()).get("pullik"))
    except Exception:
        pullik_xohish = False

    # Urinishni atomik band qilamiz: avval bepul, keyin referal bonusi, oxirida pullik
    narx = 0
    r = await users.update_one(
        {"_id": uid, "slot_sana": {"$ne": b}}, {"$set": {"slot_sana": b}}
    )
    if r.modified_count == 0:
        holat = slot_holat(u, tolangan)
        band = False
        if holat["bonus"] == "bor":
            r = await users.update_one(
                {
                    "_id": uid,
                    "slot_bonus_sana": u.get("slot_bonus_sana"),
                    "slot_bonus_jami": u.get("slot_bonus_jami"),
                },
                {"$set": {"slot_bonus_sana": b}, "$inc": {"slot_bonus_jami": 1}},
            )
            band = r.modified_count > 0
        if not band:
            if holat["pullik"] != "bor":
                return web.json_response({"error": "limit"}, status=429)
            if not pullik_xohish:
                return web.json_response({"error": "pullik_kerak"}, status=402)
            r = await users.update_one(
                {
                    "_id": uid,
                    "coins": {"$gte": S.ol("slot_narx")},
                    "slot_pullik_sana": {"$ne": b},
                },
                {"$inc": {"coins": -S.ol("slot_narx")}, "$set": {"slot_pullik_sana": b}},
            )
            if r.modified_count == 0:
                u2 = await users.find_one({"_id": uid})
                if u2.get("slot_pullik_sana") == b:
                    return web.json_response({"error": "limit"}, status=429)
                return web.json_response(
                    {"error": "tanga_yetmaydi", "narx": S.ol("slot_narx")}, status=402
                )
            narx = S.ol("slot_narx")

    # Natijani server tanlaydi
    shart = {"rarity": {"$in": [SLOT_DARAJA, SLOT_DARAJA.capitalize()]}}
    nodir_soni = await baza["characters"].count_documents(shart)
    variantlar = [v for v in S.slot_natijalar() if v[0] != "w" or nodir_soni]
    rng = random.SystemRandom()
    tanlov = rng.choices(variantlar, weights=[v[1] for v in variantlar])[0]
    kalit, _, miqdor = tanlov

    if kalit == "n":
        # Uchala belgi bir xil bo'lmasligi shart
        belgilar = SLOT_BELGILAR if nodir_soni else [x for x in SLOT_BELGILAR if x != "w"]
        while True:
            g = [rng.choice(belgilar) for _ in range(3)]
            if len(set(g)) > 1:
                break
    else:
        g = [kalit] * 3

    if kalit == "w":
        p = await baza["characters"].find_one(
            shart, skip=random.randrange(nodir_soni)
        )
        await baza["collection"].insert_one(
            {"user_id": uid, "char_id": p["_id"]}
        )
        natija = dict(kartochka_json(p), tur="personaj")
    elif kalit == "n":
        natija = {"tur": "yoq"}
    else:
        natija = {"tur": "tanga", "miqdor": miqdor}
        await users.update_one({"_id": uid}, {"$inc": {"coins": miqdor}})

    await haftalik.qosh(
        baza, uid, "coin", (miqdor if kalit not in ("w", "n") else 0) - narx
    )
    u = await users.find_one({"_id": uid})
    return web.json_response({
        "k": kalit,
        "g": g,
        "narx": narx,
        "natija": natija,
        "coins": u.get("coins", 0),
        "slot": slot_holat(u, tolangan),
    })


async def ishga_tushish(app):
    app["mijoz"] = AsyncMongoClient(MONGO_URI)
    app["baza"] = app["mijoz"]["waifu"]
    app["sess"] = ClientSession()


async def tozalash(app):
    await app["sess"].close()
    await app["mijoz"].close()


async def bot_yoqish(app):
    await telegram_bot.initialize()
    await telegram_bot.start()
    await telegram_bot.updater.start_polling()
    haftalik.fon_boshlash(telegram_bot.bot)


async def bot_ochirish(app):
    await telegram_bot.updater.stop()
    await telegram_bot.stop()
    await telegram_bot.shutdown()


app = web.Application(middlewares=[cors])
app.on_startup.append(ishga_tushish)
app.on_cleanup.append(tozalash)
app.on_startup.append(bot_yoqish)
app.on_cleanup.append(bot_ochirish)
app.router.add_get("/", bosh)
app.router.add_get("/api/collection", kolleksiya_api)
app.router.add_get("/api/photo/{pid}", rasm)
app.router.add_get("/api/me", me_api)
app.router.add_post("/api/favorite", sevimli_api)
app.router.add_post("/api/game/play", oyin_api)
app.router.add_post("/api/slot/play", slot_api)

if __name__ == "__main__":
    web.run_app(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8080")))
