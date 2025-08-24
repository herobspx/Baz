# join_bot.py
import logging
import os
from datetime import timedelta

from aiogram import Bot, Dispatcher, executor, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ChatInviteLink
from aiogram.utils.exceptions import TelegramAPIError

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ========= الإعدادات من البيئة =========
TOKEN = os.getenv("JOIN_TOKEN") or os.getenv("BOT_TOKEN")
if not TOKEN:
    raise RuntimeError("JOIN_TOKEN مفقود. ضعه في Render > Environment.")

# مجموعة/قناة الهدف (سوبرجروب أو قناة). مثال: -1003041770290
TARGET_CHAT_ID_RAW = os.getenv("TARGET_CHAT_ID", "").strip()
TARGET_CHAT_ID = int(TARGET_CHAT_ID_RAW) if TARGET_CHAT_ID_RAW and TARGET_CHAT_ID_RAW.lstrip("-").isdigit() else None

# رابط احتياطي ثابت (إذا فشل إنشاء رابط دعوة تلقائيًا)
CHANNEL_LINK = os.getenv("CHANNEL_LINK", "").strip()  # اختياري

# آي دي المشرف الذي يستلم طلبات الموافقة (من @RawDataBot)
ADMIN_ID_RAW = os.getenv("ADMIN_ID", "").strip()
ADMIN_ID = int(ADMIN_ID_RAW) if ADMIN_ID_RAW.isdigit() or (ADMIN_ID_RAW.startswith("-") and ADMIN_ID_RAW[1:].isdigit()) else None

bot = Bot(token=TOKEN, parse_mode="HTML")
dp = Dispatcher(bot)

# ========= نصوص الرسائل =========
WELCOME_TEXT = (
    "مرحبًا 👋\n"
    "للاشتراك اضغط الزر التالي، وستظهر لك تفاصيل الدفع.\n"
    "بعد التحويل أرسل صورة إيصال التحويل هنا للتأكيد ✅"
)

PAYMENT_TEXT = (
    "📄 <b>طريقة الاشتراك</b>\n"
    "حوّل الرسوم <b>180 ريال</b> إلى الحساب المحدد:\n"
    "البنك: <b>البنك العربي الوطني</b>\n"
    "الاسم: <b>بدر محمد الجعيد</b>\n"
    "الآيبان: <code>SA1630100991104930184574</code>\n"
    "ثم أرسل صورة إيصال التحويل هنا.\n\n"
    "بعد التأكيد سيُرسل لك رابط دعوة صالح لعضو واحد ✅"
)

RECEIVED_TEXT = (
    "✅ <b>تم استلام التأكيد.</b>\n"
    "جاري انتظار موافقة المشرف…"
)

APPROVED_USER_TEXT = (
    "تم التأكيد ✅\n"
    "هذا رابط الدعوة الخاص بك:"
)

REJECTED_USER_TEXT = (
    "نعتذر، تم رفض الطلب.\n"
    "يرجى التأكد من صحة الإيصال أو التواصل مع الدعم."
)

# زر الاشتراك
def subscribe_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("الاشتراك 🟢", callback_data="subscribe"))
    return kb

# أزرار المشرف (قبول/رفض)
def admin_review_kb(user_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("✅ قبول", callback_data=f"approve:{user_id}"),
        InlineKeyboardButton("❌ رفض", callback_data=f"reject:{user_id}"),
    )
    return kb

# ========= أوامر وتعاملات =========
@dp.message_handler(commands=["start"])
async def cmd_start(message: types.Message):
    await message.reply(WELCOME_TEXT, reply_markup=subscribe_keyboard())

@dp.callback_query_handler(lambda c: c.data == "subscribe")
async def on_subscribe(call: types.CallbackQuery):
    await call.message.answer(PAYMENT_TEXT)

@dp.message_handler(content_types=[types.ContentType.PHOTO, types.ContentType.DOCUMENT])
async def on_receipt(message: types.Message):
    """
    المستخدم يرسل إيصال التحويل (صورة أو مستند):
    - نرسل له إشعار بالاستلام.
    - نُرسل للمشرف نسخة مع أزرار الموافقة/الرفض.
    """
    user = message.from_user
    await message.reply(RECEIVED_TEXT)

    if not ADMIN_ID:
        # لا نرسل رسالة الخطأ القديمة — فقط نُعلم المستخدم أن الطلب بانتظار المراجعة
        logger.warning("ADMIN_ID غير مضبوط؛ لن يتم إشعار مشرف محدد.")
        return

    caption = (
        f"🆕 <b>طلب اشتراك جديد</b>\n"
        f"الاسم: <b>{user.full_name}</b>\n"
        f"المعرف: @{user.username if user.username else '—'}\n"
        f"User ID: <code>{user.id}</code>\n\n"
        f"الرجاء المراجعة ثم اختر الإجراء:"
    )

    try:
        if message.photo:
            # أكبر دقة
            fid = message.photo[-1].file_id
            await bot.send_photo(ADMIN_ID, fid, caption=caption, reply_markup=admin_review_kb(user.id))
        else:
            # مستند
            fid = message.document.file_id
            await bot.send_document(ADMIN_ID, fid, caption=caption, reply_markup=admin_review_kb(user.id))
    except Exception as e:
        logger.exception("فشل إرسال الطلب للمشرف: %s", e)

@dp.callback_query_handler(lambda c: c.data.startswith("approve:") or c.data.startswith("reject:"))
async def on_admin_action(call: types.CallbackQuery):
    """
    المشرف يوافق أو يرفض.
    """
    if call.from_user.id != ADMIN_ID:
        await call.answer("ليست لديك صلاحية على هذا الإجراء.", show_alert=True)
        return

    action, user_id_str = call.data.split(":")
    user_id = int(user_id_str)

    if action == "reject":
        try:
            await bot.send_message(user_id, REJECTED_USER_TEXT)
        except Exception:
            pass
        await call.message.edit_caption(call.message.caption + "\n\n❌ <b>تم الرفض.</b>")
        await call.answer("تم الرفض")
        return

    # قبول
    invite_link_text = None

    # نحاول توليد رابط دعوة لمرة واحدة
    if TARGET_CHAT_ID:
        try:
            # رابط صالح لعضو واحد ولمدة 24 ساعة
            link: ChatInviteLink = await bot.create_chat_invite_link(
                chat_id=TARGET_CHAT_ID,
                name=f"Invite for {user_id}",
                expire_date=int((message_date_to_epoch(call.message.date) + 24 * 3600)),
                member_limit=1,
                creates_join_request=False,
            )
            invite_link_text = link.invite_link
        except TelegramAPIError as e:
            logger.warning("تعذر إنشاء رابط تلقائي: %s", e)

    # fallback
    if not invite_link_text and CHANNEL_LINK:
        invite_link_text = CHANNEL_LINK

    if invite_link_text:
        try:
            await bot.send_message(user_id, f"{APPROVED_USER_TEXT}\n{invite_link_text}")
        except Exception:
            pass
        try:
            await call.message.edit_caption(call.message.caption + "\n\n✅ <b>تمت الموافقة وإرسال الرابط.</b>")
        except Exception:
            pass
        await call.answer("تم القبول وإرسال الرابط ✅", show_alert=False)
    else:
        # لا نرسل للمستخدم شيئًا إضافيًا؛ فقط نُبلغ المشرف
        await call.answer("تعذر إنشاء/إرسال رابط الدعوة. تأكد من صلاحيات البوت أو ضع CHANNEL_LINK.", show_alert=True)

def message_date_to_epoch(dt) -> int:
    """Aiogram يعيد datetime بالـ UTC — نحوله لثواني منذ Epoch"""
    return int(dt.timestamp())

if __name__ == "__main__":
    logger.info("Starting Join bot…")
    executor.start_polling(dp, skip_updates=True)
