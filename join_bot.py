# join_bot.py
import os
import asyncio
from aiogram import Bot, Dispatcher, executor, types

TOKEN = os.getenv("JOIN_TOKEN")
if not TOKEN or not isinstance(TOKEN, str):
    raise RuntimeError("JOIN_TOKEN is missing. Set it in Render > Environment.")

bot = Bot(token=TOKEN, parse_mode=types.ParseMode.HTML)
dp = Dispatcher(bot)

@dp.message_handler(commands=["start", "help"])
async def cmd_start(message: types.Message):
    await message.answer("البوت شغّال ✅\nأرسل أي رسالة هنا للتجربة.")

@dp.message_handler()
async def echo(message: types.Message):
    await message.reply(f"استقبلت: <b>{message.text}</b>")

if __name__ == "__main__":
    # تشغيل البولِّنج
    executor.start_polling(dp, skip_updates=True)
