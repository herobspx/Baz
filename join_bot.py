import os
import logging
from datetime import timedelta, datetime

from aiogram import Bot, Dispatcher, executor, types
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

# ===== إعدادات عامة =====
logging.basicConfig(level=logging.INFO)

JOIN_TOKEN = os.getenv("JOIN_TOKEN")
TARGET_CHAT_ID = os.getenv("TARGET_CHAT_ID")
CHANNEL_LINK = os.getenv("CHANNEL_LINK")  # رابط عام ثابت كخطة بديلة

if not JOIN_TOKEN:
    raise RuntimeError("JOIN_TOKEN is missing. Set it in Render > Environment.")
if not TARGET_CHAT_ID:
    raise RuntimeError("TARGET_CHAT_ID is missing. Set it in Render > Environment.")
# CHANNEL_LINK اختياري لكنه مفيد كخطة بديلة

# بوت و دسباتشر
bot = Bot(token=JOIN_TOKEN)
dp = Dispatcher(bot)

# كيبورد الاشتراك
btn_subscribe = KeyboardButton("الاشتراك 🟢")
kb_subscribe = ReplyKeyboardMarkup(resize_keyboard=True)
kb_subscribe.add(btn_subscribe)

# نصوص عربية
WELCOME_TEXT = (
    "مرحبًا 👋\n"
    "للاشتراك اضغط الزر التالي، وستظهر لك طريقة الاشتراك.\n"
    "بعد التحويل أرسل صورة تأكيد هنا."
)

SUBSCRIBE_INSTRUCTIONS = (
    "طريقة الاشتراك 🧾\n"
    "حوِّل الرسوم 180 ريال إلى البنك العربي الوطني الآيبان /SA1630100991104930184574 ثم أرسل صورة إيصال التحويل هنا.\n\n"
    "بعد التأكيد سترسل لك المنظومة رابط الدعوة صالح لعضو واحد ✅"
)

SUCCESS_TEXT = "تم استلام التأكيد ✅\nجاري إنشاء رابط الدعوة…"

ERROR_NO_LINK_TEXT = (
    "تم التأكيد ✅\n"
    "تعذر إنشاء رابط دعوة تلقائي (يبدو أن البوت ليس مشرفًا أو لا يملك صلاحية الدعوة).\n"
)

# ===== مساعد لإنشاء رابط دعوة مخصص =====
async def make_single_use_invite(chat_id: int) -> str:
    """
    ينشئ رابط دعوة صالح لعضو واحد مع صلاحية انتهاء بعد 24 ساعة.
    يتطلب أن يكون البوت مشرفًا ولديه 'Invite Users'.
    """
    expire_dt = datetime.utcnow() + timedelta(hours=24)
    # member_limit = 1 يجعل الرابط صالح لعضو واحد فقط
    link = await bot.create_chat_invite_link(
        chat_id=chat_id,
        expire_date=expire_dt,
        member_limit=1,
        name="JoinBot single-use"
    )
    return link.invite_link

# ===== الهاندلرز =====
@dp.message_handler(commands=["start"])
async def cmd_start(message: types.Message):
    await message.answer(WELCOME_TEXT, reply_markup=kb_subscribe)

@dp.message_handler(lambda m: m.text and m.text.strip() == "الاشتراك 🟢")
async def on_subscribe(message: types.Message):
    await message.answer(SUBSCRIBE_INSTRUCTIONS, reply_markup=kb_subscribe)

@dp.message_handler(content_types=types.ContentTypes.PHOTO)
async def on_payment_proof(message: types.Message):
    # استلمنا صورة كإثبات
    await message.answer(SUCCESS_TEXT)

    # حاول إنشاء رابط دعوة مخصص
    invite_url = None
    try:
        # تحويل TARGET_CHAT_ID إلى int إن أمكن
        target_id = int(TARGET_CHAT_ID)
    except ValueError:
        # لو كان محفوظ كنص يبدأ بـ -100 نتركه كنص
        target_id = TARGET_CHAT_ID

    try:
        invite_url = await make_single_use_invite(target_id)
    except Exception as e:
        logging.warning(f"Failed to create invite link automatically: {e}")

    if invite_url:
        await message.answer(
            f"هذا رابط الدعوة الخاص بك (صالح لعضو واحد ولمدة 24 ساعة):\n{invite_url}"
        )
    else:
        if CHANNEL_LINK:
            await message.answer(
                ERROR_NO_LINK_TEXT + f"استخدم هذا الرابط للانضمام:\n{CHANNEL_LINK}"
            )
        else:
            await message.answer(
                ERROR_NO_LINK_TEXT
                + "لم يتم إعداد CHANNEL_LINK كخطة بديلة. "
                  "أضف متغير CHANNEL_LINK في Render أو اجعل البوت مشرفًا ثم جرّب مجددًا."
            )

# رسالة افتراضية لباقي النصوص
@dp.message_handler(content_types=types.ContentTypes.TEXT)
async def echo_message(message: types.Message):
    # توجيه المستخدم نحو زر الاشتراك لو أرسل نص عشوائي
    await message.answer("أرسل صورة إيصال التحويل بعد الضغط على زر الاشتراك.", reply_markup=kb_subscribe)

# ===== التشغيل =====
if __name__ == "__main__":
    # في Render استخدم Start Command: python3 join_bot.py
    executor.start_polling(dp, skip_updates=True)
