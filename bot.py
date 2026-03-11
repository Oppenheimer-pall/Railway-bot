"""
UzRailways Seat Monitor Bot
Poyezdlarda bo'sh joy mavjudligini kuzatib, darhol xabar beradi.
"""

import asyncio
import logging
import sqlite3
from datetime import datetime, date
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
import config
from scraper import UzRailwaysScraper

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

bot = Bot(token=config.BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
scraper = UzRailwaysScraper()

# ─── FSM States ─────────────────────────────────────────────────────────────

class AddMonitor(StatesGroup):
    from_station = State()
    to_station   = State()
    travel_date  = State()
    wagon_type   = State()
    confirm      = State()

# ─── Database ────────────────────────────────────────────────────────────────

def init_db():
    conn = sqlite3.connect(config.DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS monitors (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER NOT NULL,
            chat_id     INTEGER NOT NULL,
            from_city   TEXT NOT NULL,
            to_city     TEXT NOT NULL,
            travel_date TEXT NOT NULL,
            wagon_type  TEXT DEFAULT 'any',
            active      INTEGER DEFAULT 1,
            created_at  TEXT DEFAULT (datetime('now')),
            last_check  TEXT,
            notified    INTEGER DEFAULT 0
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id    INTEGER PRIMARY KEY,
            username   TEXT,
            full_name  TEXT,
            joined_at  TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.commit()
    conn.close()

def save_user(user: types.User):
    conn = sqlite3.connect(config.DB_PATH)
    conn.execute(
        "INSERT OR REPLACE INTO users (user_id, username, full_name) VALUES (?,?,?)",
        (user.id, user.username, user.full_name)
    )
    conn.commit()
    conn.close()

def add_monitor(user_id, chat_id, from_city, to_city, travel_date, wagon_type):
    conn = sqlite3.connect(config.DB_PATH)
    c = conn.cursor()
    c.execute(
        "INSERT INTO monitors (user_id, chat_id, from_city, to_city, travel_date, wagon_type) VALUES (?,?,?,?,?,?)",
        (user_id, chat_id, from_city, to_city, travel_date, wagon_type)
    )
    monitor_id = c.lastrowid
    conn.commit()
    conn.close()
    return monitor_id

def get_user_monitors(user_id):
    conn = sqlite3.connect(config.DB_PATH)
    c = conn.cursor()
    rows = c.execute(
        "SELECT id, from_city, to_city, travel_date, wagon_type, active FROM monitors WHERE user_id=? ORDER BY id DESC",
        (user_id,)
    ).fetchall()
    conn.close()
    return rows

def deactivate_monitor(monitor_id, user_id):
    conn = sqlite3.connect(config.DB_PATH)
    conn.execute(
        "UPDATE monitors SET active=0 WHERE id=? AND user_id=?",
        (monitor_id, user_id)
    )
    conn.commit()
    conn.close()

def get_all_active_monitors():
    conn = sqlite3.connect(config.DB_PATH)
    rows = conn.execute(
        "SELECT id, user_id, chat_id, from_city, to_city, travel_date, wagon_type FROM monitors WHERE active=1"
    ).fetchall()
    conn.close()
    return rows

def mark_checked(monitor_id):
    conn = sqlite3.connect(config.DB_PATH)
    conn.execute("UPDATE monitors SET last_check=datetime('now') WHERE id=?", (monitor_id,))
    conn.commit()
    conn.close()

def mark_notified(monitor_id):
    conn = sqlite3.connect(config.DB_PATH)
    conn.execute("UPDATE monitors SET notified=1, active=0 WHERE id=?", (monitor_id,))
    conn.commit()
    conn.close()

# ─── Keyboards ───────────────────────────────────────────────────────────────

def main_menu():
    kb = ReplyKeyboardMarkup(resize_keyboard=True, keyboard=[
        [KeyboardButton(text="🔍 Yangi kuzatuv qo'shish")],
        [KeyboardButton(text="📋 Mening kuzatuvlarim"), KeyboardButton(text="ℹ️ Yordam")],
    ])
    return kb

def wagon_type_kb():
    builder = InlineKeyboardBuilder()
    types_list = [("🛏 Platskart", "platskart"), ("🚪 Kupe", "kupe"),
                  ("⭐ SV (Lyuks)", "sv"), ("💺 O'rindiq", "orindiq"), ("🔄 Barchasi", "any")]
    for label, val in types_list:
        builder.button(text=label, callback_data=f"wtype:{val}")
    builder.adjust(2)
    return builder.as_markup()

def confirm_kb():
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Tasdiqlash", callback_data="confirm:yes")
    builder.button(text="❌ Bekor qilish", callback_data="confirm:no")
    return builder.as_markup()

def monitors_kb(monitors):
    builder = InlineKeyboardBuilder()
    for m in monitors:
        mid, from_c, to_c, date_, wtype, active = m
        status = "🟢" if active else "🔴"
        builder.button(
            text=f"{status} {from_c}→{to_c} | {date_}",
            callback_data=f"view:{mid}"
        )
    builder.adjust(1)
    return builder.as_markup()

# ─── Handlers ────────────────────────────────────────────────────────────────

@dp.message(CommandStart())
async def cmd_start(msg: types.Message):
    save_user(msg.from_user)
    await msg.answer(
        f"👋 Salom, <b>{msg.from_user.first_name}</b>!\n\n"
        "🚂 <b>UzRailways Joy Monitor</b> botiga xush kelibsiz!\n\n"
        "Bu bot sizga kerakli yo'nalishda poyezdda <b>bo'sh joy paydo bo'lganda darhol xabar beradi</b>.\n\n"
        "📌 Boshlash uchun quyidagi tugmani bosing:",
        parse_mode="HTML",
        reply_markup=main_menu()
    )

@dp.message(Command("help"))
@dp.message(F.text == "ℹ️ Yordam")
async def cmd_help(msg: types.Message):
    await msg.answer(
        "📖 <b>Bot haqida ma'lumot:</b>\n\n"
        "1️⃣ <b>Yangi kuzatuv qo'shish</b> — yo'nalish, sana va vagon turini tanlang\n"
        "2️⃣ Bot har <b>5 daqiqada</b> uzrailways.uz saytini tekshiradi\n"
        "3️⃣ Bo'sh joy topilsa, <b>darhol xabar</b> yuboriladi\n"
        "4️⃣ <b>Mening kuzatuvlarim</b> — faol kuzatuvlarni ko'rish va o'chirish\n\n"
        "⚙️ Buyruqlar:\n"
        "/start — Botni ishga tushirish\n"
        "/mymonitors — Kuzatuvlarni ko'rish\n"
        "/cancel — Jarayonni bekor qilish\n\n"
        "💡 Bir vaqtda <b>5 tagacha</b> kuzatuv qo'shish mumkin.",
        parse_mode="HTML"
    )

# ─── Add Monitor Flow ─────────────────────────────────────────────────────────

@dp.message(F.text == "🔍 Yangi kuzatuv qo'shish")
async def start_add_monitor(msg: types.Message, state: FSMContext):
    active = [m for m in get_user_monitors(msg.from_user.id) if m[5] == 1]
    if len(active) >= 5:
        await msg.answer("⚠️ Siz allaqachon 5 ta faol kuzatuvga egasiz. Yangi qo'shish uchun avval birini o'chiring.")
        return
    await state.set_state(AddMonitor.from_station)
    await msg.answer(
        "🚉 <b>Qayerdan?</b>\n\nJo'nash stantsiyasini kiriting:\n"
        "<i>Masalan: Toshkent, Samarqand, Buxoro, Qarshi, Termiz...</i>",
        parse_mode="HTML"
    )

@dp.message(AddMonitor.from_station)
async def get_from_station(msg: types.Message, state: FSMContext):
    await state.update_data(from_city=msg.text.strip().title())
    await state.set_state(AddMonitor.to_station)
    await msg.answer(
        f"✅ Jo'nash: <b>{msg.text.strip().title()}</b>\n\n"
        "🏁 <b>Qayerga?</b>\n\nBoradigan stantsiyani kiriting:",
        parse_mode="HTML"
    )

@dp.message(AddMonitor.to_station)
async def get_to_station(msg: types.Message, state: FSMContext):
    data = await state.get_data()
    if msg.text.strip().title() == data['from_city']:
        await msg.answer("⚠️ Jo'nash va borish stantsiyalari bir xil bo'lmasligi kerak!")
        return
    await state.update_data(to_city=msg.text.strip().title())
    await state.set_state(AddMonitor.travel_date)
    await msg.answer(
        f"✅ Borish: <b>{msg.text.strip().title()}</b>\n\n"
        "📅 <b>Sana?</b>\n\nSayohat sanasini kiriting:\n"
        "<i>Format: KK.OO.YYYY (masalan: 25.03.2025)</i>",
        parse_mode="HTML"
    )

@dp.message(AddMonitor.travel_date)
async def get_travel_date(msg: types.Message, state: FSMContext):
    try:
        travel_date = datetime.strptime(msg.text.strip(), "%d.%m.%Y").date()
        if travel_date < date.today():
            await msg.answer("⚠️ O'tib ketgan sanani kirita olmaysiz! Kelajakdagi sanani kiriting.")
            return
    except ValueError:
        await msg.answer("⚠️ Noto'g'ri format! Iltimos KK.OO.YYYY formatida kiriting.\n<i>Masalan: 25.03.2025</i>", parse_mode="HTML")
        return
    await state.update_data(travel_date=msg.text.strip())
    await state.set_state(AddMonitor.wagon_type)
    await msg.answer(
        f"✅ Sana: <b>{msg.text.strip()}</b>\n\n"
        "🚃 <b>Vagon turi?</b>\n\nQaysi turdagi vagon kerak?",
        parse_mode="HTML",
        reply_markup=wagon_type_kb()
    )

@dp.callback_query(F.data.startswith("wtype:"), AddMonitor.wagon_type)
async def get_wagon_type(cb: types.CallbackQuery, state: FSMContext):
    wtype = cb.data.split(":")[1]
    wtype_names = {"platskart": "Platskart 🛏", "kupe": "Kupe 🚪",
                   "sv": "SV (Lyuks) ⭐", "orindiq": "O'rindiq 💺", "any": "Barchasi 🔄"}
    await state.update_data(wagon_type=wtype)
    data = await state.get_data()
    await state.set_state(AddMonitor.confirm)
    summary = (
        f"📋 <b>Kuzatuv ma'lumotlari:</b>\n\n"
        f"🚉 Jo'nash: <b>{data['from_city']}</b>\n"
        f"🏁 Borish: <b>{data['to_city']}</b>\n"
        f"📅 Sana: <b>{data['travel_date']}</b>\n"
        f"🚃 Vagon turi: <b>{wtype_names.get(wtype, wtype)}</b>\n\n"
        f"Tasdiqlaysizmi?"
    )
    await cb.message.edit_text(summary, parse_mode="HTML", reply_markup=confirm_kb())

@dp.callback_query(F.data.startswith("confirm:"), AddMonitor.confirm)
async def confirm_monitor(cb: types.CallbackQuery, state: FSMContext):
    answer = cb.data.split(":")[1]
    if answer == "no":
        await state.clear()
        await cb.message.edit_text("❌ Kuzatuv bekor qilindi.")
        return
    data = await state.get_data()
    monitor_id = add_monitor(
        cb.from_user.id, cb.message.chat.id,
        data['from_city'], data['to_city'],
        data['travel_date'], data['wagon_type']
    )
    await state.clear()
    await cb.message.edit_text(
        f"✅ <b>Kuzatuv #{monitor_id} qo'shildi!</b>\n\n"
        f"🚉 {data['from_city']} → {data['to_city']}\n"
        f"📅 {data['travel_date']}\n\n"
        f"⏰ Bot har 5 daqiqada tekshiradi va bo'sh joy topilsa <b>darhol xabar beradi</b>.",
        parse_mode="HTML"
    )

# ─── My Monitors ─────────────────────────────────────────────────────────────

@dp.message(F.text == "📋 Mening kuzatuvlarim")
@dp.message(Command("mymonitors"))
async def my_monitors(msg: types.Message):
    monitors = get_user_monitors(msg.from_user.id)
    if not monitors:
        await msg.answer(
            "📭 Sizda hali kuzatuvlar yo'q.\n"
            "«🔍 Yangi kuzatuv qo'shish» tugmasini bosing!"
        )
        return
    active = [m for m in monitors if m[5] == 1]
    inactive = [m for m in monitors if m[5] == 0]
    text = f"📋 <b>Sizning kuzatuvlaringiz:</b>\n🟢 Faol: {len(active)} | 🔴 Tugagan: {len(inactive)}\n\nKuzatuvni bosing:"
    await msg.answer(text, parse_mode="HTML", reply_markup=monitors_kb(monitors))

@dp.callback_query(F.data.startswith("view:"))
async def view_monitor(cb: types.CallbackQuery):
    monitor_id = int(cb.data.split(":")[1])
    conn = sqlite3.connect(config.DB_PATH)
    m = conn.execute(
        "SELECT id, from_city, to_city, travel_date, wagon_type, active, last_check, notified FROM monitors WHERE id=? AND user_id=?",
        (monitor_id, cb.from_user.id)
    ).fetchone()
    conn.close()
    if not m:
        await cb.answer("Kuzatuv topilmadi.", show_alert=True)
        return
    mid, from_c, to_c, date_, wtype, active, last_check, notified = m
    status = "🟢 Faol" if active else ("✅ Topildi" if notified else "🔴 To'xtatildi")
    wtype_names = {"platskart": "Platskart", "kupe": "Kupe", "sv": "SV (Lyuks)", "orindiq": "O'rindiq", "any": "Barchasi"}
    text = (
        f"🔍 <b>Kuzatuv #{mid}</b>\n\n"
        f"🚉 {from_c} → {to_c}\n"
        f"📅 Sana: {date_}\n"
        f"🚃 Vagon: {wtype_names.get(wtype, wtype)}\n"
        f"📊 Holat: {status}\n"
        f"🕐 So'nggi tekshiruv: {last_check or 'Hali tekshirilmagan'}"
    )
    builder = InlineKeyboardBuilder()
    if active:
        builder.button(text="🛑 Kuzatuvni to'xtatish", callback_data=f"stop:{mid}")
    builder.button(text="◀️ Orqaga", callback_data="back:monitors")
    await cb.message.edit_text(text, parse_mode="HTML", reply_markup=builder.as_markup())

@dp.callback_query(F.data.startswith("stop:"))
async def stop_monitor(cb: types.CallbackQuery):
    monitor_id = int(cb.data.split(":")[1])
    deactivate_monitor(monitor_id, cb.from_user.id)
    await cb.answer("✅ Kuzatuv to'xtatildi.", show_alert=True)
    await cb.message.edit_text(f"🔴 Kuzatuv #{monitor_id} to'xtatildi.")

@dp.callback_query(F.data == "back:monitors")
async def back_to_monitors(cb: types.CallbackQuery):
    monitors = get_user_monitors(cb.from_user.id)
    active = [m for m in monitors if m[5] == 1]
    text = f"📋 <b>Sizning kuzatuvlaringiz:</b>\n🟢 Faol: {len(active)}\n\nKuzatuvni bosing:"
    await cb.message.edit_text(text, parse_mode="HTML", reply_markup=monitors_kb(monitors))

@dp.message(Command("cancel"))
async def cancel(msg: types.Message, state: FSMContext):
    await state.clear()
    await msg.answer("❌ Bekor qilindi.", reply_markup=main_menu())

# ─── Background Monitor Task ──────────────────────────────────────────────────

async def check_monitors():
    """Har 5 daqiqada barcha faol kuzatuvlarni tekshiradi."""
    while True:
        try:
            monitors = get_all_active_monitors()
            logger.info(f"Tekshirilmoqda: {len(monitors)} ta kuzatuv...")
            for monitor in monitors:
                mid, user_id, chat_id, from_city, to_city, travel_date, wagon_type = monitor
                try:
                    result = await scraper.check_seats(from_city, to_city, travel_date, wagon_type)
                    mark_checked(mid)
                    if result['available']:
                        await send_notification(chat_id, from_city, to_city, travel_date, wagon_type, result, mid)
                        mark_notified(mid)
                    await asyncio.sleep(2)  # Sayt bilan hisobga olish uchun kechikish
                except Exception as e:
                    logger.error(f"Monitor #{mid} tekshirishda xato: {e}")
        except Exception as e:
            logger.error(f"check_monitors umumiy xato: {e}")
        await asyncio.sleep(config.CHECK_INTERVAL)

async def send_notification(chat_id, from_city, to_city, travel_date, wagon_type, result, monitor_id):
    """Foydalanuvchiga bo'sh joy haqida xabar yuboradi."""
    trains_text = ""
    for train in result.get('trains', [])[:5]:
        trains_text += (
            f"\n🚂 <b>Poyezd #{train.get('number', '?')}</b>\n"
            f"   ⏰ {train.get('departure', '?')} → {train.get('arrival', '?')}\n"
            f"   💺 Bo'sh joylar: <b>{train.get('seats', '?')} ta</b>\n"
            f"   💰 Narx: {train.get('price', 'noma\'lum')}\n"
        )
    message = (
        f"🔔 <b>BO'SH JOY TOPILDI!</b>\n\n"
        f"🚉 <b>{from_city} → {to_city}</b>\n"
        f"📅 Sana: <b>{travel_date}</b>\n"
        f"🚃 Vagon turi: <b>{wagon_type}</b>\n"
        f"{trains_text}\n"
        f"⚡️ <b>Tezda bron qiling!</b>\n"
        f"🔗 <a href='https://chipta.uzrailways.uz'>uzrailways.uz</a>"
    )
    builder = InlineKeyboardBuilder()
    builder.button(text="🎫 Bilet sotib olish", url="https://chipta.uzrailways.uz")
    try:
        await bot.send_message(chat_id, message, parse_mode="HTML", reply_markup=builder.as_markup())
        logger.info(f"✅ Xabar yuborildi: chat_id={chat_id}, monitor_id={monitor_id}")
    except Exception as e:
        logger.error(f"Xabar yuborishda xato: {e}")

# ─── Main ─────────────────────────────────────────────────────────────────────

async def main():
    init_db()
    logger.info("🤖 Bot ishga tushmoqda...")
    asyncio.create_task(check_monitors())
    await dp.start_polling(bot, skip_updates=True)

if __name__ == "__main__":
    asyncio.run(main())
