#!/usr/bin/env python3
"""
Telegram-бот для Чёрного Ретрита Болгария
Продавец + Администратор
"""

import os
import logging
import sqlite3
from datetime import datetime, timedelta, date, time as dtime
import pytz
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)

logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get('BOT_TOKEN', '')
ADMIN_ID = int(os.environ.get('ADMIN_ID', '7851352670'))
MSK = pytz.timezone('Europe/Moscow')

DAYS_RU = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс']
MONTHS_RU = ['', 'января', 'февраля', 'марта', 'апреля', 'мая', 'июня',
             'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря']
MONTHS_SHORT = ['', 'янв', 'фев', 'мар', 'апр', 'май', 'июн',
                'июл', 'авг', 'сен', 'окт', 'ноя', 'дек']

os.makedirs('data', exist_ok=True)

# ─── База данных ────────────────────────────────────────────────────────────

def get_db():
    return sqlite3.connect('data/bot.db')

def init_db():
    with get_db() as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS bookings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER, username TEXT, name TEXT,
            slot TEXT, created_at TEXT, status TEXT DEFAULT 'active'
        )''')
        conn.execute('''CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT, first_name TEXT, joined_at TEXT
        )''')
        conn.execute('''CREATE TABLE IF NOT EXISTS log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER, username TEXT, first_name TEXT,
            text TEXT, created_at TEXT
        )''')

def register_user(user):
    with get_db() as conn:
        row = conn.execute('SELECT 1 FROM users WHERE user_id=?', (user.id,)).fetchone()
        if not row:
            conn.execute('INSERT INTO users VALUES (?,?,?,?)',
                         (user.id, user.username, user.first_name,
                          datetime.now(MSK).strftime('%Y-%m-%d %H:%M')))
            return True
    return False

def log_message(user, text):
    with get_db() as conn:
        conn.execute(
            'INSERT INTO log (user_id, username, first_name, text, created_at) VALUES (?,?,?,?,?)',
            (user.id, user.username, user.first_name, text,
             datetime.now(MSK).strftime('%Y-%m-%d %H:%M'))
        )

def is_slot_taken(slot_str):
    with get_db() as conn:
        row = conn.execute(
            "SELECT 1 FROM bookings WHERE slot=? AND status='active'", (slot_str,)
        ).fetchone()
    return row is not None

def save_booking(user_id, username, name, slot):
    with get_db() as conn:
        conn.execute(
            'INSERT INTO bookings (user_id, username, name, slot, created_at) VALUES (?,?,?,?,?)',
            (user_id, username, name, slot,
             datetime.now(MSK).strftime('%Y-%m-%d %H:%M'))
        )

def get_available_slots(hours_range, days_ahead=7):
    booked = set()
    with get_db() as conn:
        for row in conn.execute("SELECT slot FROM bookings WHERE status='active'"):
            booked.add(row[0])

    slots = []
    now = datetime.now(MSK)
    for offset in range(1, days_ahead + 1):
        d = now.date() + timedelta(days=offset)
        if d.weekday() == 6:  # воскресенье — выходной
            continue
        for h in hours_range:
            val = f"{d.strftime('%Y-%m-%d')} {h:02d}:00"
            if val not in booked:
                display = f"{DAYS_RU[d.weekday()]} {d.day} {MONTHS_SHORT[d.month]} · {h:02d}:00 мск"
                slots.append((display, val))
    return slots[:8]

def format_slot(slot_str):
    dt = datetime.strptime(slot_str, '%Y-%m-%d %H:%M')
    return f"{DAYS_RU[dt.weekday()]}, {dt.day} {MONTHS_RU[dt.month]}, {dt.hour:02d}:00 мск"

# ─── Контент ─────────────────────────────────────────────────────────────────

INFO = {
    'dates': (
        "📅 *Даты и стоимость 2026*\n\n"
        "• Май 20–30: *200 000 ₽*\n"
        "• Июнь 20–30: *300 000 ₽*\n"
        "• Июль 20–30: *350 000 ₽*\n"
        "• Август 20–30: *350 000 ₽*\n"
        "• Сентябрь 3–13: *300 000 ₽*\n"
        "• Октябрь 1–10: *200 000 ₽*\n\n"
        "✅ *Включено:* проживание, питание 3 раза (повар в доме), "
        "вся программа, физиотерапия, кризисная сессия, материалы.\n"
        "❌ *Не включено:* перелёт, личные расходы."
    ),
    'format': (
        "🔄 *Формат ретрита*\n\n"
        "*10 дней / 9 ночей.* Единый цикл — каждый день опирается на предыдущий.\n\n"
        "• Дни 1–2: замедление, знакомство\n"
        "• Дни 3–5: Группа А — с закрытыми глазами, Группа Б — поддержка\n"
        "• День 6: интеграция, смена ролей\n"
        "• Дни 7–9: Группа Б — глубокая работа, Группа А — опора\n"
        "• День 10: ритуал закрытия, личный план на 3 месяца\n\n"
        "Каждый день: телесные практики, психологическая работа, "
        "физиотерапия, медитация у моря."
    ),
    'safety': (
        "🛡 *Безопасность*\n\n"
        "• Ольга рядом 24/7 — 34 года кризисной практики\n"
        "• Выйти из практики можно в любой момент без объяснений\n"
        "• Предварительное собеседование — исключаем противопоказания\n"
        "• Маску привозите сами — это ваша вещь, ваша граница\n"
        "• Рядом всегда есть участница — ведут за руку к морю, к столу\n\n"
        "*Противопоказания:* острые психотические состояния, беременность. "
        "Всё обсуждаем на собеседовании."
    ),
    'payment': (
        "💳 *Оплата*\n\n"
        "Два этапа:\n"
        "1. *Предоплата* — на российскую карту (бронирует место)\n"
        "2. *Остаток* — наличными в евро в день приезда\n\n"
        "Стоимость в рублях, пересчитываем по курсу в евро.\n\n"
        "ℹ️ *Про наличные:* можно провезти до 10 000 USD без декларирования — "
        "сумма ретрита укладывается в этот лимит."
    ),
    'location': (
        "📍 *Место проведения*\n\n"
        "*Святой Влас, Болгария* — тихий курорт на Чёрном море.\n\n"
        "• 200 метров от воды\n"
        "• Собственные новые апартаменты Ольги (куплены в 2025)\n"
        "• Болгария в Шенгене с 2025 — виза не нужна\n"
        "• Перелёт: Москва / Питер → Стамбул → Бургас (~4 часа)\n"
        "• Трансфер из Бургаса при раннем бронировании — бесплатно"
    ),
    'about': (
        "🖤 *Чёрный Ретрит · Болгария · 2026*\n\n"
        "10 дней трансформационной работы на берегу Чёрного моря.\n\n"
        "*Ведущая:* Ph.Dr. Ольга Турьева — кризисный психолог, "
        "34 года практики, физиотерапевт. Данибузский университет, Словакия.\n"
        "*Место:* Святой Влас, 200 м от моря.\n"
        "*Группа:* до 8 человек.\n\n"
        "Это не медитация и не йога. Настоящая работа с телом и психикой.\n"
        "Для женщин в выгорании, кризисе, потере себя."
    ),
}

FAQ_MAP = {
    'цен': 'dates', 'стоимост': 'dates', 'дорого': 'dates',
    'сколько': 'dates', 'дат': 'dates', 'когда': 'dates',
    'май': 'dates', 'июн': 'dates', 'июл': 'dates', 'август': 'dates',
    'формат': 'format', 'програм': 'format', 'глаза': 'format',
    'повязк': 'format', 'день': 'format', 'расписан': 'format',
    'безопас': 'safety', 'страшно': 'safety', 'маск': 'safety',
    'противопоказан': 'safety', 'психиатр': 'safety',
    'оплат': 'payment', 'деньг': 'payment', 'евро': 'payment',
    'перевод': 'payment', 'налич': 'payment', 'границ': 'payment',
    'где': 'location', 'болгар': 'location', 'квартир': 'location',
    'добрат': 'location', 'перелет': 'location', 'виза': 'location',
    'аэропорт': 'location', 'бургас': 'location', 'море': 'location',
    'что такое': 'about', 'что это': 'about', 'расскаж': 'about',
    'подробн': 'about', 'чёрный ретрит': 'about', 'черный ретрит': 'about',
}


def main_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📅 Даты и цены", callback_data='i_dates'),
         InlineKeyboardButton("🔄 Формат", callback_data='i_format')],
        [InlineKeyboardButton("🛡 Безопасность", callback_data='i_safety'),
         InlineKeyboardButton("📍 Место", callback_data='i_location')],
        [InlineKeyboardButton("💳 Оплата", callback_data='i_payment')],
        [InlineKeyboardButton("📞 Записаться на собеседование", callback_data='book')],
    ])


# ─── Обработчики ─────────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    is_new = register_user(user)
    context.user_data.clear()

    if is_new:
        try:
            await context.bot.send_message(
                ADMIN_ID,
                f"👤 *Новый пользователь*\n"
                f"Имя: {user.first_name} {user.last_name or ''}\n"
                f"@{user.username or '—'} · ID: `{user.id}`",
                parse_mode='Markdown'
            )
        except Exception:
            pass

    await update.message.reply_text(
        f"Здравствуйте, {user.first_name}! 👋\n\n"
        f"{INFO['about']}\n\n"
        "Выберите что вас интересует или задайте вопрос:",
        parse_mode='Markdown',
        reply_markup=main_kb()
    )


async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = update.message.text
    state = context.user_data.get('state')

    log_message(user, text)

    # Ждём имя для записи
    if state == 'wait_name':
        context.user_data['name'] = text
        context.user_data['state'] = None

        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🌅 До обеда (10:00–13:00)", callback_data='tp_morning')],
            [InlineKeyboardButton("☀️ После обеда (13:00–18:00)", callback_data='tp_afternoon')],
            [InlineKeyboardButton("🌆 Вечером (18:00–21:00)", callback_data='tp_evening')],
        ])
        await update.message.reply_text(
            f"Приятно познакомиться, {text}! 😊\n\n"
            "Когда вам удобнее созвониться с Ольгой?\n"
            "_(Время московское, пн–сб)_",
            parse_mode='Markdown',
            reply_markup=kb
        )
        return

    # FAQ
    tl = text.lower()
    for kw, key in FAQ_MAP.items():
        if kw in tl:
            try:
                await context.bot.send_message(
                    ADMIN_ID,
                    f"💬 *Вопрос:* {user.first_name} (@{user.username or '—'})\n"
                    f"_{text}_",
                    parse_mode='Markdown'
                )
            except Exception:
                pass
            await update.message.reply_text(
                INFO[key], parse_mode='Markdown', reply_markup=main_kb()
            )
            return

    # Неизвестный вопрос
    try:
        await context.bot.send_message(
            ADMIN_ID,
            f"❓ *Вопрос без ответа*\n"
            f"{user.first_name} (@{user.username or '—'}):\n_{text}_",
            parse_mode='Markdown'
        )
    except Exception:
        pass

    await update.message.reply_text(
        "Я отвечаю на вопросы о ретрите — выберите тему кнопкой ниже.\n"
        "Для других вопросов — запишитесь на личную беседу с Ольгой 🙂",
        reply_markup=main_kb()
    )


async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = q.data
    user = q.from_user

    # Информационные блоки
    if data.startswith('i_'):
        key = data[2:]
        await q.message.reply_text(
            INFO[key], parse_mode='Markdown', reply_markup=main_kb()
        )
        return

    # Начало записи
    if data == 'book':
        context.user_data['state'] = 'wait_name'
        await q.message.reply_text("Как вас зовут? Напишите имя и фамилию:")
        return

    # Выбор времени суток
    if data.startswith('tp_'):
        pref = data[3:]
        hours = {
            'morning': range(10, 13),
            'afternoon': range(13, 18),
            'evening': range(18, 21),
        }[pref]
        slots = get_available_slots(hours)

        if not slots:
            await q.message.reply_text(
                "В это время нет свободных слотов на ближайшую неделю.\n"
                "Попробуйте другое время или напишите напрямую @OlgaTurreva",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("⬅️ Выбрать другое время", callback_data='book')
                ]])
            )
            return

        keyboard = [[InlineKeyboardButton(d, callback_data=f's_{v}')] for d, v in slots]
        keyboard.append([InlineKeyboardButton("⬅️ Другое время", callback_data='book')])
        await q.message.reply_text(
            "Выберите удобное время:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    # Выбор конкретного слота
    if data.startswith('s_'):
        slot = data[2:]
        if is_slot_taken(slot):
            await q.message.reply_text(
                "Это время только что заняли 😔 Выберите другое:",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("⬅️ Выбрать время", callback_data='book')
                ]])
            )
            return

        context.user_data['slot'] = slot
        name = context.user_data.get('name', user.first_name)
        display = format_slot(slot)
        context.user_data['slot_display'] = display

        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Подтвердить", callback_data='confirm'),
            InlineKeyboardButton("✏️ Изменить", callback_data='book'),
        ]])
        await q.message.reply_text(
            f"*Подтвердите запись:*\n\n"
            f"👤 {name}\n"
            f"📅 {display}\n\n"
            f"После подтверждения Ольга получит уведомление и свяжется с вами.",
            parse_mode='Markdown',
            reply_markup=kb
        )
        return

    # Подтверждение
    if data == 'confirm':
        slot = context.user_data.get('slot', '')
        name = context.user_data.get('name', user.first_name)
        display = context.user_data.get('slot_display', slot)

        if is_slot_taken(slot):
            await q.message.reply_text(
                "Это время только что заняли 😔 Начните запись заново.",
                reply_markup=main_kb()
            )
            return

        save_booking(user.id, user.username, name, slot)
        context.user_data.clear()

        try:
            await context.bot.send_message(
                ADMIN_ID,
                f"🎯 *Новая запись на собеседование!*\n\n"
                f"👤 {name}\n"
                f"📱 @{user.username or '—'} · ID: `{user.id}`\n"
                f"📅 {display}",
                parse_mode='Markdown'
            )
        except Exception:
            pass

        await q.message.reply_text(
            f"✅ *Запись подтверждена!*\n\n"
            f"📅 {display}\n\n"
            f"Ольга свяжется с вами накануне созвона.\n"
            f"Если нужно перенести — напишите @OlgaTurreva",
            parse_mode='Markdown'
        )
        return


# ─── Ежедневный отчёт ────────────────────────────────────────────────────────

async def daily_report(context: ContextTypes.DEFAULT_TYPE):
    tomorrow = (date.today() + timedelta(days=1)).strftime('%Y-%m-%d')
    today_str = date.today().strftime('%Y-%m-%d')
    td = date.today()

    with get_db() as conn:
        bookings = conn.execute(
            "SELECT name, username, slot FROM bookings "
            "WHERE slot LIKE ? AND status='active' ORDER BY slot",
            (f'{tomorrow}%',)
        ).fetchall()

        new_users = conn.execute(
            "SELECT COUNT(*) FROM users WHERE joined_at LIKE ?",
            (f'{today_str}%',)
        ).fetchone()[0]

        messages = conn.execute(
            "SELECT COUNT(*) FROM log WHERE created_at LIKE ?",
            (f'{today_str}%',)
        ).fetchone()[0]

        activity = conn.execute(
            "SELECT first_name, username, text, created_at FROM log "
            "WHERE created_at LIKE ? ORDER BY created_at",
            (f'{today_str}%',)
        ).fetchall()

    report = (
        f"📊 *Отчёт за {td.day} {MONTHS_SHORT[td.month]}*\n\n"
        f"👤 Новых пользователей: {new_users}\n"
        f"💬 Сообщений получено: {messages}\n\n"
    )

    if bookings:
        report += f"📅 *Записи на завтра:*\n"
        for name, username, slot in bookings:
            t = slot.split(' ')[1]
            report += f"• {t} мск — {name} (@{username or '—'})\n"
    else:
        report += "📅 Записей на завтра нет.\n"

    if activity:
        report += f"\n💬 *Сообщения за день:*\n"
        for first_name, username, text, at in activity[:15]:
            short = text[:50] + ('…' if len(text) > 50 else '')
            report += f"• {at[11:16]} {first_name}: _{short}_\n"
        if len(activity) > 15:
            report += f"_...и ещё {len(activity) - 15} сообщений_\n"

    try:
        await context.bot.send_message(ADMIN_ID, report, parse_mode='Markdown')
    except Exception as e:
        logger.error(f"daily_report error: {e}")


# ─── Запуск ──────────────────────────────────────────────────────────────────

def main():
    init_db()

    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler('start', start))
    app.add_handler(CallbackQueryHandler(on_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_message))

    # Ежедневный отчёт в 21:00 мск
    app.job_queue.run_daily(
        daily_report,
        time=dtime(hour=21, minute=0, tzinfo=MSK)
    )

    logger.info("Бот запущен")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()
