# -*- coding: utf-8 -*-
import os
import logging
from datetime import timedelta, datetime

from aiogram import Bot, Dispatcher, F
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext

# -------------------- إعدادات وقراءة المتغيرات --------------------
JOIN_TOKEN = os.getenv("JOIN_TOKEN")           # توكن بوت الاشتراك
TARGET_CHAT_ID = os.getenv("TARGET_CHAT_ID")   # رقم القناة/المجموعة الهدف
CHANNEL_LINK = os.getenv("CHANNEL_LINK")       # رابط عام احتياطي (اختياري)

if not JOIN_TOKEN:
    raise RuntimeError("JOIN_TOKEN is missing. Set it in Render > Environment.")

if not TARGET_CHAT_ID:
    raise RuntimeError("TARGET_CHAT_ID is missing. Set it in Render > Environment.")

try:
    TARGET_CHAT_ID = int(TARGET_CHAT_ID)
except ValueError:
    raise RuntimeError("TARGET_CHAT_ID must be an integer (e.g. -1001234567890).")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("join-bot")

bot = Bot(
    token=JOIN_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher(storage=MemoryStorage())

# -------------------- الحالات --------------------
class JoinFlow(StatesGroup):
    waiting_receipt = State()  # انتظار صورة إيصال التحويل

# -------------------- أدوات --------------------
def subscribe_button() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.add(InlineKeyboardButton(text="🟢 الاشتراك", callback_data="subscribe"))
    return kb.as_markup()

async def send_payment_instructions(event):
    text = (
        "💳 <b>طريقة الاشتراك</b>\n"
        "حوّل الرسوم إلى الحساب المحدد (البنك العربي الوطني)\n"
        "<code>SA163010009911049301084574</code>\n"
        "ثم أرسل <b>صورة إيصال التحويل هنا</b>.\n\n"
        "بعد التأكيد سترسل لك المنظومة <b>رابط دعوة صالح لعضو واحد ✅</b>."
    )
    await event.answer(text) if isinstance(event, CallbackQuery) else await event.reply(text)

async def create_invite_link():
    """
    محاولة إنشاء رابط دعوة لعضو واحد، وإن فشلت نرجع الرابط الاحتياطي CHANNEL_LINK إن وجد.
    """
    try:
        # مدة صلاحية 24 ساعة (اختياري)
        expire_date = datetime.utcnow() + timedelta(hours=24)
        link = await bot.create_chat_invite_link(
            chat_id=TARGET_CHAT_ID,
            name="AutoInvite by JoinBot",
            expire_date=expire_date,
            member_limit=1,
            creates_join_request=False
        )
        return link.invite_link
    except TelegramBadRequest as e:
        logger.warning(f"Failed to create invite link automatically: {e}")
        # fallback إلى الرابط العام إن تم وضعه
        if CHANNEL_LINK:
            return CHANNEL_LINK
        # لا يوجد رابط بديل
        return None

# -------------------- المعالجات --------------------
@dp.message(F.text == "/start")
async def on_start(msg: Message, state: FSMContext):
    await state.clear()
    welcome = (
        "مرحبًا 👋\n"
        "للاشتراك اضغط الزر التالي، وستظهر لك طريقة الاشتراك.\n"
        "بعد التحويل أرسل صورة تأكيد هنا."
    )
    await msg.answer(welcome, reply_markup=subscribe_button())

@dp.callback_query(F.data == "subscribe")
async def on_subscribe(cb: CallbackQuery, state: FSMContext):
    await send_payment_instructions(cb)
    await state.set_state(JoinFlow.waiting_receipt)
    await cb.answer()  # لإغلاق الدائرة الصغيرة

@dp.message(JoinFlow.waiting_receipt, F.photo)
async def on_receipt(msg: Message, state: FSMContext):
    await msg.reply("✅ تم استلام التأكيد.\nجاري إنشاء رابط الدعوة…")
    invite = await create_invite_link()
    if invite:
        await msg.answer(
            "تفضل رابط الدعوة (صالح لعضو واحد):\n"
            f"<a href=\"{invite}\">{invite}</a>\n\n"
            "إذا لم يعمل الرابط جرّب فتحه مباشرة من تيليجرام."
        )
        await state.clear()
    else:
        await msg.answer(
            "⚠️ تعذّر إنشاء رابط الدعوة تلقائيًا ولا يوجد رابط احتياطي CHANNEL_LINK.\n"
            "تأكد من أن البوت مشرف في القناة/المجموعة مع صلاحية إنشاء الروابط، "
            "أو أضف متغيّر <code>CHANNEL_LINK</code> في Render وأعد المحاولة."
        )

@dp.message(JoinFlow.waiting_receipt)
async def on_non_photo_in_wait(msg: Message):
    await msg.reply("أرسل <b>صورة إيصال التحويل</b> من فضلك.")

# احتياط: أي رسالة أخرى
@dp.message()
async def fallback(msg: Message):
    await msg.answer("أرسل /start لبدء الاشتراك.")

# -------------------- التشغيل --------------------
if __name__ == "__main__":
    dp.run_polling(bot)
