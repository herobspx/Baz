import os
import asyncio
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import CommandStart
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)

# ========= الإعدادات من المتغيرات =========
TOKEN = os.getenv("JOIN_TOKEN") or os.getenv("BOT_TOKEN")
if not TOKEN:
    raise RuntimeError("JOIN_TOKEN مفقود. ضعه في Render > Settings > Environment.")

# ملاحظة: المجموعة/القناة الهدف
# مثال: -1003041770290
TARGET_CHAT_ID_ENV = os.getenv("TARGET_CHAT_ID")
TARGET_CHAT_ID = int(TARGET_CHAT_ID_ENV) if TARGET_CHAT_ID_ENV else None

# رابط بديل (اختياري) في حال تعذّر إنشاء رابط تلقائي
FALLBACK_CHANNEL_LINK = os.getenv("CHANNEL_LINK")

# نص طريقة الاشتراك (عدّل بما يناسبك)
SUBSCRIBE_TEXT = (
    "💳 **طريقة الاشتراك**\n"
    "حوّل الرسوم إلى الحساب المحدد (البنك العربي الوطني)\n"
    "**الآيبان:** `SA16301000991104930184574`\n\n"
    "ثم **أرسل صورة إيصال التحويل هنا**.\n"
    "بعد التأكيد سترسل لك المنظومة **رابط دعوة صالح لعضو واحد** ✅"
)

WELCOME_TEXT = (
    "مرحباً 👋\n"
    "للاشتراك اضغط الزر التالي، وستظهر لك طريقة الاشتراك.\n"
    "بعد التحويل أرسل **صورة تأكيد** هنا."
)

# ====== أدوات مساعدة ======
MAX_TG_LEN = 4000

async def safe_send_text(bot: Bot, chat_id: int, text: str, **kwargs):
    """
    تلخيص/تجزئة الرسائل الطويلة حتى لا نقع في MESSAGE_TOO_LONG.
    """
    chunks = [text[i:i+MAX_TG_LEN] for i in range(0, len(text), MAX_TG_LEN)] or [text]
    for chunk in chunks:
        await bot.send_message(chat_id, chunk, **kwargs)

# ====== الواجهة (ازرار) ======
def subscribe_keyboard() -> InlineKeyboardMarkup:
    kb = [
        [InlineKeyboardButton(text="الاشتراك 🟢", callback_data="subscribe")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

# ====== الراوتر والهاندلرز ======
router = Router()

@router.message(CommandStart())
async def on_start(message: Message, bot: Bot):
    await safe_send_text(bot, message.chat.id, WELCOME_TEXT)
    await bot.send_message(message.chat.id, "الاشتراك", reply_markup=subscribe_keyboard())

@router.callback_query(F.data == "subscribe")
async def on_subscribe(cb: CallbackQuery, bot: Bot):
    await cb.answer()
    await safe_send_text(
        bot,
        cb.message.chat.id,
        SUBSCRIBE_TEXT,
        parse_mode="Markdown"
    )

@router.message(F.photo)
async def on_payment_proof(msg: Message, bot: Bot):
    """
    عند استلام صورة: إنشاء رابط دعوة صالح لعضو واحد لمدة ساعة، وإرساله للمستخدم.
    يحتاج البوت صلاحية إنشاء روابط دعوة في المجموعة/القناة الهدف.
    """
    user_id = msg.from_user.id

    # تأكيد استلام الصورة
    await bot.send_message(user_id, "✅ تم استلام التأكيد. جارٍ إنشاء رابط الدعوة…")

    link_text = None
    error_reason = None

    # محاولة إنشاء رابط دعوة تلقائي (تحتاج TARGET_CHAT_ID + صلاحيات مشرف)
    if TARGET_CHAT_ID:
        try:
            # صلاحية: البوت لازم يكون Admin وله إذن إضافة مستخدمين/إنشاء روابط
            expire_date = datetime.utcnow() + timedelta(hours=1)
            invite = await bot.create_chat_invite_link(
                chat_id=TARGET_CHAT_ID,
                expire_date=expire_date,
                member_limit=1,   # صالح لعضو واحد
                creates_join_request=False
            )
            link_text = invite.invite_link
        except Exception as e:
            error_reason = str(e)

    # استخدام رابط بديل إن وجد
    if not link_text and FALLBACK_CHANNEL_LINK:
        link_text = FALLBACK_CHANNEL_LINK

    # الرد النهائي
    if link_text:
        await bot.send_message(
            user_id,
            f"🎟️ هذا رابط الدعوة:\n{link_text}\n\n"
            "ملاحظة: إن كان رابطاً تلقائياً فهو **صالح لعضو واحد ولمدة ساعة**.",
            disable_web_page_preview=True
        )
    else:
        # لم ننجح بإنشاء الرابط ولا يوجد بديل
        details = f"\n\nتفاصيل تقنية: {error_reason}" if error_reason else ""
        await bot.send_message(
            user_id,
            "❌ تعذّر إنشاء رابط الدعوة تلقائياً.\n"
            "تأكد أن البوت **مشرف** في القناة/المجموعة الهدف ولديه صلاحية إنشاء روابط دعوة،\n"
            "أو ضع متغير بيئة بديل `CHANNEL_LINK` في Render." + details
        )

# ====== التشغيل ======
async def main():
    bot = Bot(TOKEN)
    dp = Dispatcher()
    dp.include_router(router)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
