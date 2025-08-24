# -*- coding: utf-8 -*-
import os
import time
import sqlite3
import asyncio
import logging
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor
from aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton, ParseMode
)

# ================== الإعدادات من المتغيرات البيئية ==================
BOT_TOKEN     = os.getenv("JOIN_TOKEN")
TARGET_CHAT_ID = os.getenv("TARGET_CHAT_ID")  # مثال: -1001234567890 (مجموعة/سوبرجروب)
ADMIN_ID       = int(os.getenv("ADMIN_ID", "0"))  # آي دي المشرف الذي يستقبل الطلبات
CHANNEL_LINK   = os.getenv("CHANNEL_LINK", "")    # رابط بديل ثابت عند فشل إنشاء رابط تلقائي

BANK_NAME      = os.getenv("BANK_NAME", "البنك العربي الوطني")
ACCOUNT_NAME   = os.getenv("ACCOUNT_NAME", "بدر محمد الجعيد")
IBAN           = os.getenv("IBAN", "SA1630100991104930184574")

DEFAULT_DAYS   = int(os.getenv("DEFAULT_SUB_DAYS", "30"))  # مدة الاشتراك الافتراضية

if not BOT_TOKEN:
    raise RuntimeError("JOIN_TOKEN مفقود. ضعه في Render > Environment.")

if not TARGET_CHAT_ID:
    raise RuntimeError("TARGET_CHAT_ID مفقود. ضعه في Render > Environment.")

try:
    TARGET_CHAT_ID = int(TARGET_CHAT_ID)
except Exception:
    raise RuntimeError("TARGET_CHAT_ID يجب أن يكون رقمًا (مثل -100xxxxxxxxxx).")

# ================== ضبط اللوج ==================
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("join-bot")

# ================== تهيئة البوت ==================
bot = Bot(token=BOT_TOKEN, parse_mode=ParseMode.HTML)
dp = Dispatcher(bot)

# ================== قاعدة البيانات ==================
DB_PATH = os.path.join(os.path.dirname(__file__), "data.db")
conn = sqlite3.connect(DB_PATH, check_same_thread=False)
cur  = conn.cursor()
cur.execute("""
CREATE TABLE IF NOT EXISTS subscriptions (
    user_id    INTEGER PRIMARY KEY,
    expires_at INTEGER NOT NULL
)
""")
cur.execute("""
CREATE TABLE IF NOT EXISTS pending (
    user_id    INTEGER PRIMARY KEY,
    msg_id     INTEGER,
    sent_at    INTEGER NOT NULL
)
""")
conn.commit()

def set_subscription(user_id: int, days: int):
    expires = int(time.time()) + days * 86400
    cur.execute("INSERT OR REPLACE INTO subscriptions(user_id, expires_at) VALUES(?,?)",
                (user_id, expires))
    conn.commit()
    return expires

def get_subscription(user_id: int):
    row = cur.execute("SELECT expires_at FROM subscriptions WHERE user_id=?",
                      (user_id,)).fetchone()
    return row[0] if row else None

def remove_subscription(user_id: int):
    cur.execute("DELETE FROM subscriptions WHERE user_id=?", (user_id,))
    conn.commit()

# ================== الرسائل الجاهزة ==================
WELCOME_TEXT = (
    "مرحباً 👋\n"
    "للاشتراك اضغط الزر التالي، وستظهر لك طريقة الاشتراك.\n"
    "بعد التحويل أرسل <b>صورة إيصال التحويل هنا</b>."
)

def payment_text():
    return (
        "طريقة الاشتراك 🧾\n"
        f"حوِّل الرسوم <b>180 ريال</b> إلى الحساب المحدد:\n"
        f"<b>البنك:</b> {BANK_NAME}\n"
        f"<b>اسم صاحب الحساب:</b> {ACCOUNT_NAME}\n"
        f"<b>الآيبان:</b> <code>{IBAN}</code>\n\n"
        "ثم أرسل <b>صورة إيصال التحويل هنا</b>.\n\n"
        "بعد التأكيد سيُرسَل لك رابط دعوة صالح لعضو واحد ✅"
    )

def format_exp(ts: int):
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")

subscribe_kb = InlineKeyboardMarkup().add(
    InlineKeyboardButton("الاشتراك 🟢", callback_data="open_payment")
)

# ================== الأوامر العامة ==================
@dp.message_handler(commands=["start", "help"])
async def start_cmd(msg: types.Message):
    await msg.answer(WELCOME_TEXT, reply_markup=subscribe_kb)

@dp.callback_query_handler(lambda c: c.data == "open_payment")
async def show_payment(call: types.CallbackQuery):
    await call.message.answer(payment_text())

# ================== استقبال إيصالات التحويل ==================
@dp.message_handler(content_types=types.ContentTypes.PHOTO)
async def handle_receipt(msg: types.Message):
    user = msg.from_user
    cap = (msg.caption or "").strip()
    # نسجّل الطلب كـ pending
    cur.execute("INSERT OR REPLACE INTO pending(user_id, msg_id, sent_at) VALUES(?,?,?)",
                (user.id, msg.message_id, int(time.time())))
    conn.commit()

    # نرسل للمستخدم تأكيد الاستلام
    await msg.reply("✅ تم استلام التأكيد.\nجاري انتظار موافقة المشرف…")

    # نُرسِل للمشرف الصورة مع أزرار الموافقة / الرفض
    kb = InlineKeyboardMarkup(row_width=3)
    kb.add(
        InlineKeyboardButton("قبول 7 أيام", callback_data=f"approve:{user.id}:7"),
        InlineKeyboardButton("قبول 30 يومًا", callback_data=f"approve:{user.id}:30"),
        InlineKeyboardButton("رفض", callback_data=f"reject:{user.id}")
    )
    text = (
        f"💳 <b>طلب اشتراك جديد</b>\n"
        f"العضو: <a href='tg://user?id={user.id}'>{user.full_name}</a> (<code>{user.id}</code>)\n"
        f"نص الإيصال: {cap if cap else '—'}\n"
        f"أرسل الموافقة مع المدة:"
    )
    try:
        await bot.send_photo(
            chat_id=ADMIN_ID,
            photo=msg.photo[-1].file_id,
            caption=text,
            reply_markup=kb,
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        log.warning(f"لم أتمكن من إرسال الطلب للمشرف: {e}")

# ================== أزرار المشرف (اعتماد/رفض) ==================
def is_admin(user_id: int) -> bool:
    return ADMIN_ID and (user_id == ADMIN_ID)

@dp.callback_query_handler(lambda c: c.data.startswith("approve:"))
async def approve_cb(call: types.CallbackQuery):
    if not is_admin(call.from_user.id):
        return await call.answer("غير مخوّل.", show_alert=True)

    _, uid_str, days_str = call.data.split(":")
    target_uid = int(uid_str)
    days = int(days_str)

    # نحاول إنشاء رابط دعوة لمرة واحدة مع انتهاء صلاحية 24 ساعة
    invite_link = None
    try:
        expire_date = int(time.time()) + 24 * 3600
        link = await bot.create_chat_invite_link(
            chat_id=TARGET_CHAT_ID, expire_date=expire_date, member_limit=1,
            name=f"Auto-{target_uid}"
        )
        invite_link = link.invite_link
    except Exception as e:
        log.warning(f"فشل إنشاء رابط تلقائي: {e}")
        if CHANNEL_LINK:
            invite_link = CHANNEL_LINK

    # نخزن الاشتراك
    exp = set_subscription(target_uid, days)

    # نخبر المشرف
    await call.message.reply(
        f"✅ تم اعتماد اشتراك <code>{target_uid}</code> لمدة {days} يومًا.\n"
        f"ينتهي في: <code>{format_exp(exp)}</code>\n"
        f"{'🔗 أُنشئ رابط تلقائي وأُرسل للمستخدم.' if invite_link else '⚠️ لم أستطع إنشاء رابط.'}"
    )

    # نرسل للمستخدم
    try:
        if invite_link:
            await bot.send_message(
                target_uid,
                "✅ تم تأكيد اشتراكك.\n"
                "اضغط على الرابط التالي للانضمام (صالح لعضو واحد):\n"
                f"{invite_link}"
            )
        else:
            await bot.send_message(
                target_uid,
                "✅ تم تأكيد اشتراكك.\n"
                "تعذّر إنشاء رابط تلقائي. سيتواصل معك المشرف بالرابط قريبًا."
            )
    except Exception as e:
        await call.message.reply(f"تعذّر مراسلة المستخدم: {e}")

    await call.answer("تم.")

@dp.callback_query_handler(lambda c: c.data.startswith("reject:"))
async def reject_cb(call: types.CallbackQuery):
    if not is_admin(call.from_user.id):
        return await call.answer("غير مخوّل.", show_alert=True)

    _, uid_str = call.data.split(":")
    target_uid = int(uid_str)
    remove_subscription(target_uid)

    try:
        await bot.send_message(target_uid, "❌ تم رفض الطلب. تأكد من بيانات التحويل وحاول مجددًا.")
    except:
        pass

    await call.message.reply(f"تم رفض طلب <code>{target_uid}</code>.")
    await call.answer("تم.")

# ================== أوامر المشرف ==================
@dp.message_handler(commands=["users"])
async def list_users(msg: types.Message):
    if not is_admin(msg.from_user.id):
        return
    rows = cur.execute("SELECT user_id, expires_at FROM subscriptions ORDER BY expires_at ASC LIMIT 50").fetchall()
    if not rows:
        return await msg.reply("لا يوجد مشتركون حالياً.")
    lines = ["<b>المشتركون:</b>"]
    now = int(time.time())
    for uid, exp in rows:
        status = "✅ ساري" if exp > now else "⛔️ منتهي"
        lines.append(f"- <code>{uid}</code> ينتهي: <code>{format_exp(exp)}</code> {status}")
    await msg.reply("\n".join(lines), parse_mode=ParseMode.HTML)

@dp.message_handler(commands=["renew"])
async def renew_cmd(msg: types.Message):
    if not is_admin(msg.from_user.id):
        return
    try:
        _, uid_str, days_str = msg.text.strip().split()
        uid = int(uid_str); days = int(days_str)
    except:
        return await msg.reply("الاستخدام: /renew USER_ID DAYS")
    current = get_subscription(uid) or int(time.time())
    new_exp = current + days * 86400
    cur.execute("INSERT OR REPLACE INTO subscriptions(user_id, expires_at) VALUES(?,?)", (uid, new_exp))
    conn.commit()
    await msg.reply(f"تم التجديد لـ <code>{uid}</code> حتى {format_exp(new_exp)}.", parse_mode=ParseMode.HTML)

@dp.message_handler(commands=["ban"])
async def ban_cmd(msg: types.Message):
    if not is_admin(msg.from_user.id):
        return
    try:
        _, uid_str = msg.text.strip().split()
        uid = int(uid_str)
    except:
        return await msg.reply("الاستخدام: /ban USER_ID")
    # محاولة إزالة من المجموعة
    try:
        # الأسماء تختلف بين الإصدارات؛ نحاول الطريقتين
        try:
            await bot.kick_chat_member(TARGET_CHAT_ID, uid)
        except:
            await bot.ban_chat_member(TARGET_CHAT_ID, uid)
    except Exception as e:
        await msg.reply(f"تعذّر إزالة المستخدم: {e}")
    remove_subscription(uid)
    await msg.reply(f"تم حظر <code>{uid}</code> وإزالة اشتراكه.", parse_mode=ParseMode.HTML)

# ================== مهمة دورية: إزالة المنتهي اشتراكهم ==================
async def expiry_watcher():
    await bot.wait_until_ready() if hasattr(bot, "wait_until_ready") else asyncio.sleep(0)
    while True:
        try:
            now = int(time.time())
            rows = cur.execute("SELECT user_id FROM subscriptions WHERE expires_at <= ?", (now,)).fetchall()
            for (uid,) in rows:
                try:
                    try:
                        await bot.kick_chat_member(TARGET_CHAT_ID, uid)
                    except:
                        await bot.ban_chat_member(TARGET_CHAT_ID, uid)
                except Exception as e:
                    log.info(f"تعذرت إزالة {uid}: {e}")
                remove_subscription(uid)
                try:
                    await bot.send_message(uid, "⛔️ انتهى اشتراكك وتمت إزالتك من المجموعة.")
                except:
                    pass
        except Exception as e:
            log.warning(f"Watcher error: {e}")
        await asyncio.sleep(60)  # افحص كل دقيقة

# ================== تشغيل البوت ==================
async def on_startup(dp):
    # رسالة للمشرف عند التشغيل
    try:
        if ADMIN_ID:
            await bot.send_message(ADMIN_ID, "✅ Bot started.")
    except:
        pass
    # شغّل المراقب
    dp.loop.create_task(expiry_watcher())

if __name__ == "__main__":
    log.info(f"Bot: Join [{os.getenv('BOT_USERNAME','')}]")
    executor.start_polling(dp, skip_updates=True, on_startup=on_startup)
