# join_bot.py
import os
import asyncio
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher, executor, types
from dotenv import load_dotenv

# ===== إعدادات عامة =====
load_dotenv()
TOKEN = os.getenv("JOIN_TOKEN")
TARGET_CHAT_ID = os.getenv("TARGET_CHAT_ID")  # مثال: -1001234567890
FALLBACK_CHANNEL_LINK = os.getenv("CHANNEL_LINK")  # اختياري: رابط دعوة جاهز
ADMIN_ID = os.getenv("ADMIN_ID")  # اختياري: تيليجرام ID للمشرف لتلقي إنذارات

if not TOKEN:
    raise RuntimeError("JOIN_TOKEN is missing. Set it in Render > Environment.")
if not TARGET_CHAT_ID:
    raise RuntimeError("TARGET_CHAT_ID is missing. Set it in Render > Environment.")

bot = Bot(token=TOKEN, parse_mode="HTML")
dp = Dispatcher(bot)

# حالة بسيطة بالذاكرة: من ينتظر إرسال إيصال
pending_photo = {}  # {user_id: expires_at(datetime)}

# ===== أدوات مساعدة =====
MAX_CHARS = 4000

async def chunk_and_send(chat_id: int, text: str, reply_markup=None):
    """قسّم الرسالة الطويلة تلقائياً وأرسلها على دفعات."""
    if len(text) <= MAX_CHARS:
        await bot.send_message(chat_id, text, reply_markup=reply_markup)
        return
    chunks = [text[i:i+MAX_CHARS] for i in range(0, len(text), MAX_CHARS)]
    # أرسل أول جزء مع الكيبورد (إن وجد) والبقية بدون
    for i, chunk in enumerate(chunks):
        await bot.send_message(chat_id, chunk, reply_markup=reply_markup if i == 0 else None)

async def notify_admin(text: str):
    if ADMIN_ID:
        try:
            await bot.send_message(int(ADMIN_ID), f"⚠️ {text}")
        except Exception:
            pass

async def create_single_use_invite() -> str | None:
    """
    يحاول إنشاء رابط دعوة صالح لعضو واحد فقط.
    يتطلب أن يكون البوت مشرفاً في المجموعة/القناة مع صلاحية إنشاء الروابط.
    """
    try:
        # member_limit=1 يجعل الرابط صالحاً لشخص واحد
        link = await bot.create_chat_invite_link(
            chat_id=int(TARGET_CHAT_ID),
            member_limit=1,
            expire_date=int((datetime.utcnow() + timedelta(minutes=10)).timestamp())
        )
        return link.invite_link
    except Exception as e:
        await notify_admin(f"تعذر إنشاء رابط تلقائي: {e}")
        return None

# ===== الرسائل الثابتة (قصيرة) =====
WELCOME = (
    "مرحباً 👋\n"
    "للاشتراك اضغط الزر التالي، ستظهر لك طريقة الاشتراك.\n"
    "بعد التحويل أرسل صورة إيصال التحويل هنا."
)

METHOD = (
    "🧾 <b>طريقة الاشتراك</b>\n"
    "حوِّل الرسوم إلى الحساب المحدّد ثم أرسل صورة إيصال التحويل هنا.\n"
    "بعد التحقق سترسل لك المنظومة رابط الدعوة (لعضو واحد)."
)

SUCCESS_RECEIVED = (
    "✅ تم استلام التأكيد.\n"
    "جاري إنشاء رابط الدعوة…"
)

FALLBACK_MSG = (
    "⚠️ تعذر إنشاء رابط تلقائي.\n"
    "يمكنك الانضمام عبر الرابط التالي:\n{link}"
)

PERMISSION_HINT = (
    "⚠️ ملاحظة إدارية: تأكد أن البوت مشرف في القناة/المجموعة مع صلاحية دعوة المستخدمين."
)

# ===== الأزرار =====
def start_keyboard():
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("الاشتراك 🟢", callback_data="subscribe"))
    return kb

# ===== المعالجات =====
@dp.message_handler(commands=["start"])
async def cmd_start(message: types.Message):
    await chunk_and_send(message.chat.id, WELCOME, reply_markup=start_keyboard())

@dp.callback_query_handler(lambda c: c.data == "subscribe")
async def cb_subscribe(query: types.CallbackQuery):
    user_id = query.from_user.id
    # المستخدم لديه 15 دقيقة لإرسال الإيصال
    pending_photo[user_id] = datetime.utcnow() + timedelta(minutes=15)
    await chunk_and_send(query.message.chat.id, METHOD)
    # تلميح إداري لمرة واحدة
    await notify_admin(PERMISSION_HINT)
    await query.answer()  # لإغلاق "Loading…"

@dp.message_handler(content_types=["photo"])
async def handle_receipt(message: types.Message):
    user_id = message.from_user.id
    # تحقق أن البوت ينتظر إيصالاً من هذا المستخدم
    expires = pending_photo.get(user_id)
    if not expires or datetime.utcnow() > expires:
        # ليس في وضع الاشتراك
        await message.reply("أرسل /start ثم اختر الاشتراك.")
        return

    # (يمكنك هنا إضافة تحقق يدوي/تلقائي من الصورة إن رغبت)
    await message.reply(SUCCESS_RECEIVED)

    # حاول إنشاء رابط لمرة واحدة
    invite = await create_single_use_invite()

    if invite:
        await message.answer(f"🎟️ <b>رابط الدعوة:</b>\n{invite}")
    elif FALLBACK_CHANNEL_LINK:
        await message.answer(FALLBACK_MSG.format(link=FALLBACK_CHANNEL_LINK))
    else:
        await message.answer(
            "❌ تعذر إنشاء رابط الدعوة تلقائياً، ولا يوجد رابط بديل محدد.\n"
            "يرجى المحاولة لاحقاً."
        )

    # إزالة الحالة
    pending_photo.pop(user_id, None)

@dp.errors_handler()
async def errors_handler(update, error):
    # أهم خطأ كان MESSAGE_TOO_LONG – الكود الحالي يعالجه بالتقسيم، ومع ذلك نسجل أي أخطاء
    try:
        await notify_admin(f"Error: {error}")
    finally:
        return True  # منع تتبع مطوّل في اللوج

# ===== التشغيل =====
if __name__ == "__main__":
    # ملاحظة: اجعل أمر التشغيل في Render = python3 join_bot.py
    executor.start_polling(dp, skip_updates=True)
