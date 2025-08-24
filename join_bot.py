# join_bot.py
import os
import logging
from datetime import timedelta

from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor
from aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton, ContentType
)
from aiogram.utils.exceptions import BadRequest  # <-- Aiogram v2.25.1

from dotenv import load_dotenv

# ============ الإعدادات ============
load_dotenv()

TOKEN = os.getenv("JOIN_TOKEN")
if not TOKEN:
    raise RuntimeError("JOIN_TOKEN is missing. Set it in Render > Environment.")

# هدف الإضافة (قروب/قناة). مثال: -1003041770290
TARGET_CHAT_ID_ENV = os.getenv("TARGET_CHAT_ID")
if not TARGET_CHAT_ID_ENV:
    raise RuntimeError("TARGET_CHAT_ID is missing. Set it in Render > Environment.")
try:
    TARGET_CHAT_ID = int(TARGET_CHAT_ID_ENV)
except ValueError:
    raise RuntimeError("TARGET_CHAT_ID must be an integer chat id (e.g. -100xxxxxxxxxx).")

# آيبان الدفع لرسالة طريقة الاشتراك
IBAN = os.getenv("IBAN", "SA00 0000 0000 0000 0000 0000")  # غيّره من المتغيّر بالبيئة

# مسؤول الموافقة (اختياري لكن مستحسن). ضع Chat ID الخاص بك
ADMIN_ID = os.getenv("ADMIN_ID")  # example: 302461787
ADMIN_ID = int(ADMIN_ID) if ADMIN_ID and ADMIN_ID.isdigit() else None

# رابط احتياطي ثابت للقناة/القروب (في حال تعذر إنشاء رابط تلقائي)
CHANNEL_LINK = os.getenv("CHANNEL_LINK")  # مثال: https://t.me/yourPublicChannel

# ============ بوت/ديسباتشر ============
logging.basicConfig(level=logging.INFO)
bot = Bot(token=TOKEN, parse_mode=types.ParseMode.HTML)
dp = Dispatcher(bot)

# pending confirmations: user_id -> dict(info)
PENDING = {}

# ============ مساعدات ============
def subscribe_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("الاشتراك 🟢", callback_data="start_sub"))
    return kb

def approve_kb(user_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("✅ تأكيد", callback_data=f"approve:{user_id}"),
        InlineKeyboardButton("❌ رفض", callback_data=f"reject:{user_id}")
    )
    return kb

async def try_make_invite_link() -> str:
    """
    يحاول إنشاء رابط دعوة مؤقت تلقائيًا.
    يتطلب أن يكون البوت مشرفًا في القروب/القناة بصلاحية 'Invite users'.
    """
    try:
        # حاول إنشاء رابط دعوة صالح لعضو واحد لمدة 24 ساعة
        link = await bot.create_chat_invite_link(
            chat_id=TARGET_CHAT_ID,
            name="Auto by Join Bot",
            expire_date=timedelta(hours=24),
            member_limit=1
        )
        # في Aiogram 2.x ترجع كائن ChatInviteLink يحتوي .invite_link
        return link.invite_link
    except BadRequest as e:
        logging.warning(f"Failed to create invite link automatically: {e}")
        # جرّب تصدير رابط دعوة عام (قد يكون دائمًا)
        try:
            exported = await bot.export_chat_invite_link(TARGET_CHAT_ID)
            return exported
        except BadRequest as e2:
            logging.warning(f"Fallback export invite failed: {e2}")
            # آخر حل: استخدم CHANNEL_LINK إن تم ضبطه
            if CHANNEL_LINK:
                return CHANNEL_LINK
            # لم نتمكن من إنشاء رابط
            return ""

# ============ الأوامر والتعامل ============
@dp.message_handler(commands=["start"])
async def cmd_start(message: types.Message):
    text = (
        "مرحبًا 👋\n"
        "للاشتراك اضغط الزر التالي، وستظهر لك طريقة الاشتراك.\n"
        "بعد التحويل أرسل <b>صورة إيصال التحويل</b> هنا."
    )
    await message.answer(text, reply_markup=subscribe_kb())

@dp.callback_query_handler(lambda c: c.data == "start_sub")
async def show_payment_info(cb: types.CallbackQuery):
    text = (
        "🧾 <b>طريقة الاشتراك</b>\n"
        "حوِّل الرسوم ١٨٠ ريال إلى الحساب المحدد:\n"
        f"<b>الآيبان:</b> <code>{IBAN}</code>\n"
        "ثم أرسل <b>صورة إيصال التحويل</b> هنا.\n\n"
        "بعد التأكيد سيُرسَل لك رابط دعوة صالح لعضو واحد ✅"
    )
    await cb.message.answer(text)
    await cb.answer()

@dp.message_handler(content_types=ContentType.PHOTO)
async def handle_receipt(message: types.Message):
    """
    أي صورة تُعتبر إيصال. نحفظ الطلب ونسأل المشرف للتأكيد.
    """
    user_id = message.from_user.id
    file_id = message.photo[-1].file_id
    caption = message.caption or ""

    # خزّن الطلب بانتظار موافقة المشرف
    PENDING[user_id] = {
        "file_id": file_id,
        "caption": caption,
        "user_name": message.from_user.full_name,
        "user_username": f"@{message.from_user.username}" if message.from_user.username else "-",
        "chat_id": message.chat.id
    }

    # أرسل للمستخدم إشعارًا مختصرًا
    await message.reply("✅ تم استلام التأكيد.\nجاري انتظار موافقة المشرف…")

    # أرسل للمشرف للموافقة (إذا متاح)، وإلا أنبّه المستخدم أن الموافقة اليدوية مطلوبة
    if ADMIN_ID:
        info = PENDING[user_id]
        txt = (
            f"طلب اشتراك جديد 🆕\n"
            f"العضو: <b>{info['user_name']}</b> ({info['user_username']})\n"
            f"User ID: <code>{user_id}</code>\n\n"
            "تأكيد الدفع؟"
        )
        try:
            await bot.send_photo(
                ADMIN_ID,
                photo=file_id,
                caption=txt,
                reply_markup=approve_kb(user_id)
            )
        except Exception as e:
            logging.warning(f"Failed to notify admin: {e}")
    else:
        await message.answer("ℹ️ لم يتم ضبط ADMIN_ID، لا يمكن تأكيد الطلب تلقائيًا.")

@dp.callback_query_handler(lambda c: c.data.startswith("approve:") or c.data.startswith("reject:"))
async def on_review(cb: types.CallbackQuery):
    action, user_id_str = cb.data.split(":")
    try:
        user_id = int(user_id_str)
    except ValueError:
        await cb.answer("معرّف غير صالح.", show_alert=True)
        return

    # تأكد أن هناك طلبًا قيد الانتظار
    if user_id not in PENDING:
        await cb.answer("لا يوجد طلب معلق لهذا المستخدم.", show_alert=True)
        return

    if action == "reject":
        # أبلغ المستخدم بالرفض
        try:
            await bot.send_message(user_id, "❌ تم رفض طلب الاشتراك. يُرجى التواصل للدعم إن كان ذلك خطأ.")
        except Exception:
            pass
        del PENDING[user_id]
        await cb.message.edit_caption(cb.message.caption + "\n\nتم الرفض ❌")
        await cb.answer("تم الرفض.")
        return

    # موافقة
    invite = await try_make_invite_link()
    if not invite:
        # تعذّر إنشاء رابط
        try:
            await bot.send_message(
                user_id,
                "❗️ تعذّر إنشاء رابط الدعوة تلقائيًا الآن. "
                "تأكد أن البوت مشرف بصلاحية دعوة الأعضاء أو وفّر CHANNEL_LINK ثابت."
            )
        except Exception:
            pass
        await cb.answer("تعذّر إنشاء الرابط.", show_alert=True)
        return

    # أرسل الرابط للمستخدم
    try:
        await bot.send_message(
            user_id,
            "✅ تم التأكيد.\n"
            f"هذا رابط الدعوة الخاص بك (صالح لعضو واحد):\n{invite}"
        )
    except Exception as e:
        logging.warning(f"Failed to DM user: {e}")

    # حدّث رسالة المشرف
    await cb.message.edit_caption(cb.message.caption + "\n\nتمت الموافقة ✅")
    await cb.answer("تمت الموافقة وإرسال الرابط.")

    # أزل من قائمة الانتظار
    PENDING.pop(user_id, None)

# حماية من الرسائل النصية العشوائية
@dp.message_handler(content_types=ContentType.TEXT)
async def echo_info(message: types.Message):
    # اختصار الرسائل كي لا تتسبب في MESSAGE_TOO_LONG
    if message.text.strip().startswith("/"):
        return
    await message.answer("أرسل /start أو صورة إيصال التحويل للمتابعة.")

# ============ تشغيل ============
if __name__ == "__main__":
    logging.info("Starting Join bot…")
    executor.start_polling(dp, skip_updates=True)
