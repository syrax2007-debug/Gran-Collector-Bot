import os
import asyncio
from aiogram import Bot, Dispatcher
from aiogram.filters import Command
from aiogram.types import Message

bot = Bot(token=os.environ["BOT_TOKEN"])
dp = Dispatcher()

@dp.message(Command("start"))
async def start(m: Message):
    await m.answer("Salom! Men waifu botman 🌸")

async def main():
    await dp.start_polling(bot)

asyncio.run(main())
