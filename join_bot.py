# join_bot.py
import os
import logging
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ContentType
from aiogram.utils.exceptions import TelegramAPIError

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ===== الإعدادات من المتغيرات البيئية =====
BOT_TOKEN = os.getenv("JOIN_TOKEN")
TARGET_CHAT_ID = os.getenv("TARGET_CHAT_ID")   # مثال: -1003041770290
CHANNEL_LINK = os.getenv("CHANNEL_LINK")       # رابط بديل (اختياري) مثل: https://t.me/yourchannel
IBAN_NUMBER = os.getenv("IBAN_NUMBER")         # رقم الآيبان الذي تريد عرضه للمشترك

if not BOT_TOKEN:
    raise RuntimeError("JOIN_TOKEN is missing. Set it in Render > Environment.")
if not TARGET_CHAT_ID:
    raise RuntimeError("TARGET_CHAT_ID is missing. Set it in Render > Environment.")
if not IBAN_NUMBER:
    raise RuntimeError("IBAN_NUMBER is missing. Set it in Render > Environment.")

# تأكد أن TARGET_CHAT_ID رقم صحيح
try:
    TARGET_CHAT_ID = int(TARGET_CHAT_ID)
except Exception:
    raise RuntimeError("TARGET_CHAT_ID must be an integer chat id (e.g. -100xxxxxxxxxx).")

bot = Bot(token=BOT_TOKEN, parse_mode=types.ParseMode.HTML)
dp = Dispatcher(bot)

# ===== رسائل جاهزة =====
WELCOME_TEXT = (
    "مرحبًا 👋\n"
    "للاشتراك اضغط الزر التالي، وستظهر لك طريقة الاشتراك.\n"
    "بعد التحويل أرسل <b>صورة</b> تأكيد هنا."
)

PAYMENT_TEXT = (
    "طريقة الاشتراك 🧾\n"
    "حوِّل الرسوم ١٨٠ ريال إلى الحساب المحدد ثم أرسل <b>صورة إيصال التحويل</b> هنا.\n\n"
    f"الآيبان: <code>{IBAN_NUMBER}</code>\n"
    "بعد التأكيد سيتم إرسال رابط دعوة صالح لعضو واحد ✅"
)

CONFIRM_RECEIVED_TEXT = (
    "✅ تم استلام التأكيد.\n"
    "جاري إنشاء رابط الدعوة…"
)

INVITE_FAILED_TEXT = (
    "⚠️ تعذّر إنشاء رابط الدعوة تلقائيًا (قد لا يكون البوت <b>مشرفًا</b> أو لا يملك صلاحية إنشاء الروابط).\n"
    "إن كان لديك رابط دائم للقناة/المجموعة فضعه في المتغير <code>CHANNEL_LINK</code> في Render ثم جرِّب مرة أخرى."
)

# ===== الأدوات =====
def subscribe_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton(text="الاشتراك 🟢", callback_data="subscribe"))
    return kb

# ===== Handlers =====
@dp.message_handler(commands=["start"])
async def cmd_start(message: types.Message):
    await message.answer(WELCOME_TEXT, reply_markup=subscribe_keyboard())

@dp.callback_query_handler(lambda c: c.data == "subscribe")
async def on_subscribe(cb: types.CallbackQuery):
    await cb.message.answer(PAYMENT_TEXT)
    await cb.answer()

@dp.message_handler(content_types=[ContentType.PHOTO])
async def on_payment_proof(message: types.Message):
    # المستخدم أرسل صورة إيصال
    await message.reply(CONFIRM_RECEIVED_TEXT)

    # محاولة إنشاء رابط دعوة صالح لعضو واحد ومدة 24 ساعة
    try:
        expire = datetime.utcnow() + timedelta(hours=24)
        invite = await bot.create_chat_invite_link(
            chat_id=TARGET_CHAT_ID,
            name=f"Invite-{message.from_user.id}",
            expire_date=expire,
            member_limit=1
        )
        # إرسال الرابط للمستخدم فقط
        await message.answer(f"🎟️ تفضل رابط الدعوة الخاص بك:\n{invite.invite_link}")
        return

    except TelegramAPIError as e:
        logger.warning("Failed to auto-create invite link: %s", e)

    # بديل لو فشلت الإنشاءات التلقائية
    if CHANNEL_LINK:
        await message.answer(
            "تم التأكيد ✅\n"
            "تعذّر إنشاء رابط لمرة واحدة، هذا رابط الانضمام المتاح حاليًا:\n"
            f"{CHANNEL_LINK}"
        )
    else:
        await message.answer(INVITE_FAILED_TEXT)

@dp.message_handler(content_types=ContentType.ANY)
async def fallback(message: types.Message):
    # أي شيء آخر غير صور الإيصال
    await message.answer(
        "لإتمام الاشتراك:\n"
        "1) اضغط زر <b>الاشتراك</b> لاستعراض الآيبان.\n"
        "2) بعد التحويل أرسل <b>صورة إيصال</b> هنا.\n",
        reply_markup=subscribe_keyboard()
    )

# ===== التشغيل =====
if __name__ == "__main__":
    logger.info("Starting Join bot…")
    executor.start_polling(dp, skip_updates=True)
