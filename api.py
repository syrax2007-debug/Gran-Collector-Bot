import os
import hmac
import json
import time
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
    javob.headers["Access-Control-Allow-Methods"] = "GET, OPTIONS"
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


async def ishga_tushish(app):
    app["mijoz"] = AsyncMongoClient(MONGO_URI)
    app["baza"] = app["mijoz"]["waifu"]
    app["sess"] = ClientSession()


async def tozalash(app):
    await app["sess"].close()
    await app["mijoz"].close()


app = web.Application(middlewares=[cors])
app.on_startup.append(ishga_tushish)
app.on_cleanup.append(tozalash)
app.router.add_get("/", bosh)
app.router.add_get("/api/collection", kolleksiya_api)
app.router.add_get("/api/photo/{pid}", rasm)

if __name__ == "__main__":
    web.run_app(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8080")))
