# join_bot.py
# -*- coding: utf-8 -*-

import os
import asyncio
import sqlite3
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from aiogram import Bot, Dispatcher, executor, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ChatInviteLink

# ===================== الإعدادات =====================
TOKEN = os.getenv("JOIN_TOKEN")
TARGET_CHAT_ID = int(os.getenv("TARGET_CHAT_ID", "0"))
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
CHANNEL_LINK = os.getenv("CHANNEL_LINK", "")
TZ_NAME = os.getenv("TZ", "Asia/Riyadh")

# بيانات الدفع
BANK_NAME = os.getenv("BANK_NAME", "البنك العربي الوطني")
ACCOUNT_NAME = os.getenv("ACCOUNT_NAME", "بدر محمد الجعيد")
IBAN = os.getenv("IBAN", "SA1630100991104930184574")

# الخطط (لا تعدّل الأزرار؛ عدّل القيم هنا فقط)
PLAN_MONTH_DAYS = int(os.getenv("PLAN_MONTH_DAYS", "30"))
PLAN_MONTH_PRICE = os.getenv("PLAN_MONTH_PRICE", "180")
PLAN_2WEEKS_DAYS = int(os.getenv("PLAN_2WEEKS_DAYS", "14"))
PLAN_2WEEKS_PRICE = os.getenv("PLAN_2WEEKS_PRICE", "90")

if not TOKEN:
    raise RuntimeError("JOIN_TOKEN is missing.")
if not TARGET_CHAT_ID or not str(TARGET_CHAT_ID).startswith("-100"):
    raise RuntimeError("TARGET_CHAT_ID invalid (must start with -100...).")
if not ADMIN_ID:
    raise RuntimeError("ADMIN_ID is missing.")

tz = ZoneInfo(TZ_NAME)
bot = Bot(token=TOKEN, parse_mode=types.ParseMode.HTML, disable_web_page_preview=True)
dp = Dispatcher(bot)

# ===================== قاعدة البيانات =====================
DB_PATH = "subs.db"
conn = sqlite3.connect(DB_PATH, check_same_thread=False)
c = conn.cursor()
c.execute("""
CREATE TABLE IF NOT EXISTS users(
  user_id INTEGER PRIMARY KEY,
  expires_at TEXT
)""")
c.execute("""
CREATE TABLE IF NOT EXISTS pending(
  request_id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER,
  photo_file_id TEXT,
  caption TEXT,
  plan_days INTEGER,
  plan_price TEXT,
  created_at TEXT
)""")
c.execute("""
CREATE TABLE IF NOT EXISTS plan_choice(
  user_id INTEGER PRIMARY KEY,
  plan_days INTEGER,
  plan_price TEXT,
  chosen_at TEXT
)""")
conn.commit()

# ===================== أدوات =====================
def now_ksa() -> datetime:
    return datetime.now(tz)

def fmt_dt(dt: datetime) -> str:
    return dt.astimezone(tz).strftime("%Y-%m-%d %H:%M")

def add_or_update_user(user_id: int, expires_at: datetime):
    c.execute("""
      INSERT INTO users(user_id, expires_at) VALUES(?, ?)
      ON CONFLICT(user_id) DO UPDATE SET expires_at=excluded.expires_at
    """, (user_id, expires_at.isoformat()))
    conn.commit()

def get_user_expiry(user_id: int):
    row = c.execute("SELECT expires_at FROM users WHERE user_id=?", (user_id,)).fetchone()
    if row:
        return datetime.fromisoformat(row[0]).astimezone(tz)
    return None

def remove_user(user_id: int):
    c.execute("DELETE FROM users WHERE user_id=?", (user_id,))
    conn.commit()

def set_plan_choice(user_id: int, days: int, price: str):
    c.execute("""
      INSERT INTO plan_choice(user_id, plan_days, plan_price, chosen_at) VALUES(?, ?, ?, ?)
      ON CONFLICT(user_id) DO UPDATE SET plan_days=excluded.plan_days, plan_price=excluded.plan_price, chosen_at=excluded.chosen_at
    """, (user_id, days, price, now_ksa().isoformat()))
    conn.commit()

def get_plan_choice(user_id: int):
    row = c.execute("SELECT plan_days, plan_price FROM plan_choice WHERE user_id=?", (user_id,)).fetchone()
    return (row[0], row[1]) if row else (None, None)

def clear_plan_choice(user_id: int):
    c.execute("DELETE FROM plan_choice WHERE user_id=?", (user_id,))
    conn.commit()

def add_pending(user_id: int, file_id: str, caption: str, plan_days: int, plan_price: str):
    c.execute("""
      INSERT INTO pending(user_id, photo_file_id, caption, plan_days, plan_price, created_at)
      VALUES(?, ?, ?, ?, ?, ?)
    """, (user_id, file_id, caption or "", plan_days, plan_price, now_ksa().isoformat()))
    conn.commit()
    return c.lastrowid

def get_pending(request_id: int):
    return c.execute("""
      SELECT request_id, user_id, photo_file_id, caption, plan_days, plan_price, created_at
      FROM pending WHERE request_id=?
    """, (request_id,)).fetchone()

def del_pending(request_id: int):
    c.execute("DELETE FROM pending WHERE request_id=?", (request_id,))
    conn.commit()

def plan_keyboard():
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton(f"اشتراك شهر — {PLAN_MONTH_PRICE} ريال", callback_data=f"plan:{PLAN_MONTH_DAYS}:{PLAN_MONTH_PRICE}"),
        InlineKeyboardButton(f"اشتراك أسبوعين — {PLAN_2WEEKS_PRICE} ريال", callback_data=f"plan:{PLAN_2WEEKS_DAYS}:{PLAN_2WEEKS_PRICE}")
    )
    return kb

def pay_text(amount: str):
    return (
        "<b>طريقة الاشتراك 🧾</b>\n"
        f"قيمة الاشتراك: <b>{amount} ريال</b>\n"
        f"<b>البنك:</b> {BANK_NAME}\n"
        f"<b>اسم صاحب الحساب:</b> {ACCOUNT_NAME}\n"
        f"<b>الآيبان:</b> <code>{IBAN}</code>\n\n"
        "بعد التحويل أرسل <b>صورة إيصال التحويل</b> هنا.\n"
        "بعد التأكيد سيصلك رابط دعوة صالح لعضو واحد ✅"
    )

def start_text():
    return (
        "مرحباً 👋\n"
        "اختر مدة الاشتراك المناسبة، ثم اتبع تعليمات الدفع وأرسل صورة إيصال التحويل هنا.\n"
    )

async def try_create_invite_link() -> str | None:
    if CHANNEL_LINK:
        return CHANNEL_LINK
    try:
        link: ChatInviteLink = await bot.create_chat_invite_link(
            chat_id=TARGET_CHAT_ID,
            member_limit=1,
            expire_date=int((now_ksa() + timedelta(hours=6)).timestamp()),
            name="AutoInvite"
        )
        return link.invite_link
    except Exception:
        return None

# ===================== الأوامر العامة =====================
@dp.message_handler(commands=["start"])
async def cmd_start(m: types.Message):
    await m.reply(start_text(), reply_markup=plan_keyboard())

@dp.callback_query_handler(lambda q: q.data.startswith("plan:"))
async def on_choose_plan(q: types.CallbackQuery):
    _, days_str, price = q.data.split(":")
    days = int(days_str)
    set_plan_choice(q.from_user.id, days, price)
    await q.message.answer(
        "تم اختيار الخطة ✅\n" +
        (f"الخطة: شهر ({PLAN_MONTH_PRICE} ريال)" if days == PLAN_MONTH_DAYS else f"الخطة: أسبوعين ({PLAN_2WEEKS_PRICE} ريال)")
    )
    await q.message.answer(pay_text(price))

# ===================== استقبال إيصال التحويل =====================
@dp.message_handler(content_types=types.ContentTypes.PHOTO)
async def handle_receipt(m: types.Message):
    # لازم يكون اختار خطة أولاً
    plan_days, plan_price = get_plan_choice(m.from_user.id)
    if not plan_days:
        await m.reply("يرجى اختيار مدة الاشتراك أولاً من الأزرار، ثم أرسل صورة الإيصال.")
        return

    rid = add_pending(m.from_user.id, m.photo[-1].file_id, m.caption or "", plan_days, plan_price)
    await m.reply("تم استلام الإيصال ✅\nبانتظار موافقة المشرف…")

    caption = (
        f"🆕 طلب اشتراك #{rid}\n"
        f"المستخدم: {m.from_user.full_name} (ID: <code>{m.from_user.id}</code>)\n"
        f"الخطة: {plan_days} يوم — {plan_price} ريال\n"
        f"النص: {m.caption or '—'}"
    )
    kb = InlineKeyboardMarkup(row_width=2).add(
        InlineKeyboardButton("✅ تأكيد", callback_data=f"approve:{rid}"),
        InlineKeyboardButton("❌ رفض",  callback_data=f"reject:{rid}")
    )
    await bot.send_photo(ADMIN_ID, m.photo[-1].file_id, caption=caption, reply_markup=kb)

# ===================== موافقة/رفض المشرف =====================
@dp.callback_query_handler(lambda q: q.data.startswith("approve:") or q.data.startswith("reject:"))
async def on_admin_decision(q: types.CallbackQuery):
    if q.from_user.id != ADMIN_ID:
        return await q.answer("للمشرف فقط.", show_alert=True)

    action, rid_str = q.data.split(":")
    rid = int(rid_str)
    row = get_pending(rid)
    if not row:
        return await q.answer("الطلب غير موجود.", show_alert=True)

    _, user_id, file_id, caption, plan_days, plan_price, created_at = row

    if action == "reject":
        del_pending(rid)
        await bot.send_message(user_id, "نعتذر، تم رفض الاشتراك. راجع الإيصال أو تواصل مع الدعم.")
        try:
            await q.message.edit_caption(q.message.caption + "\n\n❌ تم الرفض.")
        except Exception:
            pass
        return await q.answer("تم الرفض.")

    # approve
    expires = now_ksa() + timedelta(days=int(plan_days))
    add_or_update_user(user_id, expires)

    invite = await try_create_invite_link()
    if invite:
        await bot.send_message(
            user_id,
            f"تم تأكيد اشتراكك ✅\n"
            f"الخطة: {plan_days} يوم — {plan_price} ريال\n"
            f"تاريخ الانتهاء: <b>{fmt_dt(expires)}</b> ({TZ_NAME})\n\n"
            f"رابط الدعوة (لعضو واحد):\n{invite}"
        )
        try:
            await q.message.edit_caption(q.message.caption + f"\n\n✅ تم التأكيد — ينتهي في {fmt_dt(expires)} ({TZ_NAME})")
        except Exception:
            pass
        del_pending(rid)
        # بعد التأكيد، نحذف اختيار الخطة من الجدول (ينظّف الحالة)
        clear_plan_choice(user_id)
        await q.answer("تمت الموافقة.")
    else:
        await q.answer("تعذر إنشاء رابط تلقائي. تأكد من صلاحيات البوت أو ضع CHANNEL_LINK.", show_alert=True)

# ===================== أوامر المشرف الاختيارية =====================
@dp.message_handler(commands=["members"])
async def cmd_members(m: types.Message):
    if m.from_user.id != ADMIN_ID:
        return
    rows = c.execute("SELECT user_id, expires_at FROM users ORDER BY expires_at").fetchall()
    if not rows:
        return await m.reply("لا يوجد مشتركين مسجلين.")
    lines = []
    for uid, ex in rows:
        dt = datetime.fromisoformat(ex).astimezone(tz)
        lines.append(f"{uid} — ينتهي: {fmt_dt(dt)}")
    await m.reply("المشتركون:\n" + "\n".join(lines))

@dp.message_handler(commands=["remove"])
async def cmd_remove(m: types.Message):
    if m.from_user.id != ADMIN_ID:
        return
    args = m.get_args().strip().split()
    if not args:
        return await m.reply("الاستخدام: /remove USER_ID")
    uid = int(args[0])
    try:
        await bot.kick_chat_member(TARGET_CHAT_ID, uid)
        await bot.unban_chat_member(TARGET_CHAT_ID, uid)
    except Exception:
        pass
    remove_user(uid)
    await m.reply(f"تمت إزالة {uid}.")

# ===================== مراقبة الانتهاء والتنبيهات =====================
async def expiry_watcher():
    notified = set()  # (user_id, expires_iso) لمنع تكرار التنبيه قبل يومين
    while True:
        try:
            rows = c.execute("SELECT user_id, expires_at FROM users").fetchall()
            now = now_ksa()
            for uid, ex in rows:
                dt = datetime.fromisoformat(ex).astimezone(tz)

                # تذكير قبل يومين
                if 0 < (dt - now).total_seconds() <= 2*24*3600:
                    key = (uid, ex)
                    if key not in notified:
                        try:
                            await bot.send_message(uid, f"⏰ تذكير: سينتهي اشتراكك بعد أقل من يومين في {fmt_dt(dt)} ({TZ_NAME}).")
                        except Exception:
                            pass
                        notified.add(key)

                # الانتهاء وإزالة العضو
                if now >= dt:
                    try:
                        await bot.kick_chat_member(TARGET_CHAT_ID, uid)
                        await bot.unban_chat_member(TARGET_CHAT_ID, uid)
                    except Exception:
                        pass
                    remove_user(uid)
                    try:
                        await bot.send_message(uid, "⛔️ انتهى اشتراكك. لإعادة الاشتراك ابدأ من جديد بـ /start.")
                    except Exception:
                        pass
        except Exception:
            pass
        await asyncio.sleep(60)

# ===================== تشغيل =====================
async def on_startup(_):
    asyncio.create_task(expiry_watcher())

if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True, on_startup=on_startup)
