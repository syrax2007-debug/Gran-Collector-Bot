import re
from telegram.ext import ExtBot

# a-z harflarining kichik bosh (small caps) ko'rinishi
ODDIY = "abcdefghijklmnopqrstuvwxyz"
KICHIK_BOSH = "ᴀʙᴄᴅᴇꜰɢʜɪᴊᴋʟᴍɴᴏᴘǫʀꜱᴛᴜᴠᴡxʏᴢ"
KICHIK = dict(zip(ODDIY, KICHIK_BOSH))
TESKARI = {v: k for k, v in KICHIK.items() if k != v}

_HARFLAR = "A-Za-z" + "".join(TESKARI)
SOZ = re.compile(rf"[{_HARFLAR}]+(?:['ʻ’][{_HARFLAR}]+)*")

# Bularga tegilmaydi: HTML teglar, <code> ichi, havolalar,
# /buyruqlar va #KODlar
HIMOYA = re.compile(
    r"(<code>.*?</code>|<[^>]+>|&#?\w+;|https?://\S+"
    r"|(?<!\w)/\w+(?:@\w+)?|#[A-Za-z0-9]{3,})",
    re.S,
)


def _soz(w):
    w = "".join(TESKARI.get(c, c) for c in w).lower()
    return w[0].upper() + "".join(KICHIK.get(c, c) for c in w[1:])


def stil(matn):
    # Har bir so'zni "Nᴀᴍᴇ" ko'rinishiga o'tkazadi
    qismlar = HIMOYA.split(matn)
    for i in range(0, len(qismlar), 2):
        qismlar[i] = SOZ.sub(lambda m: _soz(m.group()), qismlar[i])
    return "".join(qismlar)


class StilBot(ExtBot):
    # Chiqadigan hamma matnga avtomatik uslub beradi

    @staticmethod
    def _kw(kw, kalit):
        v = kw.get(kalit)
        if isinstance(v, str) and v:
            kw[kalit] = stil(v)

    async def send_message(self, *args, **kwargs):
        if len(args) > 1 and isinstance(args[1], str):
            args = (args[0], stil(args[1])) + tuple(args[2:])
        self._kw(kwargs, "text")
        return await super().send_message(*args, **kwargs)

    async def edit_message_text(self, *args, **kwargs):
        if args and isinstance(args[0], str):
            args = (stil(args[0]),) + tuple(args[1:])
        self._kw(kwargs, "text")
        return await super().edit_message_text(*args, **kwargs)

    async def send_photo(self, *args, **kwargs):
        self._kw(kwargs, "caption")
        return await super().send_photo(*args, **kwargs)

    async def answer_callback_query(self, *args, **kwargs):
        self._kw(kwargs, "text")
        return await super().answer_callback_query(*args, **kwargs)
