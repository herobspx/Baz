# join_bot.py
# -*- coding: utf-8 -*-

import os
import asyncio
import logging
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ChatInviteLink
from aiogram.utils.exceptions import TelegramAPIError, BadRequest

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("join-bot")

# ========= الإعدادات من متغيرات البيئة =========
JOIN_TOKEN      = os.getenv("JOIN_TOKEN")            # توكن البوت
TARGET_CHAT_ID  = os.getenv("TARGET_CHAT_ID")        # آي دي الجروب/القناة (مثال: -1003041770290)
ADMIN_ID        = os.getenv("ADMIN_ID")              # آي دي الأدمن الذي يستقبل الطلبات
CHANNEL_LINK    = os.getenv("CHANNEL_LINK")          # (اختياري) رابط ثابت بديل إن لم يقدر البوت ينشئ دعوة
SUB_DAYS        = int(os.getenv("SUB_DAYS", "30"))   # مدة الاشتراك بالأيام

if not JOIN_TOKEN:
    raise RuntimeError("JOIN_TOKEN is missing. Set it in Render > Environment.")
if not TARGET_CHAT_ID:
    raise RuntimeError("TARGET_CHAT_ID is missing. Set it in Render > Environment.")

bot = Bot(token=JOIN_TOKEN, parse_mode="HTML", disable_web_page_preview=True)
dp  = Dispatcher(bot)

# ====== ذاكرة بسيطة لحفظ الاشتراكات (غير دائمة) ======
# { user_id: expiry_datetime }
subscriptions = {}

# ====== رسائل الواجهة (مخصصة بالعربي) ======
WELCOME_TEXT = (
    "مرحبًا 👋\n"
    "للاشتراك اضغط الزر التالي، وستظهر لك طريقة الاشتراك.\n"
    "بعد التحويل أرسل <b>صورة إيصال التحويل هنا</b>."
)

METHOD_TEXT = (
    "<b>طريقة الاشتراك 🧾</b>\n"
    "حوِّل الرسوم <b>180 ريال</b> إلى الحساب المحدد:\n"
    "<b>البنك:</b> البنك العربي الوطني\n"
    "<b>اسم صاحب الحساب:</b> بدر محمد الجعيد\n"
    "<b>الآيبان:</b> <code>SA1630100991104930184574</code>\n"
    "ثم أرسل صورة إيصال التحويل هنا.\n\n"
    "بعد التأكيد سيُرسَل لك رابط دعوة صالح لعضو واحد ✅"
)

SUBSCRIBE_KB = InlineKeyboardMarkup().add(
    InlineKeyboardButton("الاشتراك 🟢", callback_data="subscribe")
)

# ====== أدوات ======
def human(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M")

async def try_create_invite_link() -> str:
    """
    يحاول إنشاء رابط دعوة مؤقت (صالح لمرّة واحدة) للجروب/القناة.
    إن فشل (ليس مشرف/قناة خاصة/الصلاحيات ناقصة)، يستخدم CHANNEL_LINK إن وجد.
    """
    # إن كان هناك رابط ثابت مضاف بالبيئة نُعيده مباشرةً
    if CHANNEL_LINK:
        return CHANNEL_LINK

    try:
        link: ChatInviteLink = await bot.create_chat_invite_link(
            chat_id=int(TARGET_CHAT_ID),
            expire_date=None,           # بدون انتهاء (الإدارة تحذف يدويًا إن رغبت)
            member_limit=1,             # صالح لعضو واحد
            creates_join_request=False  # دعوة مباشرة
        )
        return link.invite_link
    except (BadRequest, TelegramAPIError) as e:
        log.warning(f"Failed to create invite link automatically: {e}")
        # رجوع لرابط ثابت إن تم توفيره لاحقًا
        if CHANNEL_LINK:
            return CHANNEL_LINK
        # إن لم يتوفر، نخبر الأدمن لاحقًا داخل منطق الموافقة
        return ""

async def add_or_invite_user(user_id: int) -> str:
    """
    في القنوات/المجموعات الخاصة: الأفضل إرسال رابط دعوة.
    """
    invite = await try_create_invite_link()
    return invite

# ====== أوامر ومعالجات ======
@dp.message_handler(commands=["start"])
async def cmd_start(message: types.Message):
    await message.answer(WELCOME_TEXT, reply_markup=SUBSCRIBE_KB)

@dp.callback_query_handler(lambda c: c.data == "subscribe")
async def cb_subscribe(call: types.CallbackQuery):
    await call.message.answer(METHOD_TEXT)

@dp.message_handler(content_types=types.ContentType.PHOTO)
async def on_payment_proof(message: types.Message):
    """
    المستخدم يرسل صورة إيصال التحويل:
    - نؤكد الاستلام للمستخدم.
    - نرسل للإدمن رسالة تحتوي أزرار (موافقة/رفض).
    """
    user = message.from_user
    await message.reply("✅ تم استلام التأكيد.\nجاري انتظار موافقة المشرف…")

    if not ADMIN_ID:
        # لا نوقف التدفق تمامًا، لكن نُعلم المستخدم أن الموافقة اليدوية غير مفعلة
        await message.answer(
            "ℹ️ لا يمكن تأكيد الطلب تلقائيًا، لم يتم ضبط ADMIN_ID.\n"
            "سيتم مراجعته يدويًا."
        )
        return

    kb = InlineKeyboardMarkup().add(
        InlineKeyboardButton("✅ موافقة", callback_data=f"approve:{user.id}"),
        InlineKeyboardButton("❌ رفض", callback_data=f"reject:{user.id}")
    )

    caption = (
        f"<b>طلب اشتراك جديد</b>\n"
        f"العميل: <a href='tg://user?id={user.id}'>{user.full_name}</a> (ID: <code>{user.id}</code>)\n"
        f"التاريخ: {human(datetime.utcnow())} UTC\n\n"
        f"الرجاء التأكيد."
    )
    # إعادة إرسال صورة الإيصال للأدمن مع الأزرار
    photo = message.photo[-1].file_id
    try:
        await bot.send_photo(
            chat_id=int(ADMIN_ID),
            photo=photo,
            caption=caption,
            reply_markup=kb
        )
    except TelegramAPIError:
        # لو ما قدر يرسل صورة، يرسل نص
        await bot.send_message(
            chat_id=int(ADMIN_ID),
            text=caption,
            reply_markup=kb
        )

@dp.callback_query_handler(lambda c: c.data.startswith("approve:"))
async def cb_approve(call: types.CallbackQuery):
    """
    الأدمن ضغط موافقة:
    - نحسب نهاية الاشتراك.
    - نرسل للمستخدم رابط دعوة.
    - نخزن وقت الانتهاء في الذاكرة.
    """
    if not ADMIN_ID or call.from_user.id != int(ADMIN_ID):
        await call.answer("غير مصرح.", show_alert=True)
        return

    target_user_id = int(call.data.split(":")[1])
    expires_at = datetime.utcnow() + timedelta(days=SUB_DAYS)
    subscriptions[target_user_id] = expires_at

    invite_link = await add_or_invite_user(target_user_id)
    if not invite_link:
        await call.message.answer("⚠️ تعذّر إنشاء رابط الدعوة تلقائيًا. تأكد من صلاحيات البوت أو أضف CHANNEL_LINK.")
        await bot.send_message(
            target_user_id,
            "⚠️ حدثت مشكلة في إنشاء رابط الدعوة تلقائيًا. سيتم إرسال الرابط لاحقًا بعد معالجة المشرف."
        )
        await call.answer("تم تسجيل الموافقة ولكن فشل إنشاء الرابط.", show_alert=True)
        return

    await bot.send_message(
        target_user_id,
        f"🎟️ تم تأكيد اشتراكك!\n"
        f"رابط الدعوة (صالح لعضو واحد):\n{invite_link}\n\n"
        f"📅 ينتهي الاشتراك في: {human(expires_at)} UTC"
    )
    await call.answer("تمت الموافقة وإرسال الرابط ✅", show_alert=False)

@dp.callback_query_handler(lambda c: c.data.startswith("reject:"))
async def cb_reject(call: types.CallbackQuery):
    if not ADMIN_ID or call.from_user.id != int(ADMIN_ID):
        await call.answer("غير مصرح.", show_alert=True)
        return
    target_user_id = int(call.data.split(":")[1])
    subscriptions.pop(target_user_id, None)
    await bot.send_message(target_user_id, "❌ تم رفض الطلب. إن كان هناك خطأ تواصل مع الدعم.")
    await call.answer("تم الرفض.", show_alert=False)

# ====== مراقبة صلاحية الاشتراكات ======
async def expiry_watcher():
    """
    يفحص كل دقيقة المستخدمين المنتهية اشتراكاتهم ويُبلغ الأدمن (إزالة العضو تتم يدويًا عبر التليجرام).
    يمكن لاحقًا ربطه بإزالة تلقائية إن كان البوت له صلاحية مناسبة ومجموعة (وليس قناة).
    """
    while True:
        try:
            now = datetime.utcnow()
            to_remove = [uid for uid, exp in subscriptions.items() if exp <= now]
            for uid in to_remove:
                subscriptions.pop(uid, None)
                # مجرد تنبيه — الإزالة الفعلية من القنوات الخاصة غير مدعومة مباشرة عبر البوت دائمًا.
                if ADMIN_ID:
                    await bot.send_message(
                        int(ADMIN_ID),
                        f"⌛ انتهى اشتراك المستخدم ID: <code>{uid}</code>. الرجاء إزالة الوصول إذا كان عضوًا."
                    )
        except Exception as e:
            log.error(f"expiry_watcher error: {e}")
        await asyncio.sleep(60)

# ====== تشغيل البوت ======
async def on_startup(dp: Dispatcher):
    try:
        if ADMIN_ID:
            await bot.send_message(int(ADMIN_ID), "✅ Bot started.")
    except Exception:
        pass
    # المهم: استخدام asyncio.create_task بدلاً من dp.loop.create_task
    asyncio.create_task(expiry_watcher())

if __name__ == "__main__":
    log.info("Starting Join bot…")
    executor.start_polling(dp, skip_updates=True, on_startup=on_startup)
