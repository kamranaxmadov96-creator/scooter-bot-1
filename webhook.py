import asyncio
import aiosqlite
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.client.default import DefaultBotProperties
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from datetime import datetime, date
from openpyxl import Workbook
import os
from aiohttp import web

# ===================== НАСТРОЙКИ ========================
API_TOKEN = os.getenv("BOT_TOKEN")  # Render переменная
ADMIN_IDS = {1060590354}

WEBHOOK_PATH = "/webhook"
WEBHOOK_URL = os.getenv("WEBHOOK_URL") + WEBHOOK_PATH


# ===================== БАЗА ДАННЫХ =======================
async def init_db():
    async with aiosqlite.connect("scooters.db") as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                scooter_number INTEGER,
                user_id INTEGER,
                action TEXT,
                datetime TEXT
            )
        """)
        await db.commit()


# ===================== КЛАВИАТУРЫ ========================
def scooter_actions_keyboard(number):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👁️ Görüldü", callback_data=f"seen_{number}")],
        [InlineKeyboardButton(text="🔋 Batarya Değişti", callback_data=f"battery_{number}")],
        [InlineKeyboardButton(text="🔧 Tamir", callback_data=f"repair_{number}")]
    ])


def page_keyboard(page):
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="⬅️", callback_data=f"page_{page-1}"),
            InlineKeyboardButton(text="➡️", callback_data=f"page_{page+1}")
        ]
    ])


# ===================== СПИСОК СКУТЕРОВ ======================
async def show_page(message, page):
    scooters = list(range(101, 231))
    per_page = 20
    pages = (len(scooters) + per_page - 1) // per_page

    page = max(1, min(page, pages))
    start = (page - 1) * per_page
    part = scooters[start:start + per_page]

    text = f"📋 Scooter Listesi (Sayfa {page}/{pages}):\n\n"
    for num in part:
        text += f"🛵 {num} — /s{num}\n"

    await message.answer(text, reply_markup=page_keyboard(page))


# ===================== TELEGRAM BOT =======================
dp = Dispatcher()


@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer("🇹🇷 Merhaba!\nScooter listesini görmek için /liste yazın.")


@dp.message(Command("liste"))
async def cmd_list(message: types.Message):
    await show_page(message, 1)


@dp.message(F.text.regexp(r"^/s(\d+)$"))
async def cmd_scooter(message: types.Message):
    num = int(message.text[2:])
    if num < 101 or num > 230:
        return await message.answer("❌ Geçersiz numara.")

    await message.answer(
        f"🛵 Scooter {num}\nİşaretleyin:",
        reply_markup=scooter_actions_keyboard(num)
    )


# ===================== CALLBACK ACTIONS ======================
@dp.callback_query(F.data.startswith("page_"))
async def cb_page(query: types.CallbackQuery):
    page = int(query.data.split("_")[1])
    await query.message.delete()
    await show_page(query.message, page)


@dp.callback_query(F.data.regexp(r"^(seen|battery|repair)_"))
async def cb_actions(query: types.CallbackQuery):
    action, num = query.data.split("_")
    num = int(num)

    async with aiosqlite.connect("scooters.db") as db:
        await db.execute(
            "INSERT INTO records (scooter_number, user_id, action, datetime) VALUES (?, ?, ?, ?)",
            (num, query.from_user.id, action, datetime.now().isoformat())
        )
        await db.commit()

    responses = {
        "seen": "👁️ Görüldü kaydedildi",
        "battery": "🔋 Batarya değişti",
        "repair": "🔧 Tamir için işaretlendi"
    }

    await query.answer(responses[action], show_alert=True)


# ===================== MYID ======================
@dp.message(Command("myid"))
async def cmd_myid(message: types.Message):
    await message.answer(f"Sizin ID: <b>{message.from_user.id}</b>")


# ===================== ADMIN PANEL ======================
@dp.message(Command("admin"))
async def cmd_admin(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return await message.answer("❌ Только админ.")

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Günlük Rapor", callback_data="admin_today")],
        [InlineKeyboardButton(text="📅 Tarihe Göre Rapor", callback_data="admin_by_date")],
        [InlineKeyboardButton(text="🛠 Tamirdeki Scooterlar", callback_data="admin_repair_list")],
        [InlineKeyboardButton(text="🔋 Batarya Değişenler", callback_data="admin_battery_list")],
        [InlineKeyboardButton(text="👁️ Görülenler", callback_data="admin_seen_list")],
        [InlineKeyboardButton(text="🧹 Veritabanını Temizle", callback_data="admin_clear_db")],
    ])

    await message.answer("🔧 <b>Админ-меню:</b>", reply_markup=kb)


# ===================== ADMIN CALLBACK ======================
@dp.callback_query(F.data == "admin_today")
async def admin_today_report(query):
    await query.answer()
    await send_daily_report(query.message)


@dp.callback_query(F.data == "admin_by_date")
async def admin_by_date(query):
    await query.answer("Format:\n/report 2025-01-01", show_alert=True)


@dp.callback_query(F.data == "admin_repair_list")
async def admin_repair_list(query):
    await query.answer()
    await send_status_list(query.message, "repair", "Tamirdeki Scooterlar")


@dp.callback_query(F.data == "admin_battery_list")
async def admin_battery_list(query):
    await query.answer()
    await send_status_list(query.message, "battery", "Batarya Değişenler")


@dp.callback_query(F.data == "admin_seen_list")
async def admin_seen_list(query):
    await query.answer()
    await send_status_list(query.message, "seen", "Görülen Scooterlar")


@dp.callback_query(F.data == "admin_clear_db")
async def admin_clear_db(query):
    if query.from_user.id not in ADMIN_IDS:
        return await query.answer("❌ Только админ.", show_alert=True)

    async with aiosqlite.connect("scooters.db") as db:
        await db.execute("DELETE FROM records")
        await db.commit()

    await query.message.answer("🧹 База данных очищена.")
    await query.answer()


# ===================== REPORT ======================
@dp.message(Command("report"))
async def cmd_report(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return await message.answer("❌ Только админ.")

    try:
        async with aiosqlite.connect("scooters.db") as db:
            cursor = await db.execute(
                "SELECT scooter_number, user_id, action, datetime FROM records"
            )
            rows = await cursor.fetchall()

        if not rows:
            return await message.answer("📝 Kayıt yok.")

        wb = Workbook()
        ws = wb.active
        ws.append(["scooter_number", "user_id", "action", "datetime"])

        for row in rows:
            ws.append(row)

        file = "rapor.xlsx"
        wb.save(file)

        await message.answer_document(
            types.FSInputFile(file),
            caption="📊 Genel rapor hazır."
        )

    except Exception as e:
        await message.answer(f"❌ Hata:\n<code>{e}</code>")


# ===================== DAILY REPORT ======================
async def send_daily_report(message):
    today = date.today().isoformat()

    async with aiosqlite.connect("scooters.db") as db:
        cursor = await db.execute(
            "SELECT scooter_number, user_id, action, datetime FROM records WHERE datetime LIKE ?",
            (today + "%",)
        )
        rows = await cursor.fetchall()

    if not rows:
        return await message.answer("📝 Bugün kayıt yok.")

    wb = Workbook()
    ws = wb.active
    ws.append(["scooter_number", "user_id", "action", "datetime"])

    for row in rows:
        ws.append(row)

    file = "rapor_gunluk.xlsx"
    wb.save(file)

    await message.answer_document(
        types.FSInputFile(file),
        caption="📊 Günlük rapor hazır."
    )


# ===================== STATUS LISTS ======================
async def send_status_list(message, status, title):
    async with aiosqlite.connect("scooters.db") as db:
        cursor = await db.execute(
            "SELECT DISTINCT scooter_number FROM records WHERE action = ?",
            (status,)
        )
        rows = await cursor.fetchall()

    if not rows:
        return await message.answer(f"📝 {title}: Kayıt yok.")

    text = f"📋 <b>{title}</b>:\n\n"
    for r in rows:
        text += f"🛵 {r[0]}\n"

    await message.answer(text)


# ===================== WEBHOOK SERVER (Render) ======================
bot = Bot(API_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))


async def webhook_handler(request: web.Request):
    update = await request.json()
    await dp.feed_update(bot, types.Update(**update))
    return web.Response()


async def on_startup(app):
    await init_db()
    await bot.set_webhook(WEBHOOK_URL)


def create_app():
    app = web.Application()
    app.router.add_post(WEBHOOK_PATH, webhook_handler)
    app.on_startup.append(on_startup)
    return app


app = create_app()
