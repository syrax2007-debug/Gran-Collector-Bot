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
from referal import REFERAL_TANGA

BOT_TOKEN = os.environ["BOT_TOKEN"]
MONGO_URI = os.environ["MONGO_URI"]
# Mini App sahifasi turgan manzil (faqat shu sayt API'dan foydalana oladi)
RUXSAT_ETILGAN = os.environ.get(
    "ALLOWED_ORIGIN", "https://syrax2007-debug.github.io"
)
TOSHKENT = timezone(timedelta(hours=5))

# ---------- O'yin sozlamalari ----------
OYIN_KUNLIK = 5  # kuniga jami urinish
OYIN_BEPUL = 1  # shundan nechtasi bepul
REPLAY_NARX = 100  # pullik urinish narxi (tanga)
KATTA_TANGALAR = [200, 150]  # 2x va 1.5x sovrin
KICHIK_TANGALAR = [10, 20, 30, 40, 50, 60, 80]  # narxdan kam ("minus")


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
        "free": ishlatilgan < OYIN_BEPUL,
        "qolgan": max(OYIN_KUNLIK - ishlatilgan, 0),
        "limit": OYIN_KUNLIK,
        "replay_cost": REPLAY_NARX,
        "sevimli": sevimli,
        "ref_link": f"https://t.me/{nom}?start=ref_{f['id']}" if nom else "",
        "ref_tolangan": tolangan,
        "ref_kutilmoqda": kutilmoqda,
        "ref_tanga": REFERAL_TANGA,
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
    if ishlatilgan >= OYIN_KUNLIK:
        return web.json_response({"error": "limit"}, status=429)

    # Bepul urinishdan keyingilari tanga evaziga
    pullik = ishlatilgan >= OYIN_BEPUL
    if pullik:
        r = await users.update_one(
            {"_id": uid, "coins": {"$gte": REPLAY_NARX}},
            {"$inc": {"coins": -REPLAY_NARX}},
        )
        if r.modified_count == 0:
            return web.json_response(
                {"error": "tanga_yetmaydi", "replay_cost": REPLAY_NARX},
                status=402,
            )
    r = await users.update_one(
        {"_id": uid, "oyin_sana": b, "oyin_soni": {"$lt": OYIN_KUNLIK}},
        {"$inc": {"oyin_soni": 1}},
    )
    if r.modified_count == 0:
        if pullik:
            await users.update_one(
                {"_id": uid}, {"$inc": {"coins": REPLAY_NARX}}
            )
        return web.json_response({"error": "limit"}, status=429)

    # Taxtani server tuzadi: 2x, 1.5x va 7 ta kichik sovrin
    shart = {"rarity": {"$in": ["rare", "Rare"]}}
    nodir_soni = await baza["characters"].count_documents(shart)
    karta = KATTA_TANGALAR + KICHIK_TANGALAR
    random.shuffle(karta)
    # Har o'yinda 9 ta kartaning bittasida DOIM waifu bor (o'rni tasodifiy)
    sovrin = random.randrange(9) if nodir_soni else -1

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

    u = await users.find_one({"_id": uid})
    return web.json_response({
        "natija": natija,
        "taxta": [
            {"tur": "personaj"} if i == sovrin
            else {"tur": "tanga", "miqdor": karta[i]}
            for i in range(9)
        ],
        "pullik": pullik,
        "coins": u.get("coins", 0),
        "qolgan": max(OYIN_KUNLIK - (ishlatilgan + 1), 0),
        "free": (ishlatilgan + 1) < OYIN_BEPUL,
        "replay_cost": REPLAY_NARX,
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

if __name__ == "__main__":
    web.run_app(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8080")))
    
