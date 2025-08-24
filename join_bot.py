# join_bot.py
import os
import asyncio
import time
import aiosqlite
from contextlib import suppress

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import (Message, CallbackQuery, InlineKeyboardMarkup,
                           InlineKeyboardButton)
from aiogram.enums import ParseMode

JOIN_TOKEN = os.getenv("JOIN_TOKEN")  # اجباري
TARGET_CHAT_ID = int(os.getenv("TARGET_CHAT_ID", "0"))  # اجباري: اكتب رقم الجروب/القناة
SUB_DURATION_DAYS = int(os.getenv("SUB_DURATION_DAYS", "30"))  # مدة الاشتراك بالايام

if not JOIN_TOKEN:
    raise RuntimeError("JOIN_TOKEN is missing. Set it in Render > Environment.")
if TARGET_CHAT_ID == 0:
    raise RuntimeError("TARGET_CHAT_ID is missing. Set it in Render > Environment.")

DB_PATH = "subs.db"

bot = Bot(token=JOIN_TOKEN, parse_mode=ParseMode.HTML)
dp = Dispatcher()


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS subs (
                user_id INTEGER NOT NULL,
                chat_id INTEGER NOT NULL,
                expires_at INTEGER NOT NULL,
                PRIMARY KEY (user_id, chat_id)
            )
        """)
        await db.commit()


async def schedule_kick(user_id: int, chat_id: int, expires_at: int):
    """يجدول طرد المستخدم عند إنتهاء الاشتراك."""
    delay = max(0, expires_at - int(time.time()))
    await asyncio.sleep(delay)
    # طرد ثم إلغاء الحظر ليسمح بإعادة الاشتراك لاحقاً
    with suppress(Exception):
        await bot.ban_chat_member(chat_id, user_id)
    await asyncio.sleep(1)
    with suppress(Exception):
        await bot.unban_chat_member(chat_id, user_id)
    # حذف السجل من القاعدة
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM subs WHERE user_id=? AND chat_id=?", (user_id, chat_id))
        await db.commit()


async def restore_schedules():
    """إعادة جدولة كل الاشتراكات غير المنتهية بعد إعادة تشغيل البوت."""
    now = int(time.time())
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT user_id, chat_id, expires_at FROM subs WHERE expires_at > ?", (now,)) as cur:
            async for user_id, chat_id, expires_at in cur:
                asyncio.create_task(schedule_kick(user_id, chat_id, expires_at))


def sub_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🟢 الاشتراك", callback_data="subscribe")
    ]])
    return kb


@dp.message(CommandStart())
async def start_cmd(msg: Message):
    text = (
        "مرحباً 👋\n"
        "للاشتراك اضغط الزر التالي، وستظهر لك طريقة الاشتراك.\n"
        "بعد التحويل أرسل <b>صورة تأكيد</b> هنا."
    )
    await msg.answer(text, reply_markup=sub_keyboard())


@dp.callback_query(F.data == "subscribe")
async def show_payment_info(cb: CallbackQuery):
    text = (
        "💳 <b>طريقة الاشتراك</b>\n"
        "حوّل الرسوم إلى الحساب المحدد (البنك العربي الوطني الآيبان / SA1630100991104930184574)\n"
        "ثم أرسل <b>صورة</b> إيصال التحويل هنا.\n\n"
        "بعد التأكيد سترسل لك المنظومة رابط دعوة صالح لعضو واحد ✅"
    )
    await cb.message.answer(text)
    await cb.answer()


@dp.message(F.photo)
async def handle_proof(msg: Message):
    user_id = msg.from_user.id

    # صنع رابط دعوة فردي لمدة ساعة (3600 ثانية)
    expire = int(time.time()) + 3600
    invite = await bot.create_chat_invite_link(
        chat_id=TARGET_CHAT_ID,
        expire_date=expire,
        member_limit=1,
        creates_join_request=False
    )

    # سجل انتهاء الاشتراك بعد المدة المحددة
    expires_at = int(time.time()) + SUB_DURATION_DAYS * 24 * 3600

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO subs (user_id, chat_id, expires_at) VALUES (?,?,?)",
            (user_id, TARGET_CHAT_ID, expires_at)
        )
        await db.commit()

    # جدولة الطرد
    asyncio.create_task(schedule_kick(user_id, TARGET_CHAT_ID, expires_at))

    # أرسل الرابط وموعد الانتهاء
    until_str = f"{SUB_DURATION_DAYS} يوم"
    await msg.answer(
        "تم التحقق من الإيصال ✅\n"
        f"هذا رابط الانضمام (صالح لساعة واحدة وعضو واحد):\n{invite.invite_link}\n\n"
        f"⏳ مدة الاشتراك: {until_str}\n"
        "ملاحظة: البوت يحتاج أن يكون أدمن في الجروب ليستطيع إدارة الاشتراك."
    )


@dp.message()
async def fallback(msg: Message):
    await msg.answer(
        "✅ البوت شغّال.\n"
        "اكتب /start ثم اضغط “الاشتراك”، وبعد الدفع أرسل <b>صورة</b> تأكيد هنا."
    )


async def main():
    await init_db()
    await restore_schedules()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
