import os
import hmac
import json
import time
import random
from datetime import datetime, timedelta, timezone
import hashlib
from urllib.parse import parse_qsl
from aiohttp import web, ClientSession
from bson import ObjectId
from pymongo import AsyncMongoClient
from main import ilova as telegram_bot

BOT_TOKEN = os.environ["BOT_TOKEN"]
MONGO_URI = os.environ["MONGO_URI"]
# Mini App sahifasi turgan manzil (faqat shu sayt API'dan foydalana oladi)
RUXSAT_ETILGAN = os.environ.get(
    "ALLOWED_ORIGIN", "https://syrax2007-debug.github.io"
)

TOSHKENT = timezone(timedelta(hours=5))
REPLAY_NARX = 60  # qayta o'ynash narxi (tanga)
TANGA_QIYMATLARI = [5, 10, 15, 20, 25, 50]


def bugun():
    return datetime.now(TOSHKENT).strftime("%Y-%m-%d")


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
        royxat.append({
            "name": p["name"],
            "anime": p["anime"],
            "rarity": p["rarity"],
            "count": sanash[p["_id"]],
            "image": f"/api/photo/{p['_id']}",
        })
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

async def foydalanuvchi_ol(baza, f):
    await baza["users"].update_one(
        {"_id": f["id"]},
        {"$set": {"name": f.get("first_name", "")}},
        upsert=True,
    )
    return await baza["users"].find_one({"_id": f["id"]})


async def me_api(request):
    f = tekshir(request.headers.get("X-Init-Data", ""))
    if not f:
        raise web.HTTPUnauthorized(text="Ruxsat yo'q")
    u = await foydalanuvchi_ol(request.app["baza"], f)
    return web.json_response({
        "coins": u.get("coins", 0),
        "free": u.get("last_free_play") != bugun(),
        "replay_cost": REPLAY_NARX,
    })


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
    await foydalanuvchi_ol(baza, f)

    # 1) Kunlik bepul urinish, 2) bo'lmasa tanga evaziga
    r = await users.update_one(
        {"_id": uid, "last_free_play": {"$ne": bugun()}},
        {"$set": {"last_free_play": bugun()}},
    )
    pullik = False
    if r.modified_count == 0:
        r = await users.update_one(
            {"_id": uid, "coins": {"$gte": REPLAY_NARX}},
            {"$inc": {"coins": -REPLAY_NARX}},
        )
        if r.modified_count == 0:
            return web.json_response(
                {"error": "tanga_yetmaydi", "replay_cost": REPLAY_NARX},
                status=402,
            )
        pullik = True

    # Taxtani server tuzadi
    shart = {"rarity": {"$in": ["rare", "Rare"]}}
    nodir_soni = await baza["characters"].count_documents(shart)
    sovrin = random.randrange(9) if nodir_soni else -1
    tangalar = [random.choice(TANGA_QIYMATLARI) for _ in range(9)]

    if tanlov == sovrin:
        p = await baza["characters"].find_one(
            shart, skip=random.randrange(nodir_soni)
        )
        await baza["collection"].insert_one({"user_id": uid, "char_id": p["_id"]})
        natija = {
            "tur": "personaj", "name": p["name"], "anime": p["anime"],
            "rarity": p["rarity"], "image": f"/api/photo/{p['_id']}",
        }
    else:
        natija = {"tur": "tanga", "miqdor": tangalar[tanlov]}
        await users.update_one({"_id": uid}, {"$inc": {"coins": tangalar[tanlov]}})

    u = await users.find_one({"_id": uid})
    return web.json_response({
        "natija": natija,
        "taxta": [
            {"tur": "personaj"} if i == sovrin
            else {"tur": "tanga", "miqdor": tangalar[i]}
            for i in range(9)
        ],
        "pullik": pullik,
        "coins": u.get("coins", 0),
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

if __name__ == "__main__":
    web.run_app(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8080")))
