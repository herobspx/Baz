import os
import asyncio
import logging
from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.exceptions import TelegramBadRequest

logging.basicConfig(level=logging.INFO)

# ====== الإعدادات من Environment ======
TOKEN          = os.getenv("JOIN_TOKEN")
TARGET_CHAT_ID = int(os.getenv("TARGET_CHAT_ID"))  # مثال: -100xxxxxxxxxx
ADMIN_CHAT_ID  = int(os.getenv("ADMIN_CHAT_ID", "0"))  # رقم تيليجرام تبعك
CHANNEL_LINK   = os.getenv("CHANNEL_LINK")  # اختياري: رابط دعوة جاهز
IBAN           = os.getenv("IBAN", "SA16301000991104930184574")  # عدّله من Render

if not TOKEN:
    raise RuntimeError("JOIN_TOKEN is missing. Set it in Render > Environment.")
if not TARGET_CHAT_ID:
    raise RuntimeError("TARGET_CHAT_ID is missing. Set it in Render > Environment.")
if not ADMIN_CHAT_ID:
    raise RuntimeError("ADMIN_CHAT_ID is missing. Set it in Render > Environment.")

bot = Bot(token=TOKEN, parse_mode="HTML")
dp  = Dispatcher(bot)

# تتبع من ينتظر إرسال الإيصال
WAITING_PROOF = set()
# طلبات قيد المراجعة: {request_id: {"user_id": ..., "proof_msg_id": ..., "chat_id": ...}}
PENDING = {}

# ====== الواجهات ======
def start_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("الاشتراك 🟢", callback_data="subscribe"))
    return kb

PAY_TEXT = (
    "💳 <b>طريقة الاشتراك</b>\n"
    f"حوِّل الرسوم ١٨٠ ريال إلى الحساب:\n"
    f"<b>IBAN:</b> <code>{IBAN}</code>\n\n"
    "ثم أرسل <b>صورة</b> إيصال التحويل هنا.\n"
)

OK_SENT_TO_ADMIN = "✅ تم استلام الإيصال. بانتظار اعتماد المشرف…"
REJECTED_TEXT     = "❌ تم رفض الطلب. إذا كان هناك خطأ راسل الدعم."
APPROVED_TEXT     = "✅ تم اعتماد الطلب. هذا رابط الدعوة (صالح لعضو واحد):\n{link}"
NEED_SUBSCRIBE_TEXT = "ℹ️ اضغط زر <b>الاشتراك</b> أولًا، ثم أرسل صورة إيصال التحويل."

FAILED_AUTO_LINK_TEXT = (
    "⚠️ تعذّر إنشاء رابط دعوة تلقائي. تأكد أن البوت مشرف ولديه صلاحية الدعوة."
)

# ====== إنشاء رابط دعوة لمرة واحدة ======
async def make_invite_link() -> str:
    try:
        link_obj = await bot.create_chat_invite_link(
            chat_id=TARGET_CHAT_ID,
            member_limit=1  # دعوة لعضو واحد
        )
        return link_obj.invite_link
    except TelegramBadRequest as e:
        logging.warning(f"Failed to create invite link automatically: {e}")
        if CHANNEL_LINK:
            return CHANNEL_LINK.strip()
        return None

# ====== Handlers ======

@dp.message_handler(commands=["start"])
async def cmd_start(msg: types.Message):
    WAITING_PROOF.discard(msg.from_user.id)
    text = (
        "مرحباً 👋\n"
        "للاشتراك اضغط الزر التالي وستظهر لك طريقة الاشتراك.\n"
        "بعد التحويل أرسل صورة الإيصال هنا.\n"
    )
    await msg.answer(text, reply_markup=start_kb())

@dp.callback_query_handler(lambda c: c.data == "subscribe")
async def on_subscribe(cb: types.CallbackQuery):
    WAITING_PROOF.add(cb.from_user.id)
    await cb.message.answer(PAY_TEXT)
    await cb.answer()

@dp.message_handler(content_types=types.ContentTypes.PHOTO)
async def on_photo(msg: types.Message):
    # يقبل الصور فقط إذا المستخدم دخل وضع الاشتراك
    if msg.from_user.id not in WAITING_PROOF:
        await msg.answer(NEED_SUBSCRIBE_TEXT)
        return

    # خزّن طلب بانتظار المراجعة
    req_id = f"{msg.chat.id}:{msg.message_id}"
    PENDING[req_id] = {
        "user_id": msg.from_user.id,
        "proof_msg_id": msg.message_id,
        "chat_id": msg.chat.id,
    }

    # أرسل للمشرف للمراجعة مع أزرار قبول/رفض
    approve_kb = InlineKeyboardMarkup().add(
        InlineKeyboardButton("✅ قبول", callback_data=f"approve:{req_id}"),
        InlineKeyboardButton("❌ رفض",  callback_data=f"reject:{req_id}")
    )

    caption = (
        f"📥 <b>طلب اشتراك جديد</b>\n"
        f"👤 المستخدم: <a href='tg://user?id={msg.from_user.id}'>{msg.from_user.first_name}</a>\n"
        f"🆔 ID: <code>{msg.from_user.id}</code>\n\n"
        "اعتمد الطلب أو ارفضه:"
    )

    # أعد إرسال أعلى دقة من الصورة
    file_id = msg.photo[-1].file_id
    await bot.send_photo(
        chat_id=ADMIN_CHAT_ID,
        photo=file_id,
        caption=caption,
        reply_markup=approve_kb,
        parse_mode="HTML",
    )

    await msg.answer(OK_SENT_TO_ADMIN)

@dp.callback_query_handler(lambda c: c.data.startswith("approve:") or c.data.startswith("reject:"))
async def admin_decision(cb: types.CallbackQuery):
    # السماح فقط لـ ADMIN_CHAT_ID
    if cb.from_user.id != ADMIN_CHAT_ID:
        await cb.answer("غير مخوّل.", show_alert=True)
        return

    action, req_id = cb.data.split(":", 1)
    req = PENDING.get(req_id)
    if not req:
        await cb.answer("الطلب غير موجود/منتهي.", show_alert=True)
        return

    user_id = req["user_id"]

    if action == "reject":
        await bot.send_message(user_id, REJECTED_TEXT)
        await cb.message.edit_caption(cb.message.caption + "\n\n❌ تم الرفض.")
        PENDING.pop(req_id, None)
        await cb.answer("تم الرفض.")
        return

    # قبول: أنشئ الرابط وأرسله للمستخدم
    link = await make_invite_link()
    if not link:
        await bot.send_message(user_id, FAILED_AUTO_LINK_TEXT + (f"\nبديل: {CHANNEL_LINK}" if CHANNEL_LINK else ""))
        await cb.message.edit_caption(cb.message.caption + "\n\n⚠️ تعذّر إنشاء رابط تلقائي.")
        PENDING.pop(req_id, None)
        await cb.answer("تعذّر إنشاء الرابط.")
        return

    await bot.send_message(user_id, APPROVED_TEXT.format(link=link))
    await cb.message.edit_caption(cb.message.caption + "\n\n✅ تم القبول وإرسال الرابط.")
    PENDING.pop(req_id, None)
    # خرج المستخدم من وضع الانتظار
    WAITING_PROOF.discard(user_id)
    await cb.answer("تم الإرسال.")

@dp.message_handler()
async def on_text(msg: types.Message):
    if msg.from_user.id in WAITING_PROOF:
        await msg.answer("📷 أرسل <b>صورة</b> إيصال التحويل لإتمام الطلب.")
    else:
        await msg.answer("اكتب /start ثم اضغط زر <b>الاشتراك</b>.")

# ====== تشغيل البوت ======
async def main():
    logging.info("Starting Join bot…")
    me = await bot.get_me()
    logging.info(f"Bot: {me.first_name} [@{me.username}]")
    await dp.start_polling()

if __name__ == "__main__":
    asyncio.run(main())
