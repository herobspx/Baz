# join_bot.py  (Aiogram 2.25.1)

import os
import logging
import asyncio
from datetime import datetime, timedelta
try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo  # احتياط للبيئات القديمة

from aiogram import Bot, Dispatcher, executor, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.utils.callback_data import CallbackData

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("join-bot")

# =======================
# متغيرات البيئة المطلوبة
# =======================
JOIN_TOKEN = os.getenv("JOIN_TOKEN", "").strip()
TARGET_CHAT_ID = int(os.getenv("TARGET_CHAT_ID", "0"))
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

BANK_NAME = os.getenv("BANK_NAME", "البنك العربي الوطني")
ACCOUNT_NAME = os.getenv("ACCOUNT_NAME", "بدر محمد الجعيد")
IBAN_NUMBER = os.getenv("IBAN_NUMBER", "SA1630100991104930184574")

TZ_NAME = os.getenv("TZ_NAME", "Asia/Riyadh")
TZ = ZoneInfo(TZ_NAME)

PLAN_MONTH_DAYS = int(os.getenv("PLAN_MONTH_DAYS", "30"))
PLAN_MONTH_PRICE = int(os.getenv("PLAN_MONTH_PRICE", "180"))
PLAN_2WEEKS_DAYS = int(os.getenv("PLAN_2WEEKS_DAYS", "14"))
PLAN_2WEEKS_PRICE = int(os.getenv("PLAN_2WEEKS_PRICE", "90"))

if not JOIN_TOKEN:
    raise RuntimeError("JOIN_TOKEN is missing. Set it in Render > Environment.")

if not TARGET_CHAT_ID:
    raise RuntimeError("TARGET_CHAT_ID is missing. Set it in Render > Environment.")

if not ADMIN_ID:
    logger.warning("ADMIN_ID غير مضبوط — تأكيد الاشتراكات اليدوي لن يرسل تنبيهات للمشرف.")

bot = Bot(token=JOIN_TOKEN, parse_mode=types.ParseMode.HTML)
dp = Dispatcher(bot)

# =======================
# حالة مؤقتة في الذاكرة
# (يفضّل DB للإنتاج)
# =======================
# تفضيل المستخدم: آخر خطة اختارها (أيام/سعر)
last_choice = {}       # user_id -> {"days": int, "price": int}
# تواريخ انتهاء الاشتراكات
subscriptions = {}     # user_id -> datetime (timezone=TZ)

# CB factories
approve_cb = CallbackData("appr", "uid", "days")   # موافقة مشرف
reject_cb  = CallbackData("rejt", "uid")           # رفض مشرف


# ========= رسائل ثابتة =========
WELCOME_TEXT = (
    "مرحباً 👋\n"
    "هذا البوت يقدّم لك اشتراكاً مباشراً في قناة إشارات عقود SPX.\n"
    "اختر مدة الاشتراك، ادفع عبر التحويل البنكي، ثم أرسل صورة التأكيد — والبوت يتكفّل بالباقي."
)

PROTECTION_NOTE = (
    "🔒 ملاحظة أمان:\n"
    "• لا تشارك توكنات أو روابط دعوة خاصة بك مع أي جهة.\n"
    "• تأكد أن التحويل البنكي على الحساب الصحيح.\n"
    "• لن نطلب كلمات مرور أو رموز تحقق مطلقاً."
)

def main_menu_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📈 الاشتراك الشهري — 180 ر.س", callback_data="plan_month")],
        [InlineKeyboardButton(text="🗓️ اشتراك أسبوعين — 90 ر.س", callback_data="plan_2weeks")],
        [InlineKeyboardButton(text="💳 طريقة الدفع", callback_data="pay_info")],
        [InlineKeyboardButton(text="🔁 تجديد الاشتراك", callback_data="renew")],
        [InlineKeyboardButton(text="📄 حالة اشتراكي", callback_data="status")],
        [InlineKeyboardButton(text="🆘 مساعدة", callback_data="help")]
    ])
    return kb

def payment_instructions(days: int, price: int) -> str:
    return (
        "طريقة الاشتراك 🧾\n"
        f"حوِّل الرسوم (<b>{price} ريال</b>) إلى الحساب المحدد:\n"
        f"• البنك: <b>{BANK_NAME}</b>\n"
        f"• اسم صاحب الحساب: <b>{ACCOUNT_NAME}</b>\n"
        f"• الآيبان: <code>{IBAN_NUMBER}</code>\n\n"
        "ثم أرسل <b>صورة إيصال التحويل</b> هنا.\n"
        f"بعد التأكيد سيُرسَل لك رابط دعوة صالح لعضو واحد لمدة <b>{days} يومًا</b>.\n\n"
        f"{PROTECTION_NOTE}"
    )

def fmt_dt(dt: datetime) -> str:
    # تاريخ بصيغة ودّية بتوقيت السعودية
    return dt.astimezone(TZ).strftime("%Y-%m-%d %H:%M (%Z)")


# ========= أوامر /start =========
@dp.message_handler(commands=["start"])
async def cmd_start(message: types.Message):
    await message.answer(WELCOME_TEXT, reply_markup=main_menu_kb())


# ========= أزرار القائمة =========
@dp.callback_query_handler(lambda c: c.data == "plan_month")
async def choose_month(call: CallbackQuery):
    last_choice[call.from_user.id] = {"days": PLAN_MONTH_DAYS, "price": PLAN_MONTH_PRICE}
    await call.message.answer(payment_instructions(PLAN_MONTH_DAYS, PLAN_MONTH_PRICE))
    await call.answer()

@dp.callback_query_handler(lambda c: c.data == "plan_2weeks")
async def choose_2weeks(call: CallbackQuery):
    last_choice[call.from_user.id] = {"days": PLAN_2WEEKS_DAYS, "price": PLAN_2WEEKS_PRICE}
    await call.message.answer(payment_instructions(PLAN_2WEEKS_DAYS, PLAN_2WEEKS_PRICE))
    await call.answer()

@dp.callback_query_handler(lambda c: c.data == "pay_info")
async def pay_info(call: CallbackQuery):
    txt = (
        "💳 طريقة الدفع\n"
        f"• البنك: <b>{BANK_NAME}</b>\n"
        f"• اسم صاحب الحساب: <b>{ACCOUNT_NAME}</b>\n"
        f"• الآيبان: <code>{IBAN_NUMBER}</code>\n\n"
        "بعد التحويل أرسل صورة الإيصال هنا للمراجعة.\n\n"
        f"{PROTECTION_NOTE}"
    )
    await call.message.answer(txt)
    await call.answer()

@dp.callback_query_handler(lambda c: c.data == "renew")
async def renew(call: CallbackQuery):
    # التجديد = نفس خيارات المدد
    await call.message.answer("اختر مدة التجديد:", reply_markup=main_menu_kb())
    await call.answer()

@dp.callback_query_handler(lambda c: c.data == "status")
async def status(call: CallbackQuery):
    uid = call.from_user.id
    exp = subscriptions.get(uid)
    if exp:
        await call.message.answer(f"📄 حالة اشتراكك\nينتهي في: <b>{fmt_dt(exp)}</b>")
    else:
        await call.message.answer("لا توجد بيانات اشتراك محفوظة.\n"
                                  "إن كنت قد دفعت بالفعل، أرسل صورة الإيصال هنا.")
    await call.answer()

@dp.callback_query_handler(lambda c: c.data == "help")
async def help_btn(call: CallbackQuery):
    await call.message.answer(
        "🆘 مساعدة\n"
        "1) اختر مدة الاشتراك.\n"
        "2) حوّل الرسوم ثم أرسل صورة الإيصال هنا.\n"
        "3) بعد التأكيد يصلك رابط الدعوة.\n\n"
        f"{PROTECTION_NOTE}"
    )
    await call.answer()


# ========= استقبال صورة الإيصال =========
@dp.message_handler(content_types=types.ContentTypes.PHOTO)
async def handle_receipt(message: types.Message):
    uid = message.from_user.id
    choice = last_choice.get(uid, {"days": PLAN_MONTH_DAYS, "price": PLAN_MONTH_PRICE})
    days = choice["days"]
    price = choice["price"]

    await message.reply("✅ تم استلام التأكيد.\n"
                        "جاري انتظار موافقة المشرف...")

    if ADMIN_ID:
        # أرسل للمشرف الصورة + أزرار موافقة/رفض
        caption = (
            f"طلب اشتراك جديد:\n"
            f"المستخدم: <b>{message.from_user.full_name}</b> (ID: <code>{uid}</code>)\n"
            f"الخطة: <b>{days} يوم</b> — <b>{price} ريال</b>\n\n"
            "اعتمد الطلب لإرسال رابط الدعوة."
        )
        kb = InlineKeyboardMarkup().add(
            InlineKeyboardButton("✅ اعتماد", callback_data=approve_cb.new(uid=str(uid), days=str(days))),
            InlineKeyboardButton("❌ رفض", callback_data=reject_cb.new(uid=str(uid)))
        )
        file_id = message.photo[-1].file_id
        try:
            await bot.send_photo(chat_id=ADMIN_ID, photo=file_id, caption=caption, reply_markup=kb, parse_mode="HTML")
        except Exception as e:
            logger.exception("فشل إرسال تنبيه للمشرف: %s", e)


# ========= موافقة/رفض المشرف =========
@dp.callback_query_handler(approve_cb.filter())
async def admin_approve(call: CallbackQuery, callback_data: dict):
    if call.from_user.id != ADMIN_ID:
        await call.answer("غير مسموح", show_alert=True)
        return

    uid = int(callback_data["uid"])
    days = int(callback_data["days"])
    try:
        # إنشاء رابط دعوة صالح لعضو واحد، لمدة قصيرة (10 دقائق)
        invite = await bot.create_chat_invite_link(
            chat_id=TARGET_CHAT_ID,
            member_limit=1,
            expire_date=int((datetime.now(tz=TZ) + timedelta(minutes=10)).timestamp())
        )
        link = invite.invite_link
    except Exception as e:
        logger.exception("فشل إنشاء رابط الدعوة: %s", e)
        await call.answer("تعذّر إنشاء رابط الدعوة", show_alert=True)
        return

    # حفظ موعد الانتهاء
    expiry = datetime.now(tz=TZ) + timedelta(days=days)
    subscriptions[uid] = expiry

    # إرسال الرابط للمستخدم
    try:
        await bot.send_message(
            chat_id=uid,
            text=(
                "✅ تم اعتماد طلبك.\n"
                f"هذا رابط الدعوة (صالح لعضو واحد ولفترة محدودة):\n{link}\n\n"
                f"ستنتهي عضويتك في: <b>{fmt_dt(expiry)}</b>."
            ),
            parse_mode="HTML"
        )
    except Exception as e:
        logger.exception("تعذّر إرسال الرابط للمستخدم: %s", e)

    await call.answer("تم الاعتماد وإرسال الرابط.")
    await call.message.edit_reply_markup()

    # جدولة إزالة العضو عند الانتهاء (أفضل استخدام DB + job runner للإنتاج)
    dp.loop.create_task(remove_when_expired(uid, expiry))


@dp.callback_query_handler(reject_cb.filter())
async def admin_reject(call: CallbackQuery, callback_data: dict):
    if call.from_user.id != ADMIN_ID:
        await call.answer("غير مسموح", show_alert=True)
        return

    uid = int(callback_data["uid"])
    try:
        await bot.send_message(uid, "❌ لم يتم اعتماد الطلب. الرجاء مراجعة بيانات التحويل والمحاولة من جديد.")
    except Exception as e:
        logger.exception("تعذّر إبلاغ المستخدم بالرفض: %s", e)

    await call.answer("تم الرفض.")
    await call.message.edit_reply_markup()


# ========= مهمة إزالة العضو عند الانتهاء + تنبيه قبل يومين =========
async def remove_when_expired(user_id: int, expiry: datetime):
    try:
        # تنبيه قبل يومين
        warn_at = expiry - timedelta(days=2)
        now = datetime.now(tz=TZ)
        if warn_at > now:
            await asyncio.sleep((warn_at - now).total_seconds())
            try:
                await bot.send_message(user_id,
                    f"⏰ تذكير: ستنتهي عضويتك بعد يومين في <b>{fmt_dt(expiry)}</b>.\n"
                    "يمكنك التجديد من زر <b>🔁 تجديد الاشتراك</b>.", parse_mode="HTML")
            except Exception:
                pass

        # الانتظار حتى الانتهاء
        now = datetime.now(tz=TZ)
        if expiry > now:
            await asyncio.sleep((expiry - now).total_seconds())

        # إزالة العضو من المجموعة (إن كان مجموعة/سوبرجروب)
        try:
            await bot.kick_chat_member(TARGET_CHAT_ID, user_id)
            await bot.unban_chat_member(TARGET_CHAT_ID, user_id)  # إلغاء الحظر للسماح بدعوات لاحقة
        except Exception as e:
            logger.warning("تعذّرت الإزالة (قد تكون قناة/أذونات): %s", e)

        subscriptions.pop(user_id, None)
        try:
            await bot.send_message(user_id, "⛔ انتهى اشتراكك وتمت إزالتك من المجموعة. يمكنك التجديد من القائمة.")
        except Exception:
            pass
    except Exception as e:
        logger.exception("خطأ في مهمة الإنهاء: %s", e)


# ========= بدء التشغيل =========
async def on_startup(_):
    logger.info("Starting Join bot…")
    # لا يوجد استرجاع من DB هنا؛ إن رغبت أضف تحميل اشتراكاتك من قاعدة بيانات.


if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True, on_startup=on_startup)
