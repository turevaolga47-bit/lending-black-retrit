#!/usr/bin/env python3
"""
Telegram-бот Чёрного Ретрита Болгария
Воронка: квалификация → прогрев → собеседование → онбординг
Администратор: уведомления, отчёты, статистика
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

logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN    = os.environ.get('BOT_TOKEN', '')
ADMIN_ID = int(os.environ.get('ADMIN_ID', '7851352670'))
MSK      = pytz.timezone('Europe/Moscow')
MAX_SEATS = 8  # мест в группе

DAYS_RU     = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс']
MONTHS_RU   = ['','января','февраля','марта','апреля','мая','июня',
                'июля','августа','сентября','октября','ноября','декабря']
MONTHS_SHORT= ['','янв','фев','мар','апр','май','июн',
                'июл','авг','сен','окт','ноя','дек']

os.makedirs('data', exist_ok=True)

# ═══════════════════════════════════════════════════════════════════════════════
# БАЗА ДАННЫХ
# ═══════════════════════════════════════════════════════════════════════════════

def get_db():
    return sqlite3.connect('data/bot.db')

def init_db():
    with get_db() as c:
        c.execute('''CREATE TABLE IF NOT EXISTS bookings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER, username TEXT, name TEXT,
            slot TEXT, created_at TEXT, status TEXT DEFAULT 'active'
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT, first_name TEXT, joined_at TEXT,
            situation TEXT, preferred_month TEXT, with_friend TEXT,
            temperature TEXT DEFAULT 'warm'
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER, username TEXT, first_name TEXT,
            text TEXT, created_at TEXT
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS waitlist (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER, username TEXT, name TEXT,
            preferred_month TEXT, created_at TEXT
        )''')

def register_user(user):
    with get_db() as c:
        row = c.execute('SELECT 1 FROM users WHERE user_id=?', (user.id,)).fetchone()
        if not row:
            c.execute('INSERT INTO users (user_id,username,first_name,joined_at) VALUES (?,?,?,?)',
                      (user.id, user.username, user.first_name,
                       datetime.now(MSK).strftime('%Y-%m-%d %H:%M')))
            return True
    return False

def update_user_qual(user_id, field, value):
    with get_db() as c:
        c.execute(f'UPDATE users SET {field}=? WHERE user_id=?', (value, user_id))

def log_message(user, text):
    with get_db() as c:
        c.execute('INSERT INTO log (user_id,username,first_name,text,created_at) VALUES (?,?,?,?,?)',
                  (user.id, user.username, user.first_name, text,
                   datetime.now(MSK).strftime('%Y-%m-%d %H:%M')))

def booked_count():
    with get_db() as c:
        return c.execute("SELECT COUNT(*) FROM bookings WHERE status='active'").fetchone()[0]

def seats_left():
    return max(0, MAX_SEATS - booked_count())

def is_slot_taken(slot_str):
    with get_db() as c:
        return c.execute("SELECT 1 FROM bookings WHERE slot=? AND status='active'",
                         (slot_str,)).fetchone() is not None

def save_booking(user_id, username, name, slot):
    with get_db() as c:
        c.execute('INSERT INTO bookings (user_id,username,name,slot,created_at) VALUES (?,?,?,?,?)',
                  (user_id, username, name, slot,
                   datetime.now(MSK).strftime('%Y-%m-%d %H:%M')))

def save_waitlist(user_id, username, name, month):
    with get_db() as c:
        c.execute('INSERT INTO waitlist (user_id,username,name,preferred_month,created_at) VALUES (?,?,?,?,?)',
                  (user_id, username, name, month,
                   datetime.now(MSK).strftime('%Y-%m-%d %H:%M')))

def get_available_slots(hours_range, days_ahead=7):
    booked = set()
    with get_db() as c:
        for row in c.execute("SELECT slot FROM bookings WHERE status='active'"):
            booked.add(row[0])
    slots = []
    now = datetime.now(MSK)
    for offset in range(1, days_ahead + 1):
        d = now.date() + timedelta(days=offset)
        if d.weekday() == 6:
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

# ═══════════════════════════════════════════════════════════════════════════════
# КОНТЕНТ
# ═══════════════════════════════════════════════════════════════════════════════

def seats_line():
    left = seats_left()
    if left <= 2:
        return f"🔴 *Осталось {left} место{'а' if left==2 else ''}* из {MAX_SEATS}"
    elif left <= 4:
        return f"🟡 Свободно {left} из {MAX_SEATS} мест"
    else:
        return f"🟢 Открыта запись · {left} мест из {MAX_SEATS}"

INFO = {
    'dates': (
        "📅 *Даты и стоимость 2026*\n\n"
        "• Май 20–30 · *200 000 ₽* _(стартовая цена первого заезда)_\n"
        "• Июнь 20–30 · *300 000 ₽*\n"
        "• Июль 20–30 · *350 000 ₽*\n"
        "• Август 20–30 · *350 000 ₽*\n"
        "• Сентябрь 3–13 · *300 000 ₽*\n"
        "• Октябрь 1–10 · *200 000 ₽*\n\n"
        "✅ *Включено:* проживание 10 дней, питание 3 раза (повар в доме), "
        "вся программа ретрита, физиотерапия, кризисная сессия, все материалы.\n"
        "❌ *Не включено:* перелёт, личные расходы.\n\n"
        "💡 Чем раньше бронируете — тем ниже цена. "
        "Первый заезд (май) — самый доступный."
    ),
    'format': (
        "🔄 *Формат ретрита*\n\n"
        "*10 дней / 9 ночей.* Это единый цикл — нельзя приехать на часть.\n\n"
        "• Дни 1–2: замедление, знакомство с группой\n"
        "• Дни 3–5: Группа А — работа с закрытыми глазами, Группа Б — поддержка\n"
        "• День 6: интеграция, обмен, смена ролей\n"
        "• Дни 7–9: Группа Б погружается, Группа А — опора\n"
        "• День 10: ритуал закрытия, личный план на 3 месяца\n\n"
        "*Каждый день:* телесные практики, психологическая работа, "
        "физиотерапия, медитация у воды.\n\n"
        "📱 Телефон — с собой, но в практиках рекомендуем убирать. "
        "WiFi есть. Связь с домом — без ограничений."
    ),
    'safety': (
        "🛡 *Безопасность*\n\n"
        "• Ольга рядом *24/7* — 34 года кризисной практики\n"
        "• Страх и слёзы — нормальная часть процесса, не исключение\n"
        "• Выйти из практики можно в любой момент без объяснений\n"
        "• Маску для глаз привозите сами — это ваша вещь, ваша граница\n"
        "• Рядом всегда есть участница — к морю, к столу — за руку\n"
        "• Предварительное собеседование — исключаем противопоказания\n\n"
        "*Противопоказания:* острые психотические состояния, тяжёлые "
        "психиатрические диагнозы в обострении, беременность.\n\n"
        "_Всё обсуждаем на личном созвоне — честно._"
    ),
    'payment': (
        "💳 *Оплата*\n\n"
        "*Два этапа:*\n"
        "1. Предоплата — на российскую карту _(бронирует место)_\n"
        "2. Остаток — наличными в евро в день приезда\n\n"
        "Стоимость в рублях, пересчитываем по курсу в евро.\n\n"
        "ℹ️ *Про наличные через границу:*\n"
        "Физическое лицо вправе провезти до 10 000 USD без декларирования. "
        "Сумма ретрита укладывается в этот лимит.\n\n"
        "_Предоплата не возвращается — возможен перенос на другой заезд._"
    ),
    'location': (
        "📍 *Место — Святой Влас, Болгария*\n\n"
        "• 200 метров от Чёрного моря\n"
        "• Собственные апартаменты Ольги — куплены в феврале 2025 специально для ретрита\n"
        "• Новый ремонт, новая мебель, балкон, кухня, кондиционер\n"
        "• Трёхразовое питание — повар готовит прямо в доме\n\n"
        "*Как добраться:*\n"
        "Москва / Питер → Стамбул → Бургас (~4 часа)\n"
        "Бургас → Святой Влас — 35 км. Трансфер при раннем бронировании — бесплатно.\n\n"
        "*Виза:*\n"
        "Нужен загранпаспорт и болгарская виза. Болгария — в Шенгене, но для граждан России виза оформляется отдельно.\n"
        "Консульство Болгарии в Москве и Санкт-Петербурге. Подаётся заранее — на период поездки.\n\n"
        "📞 *Связь с Ольгой:* +49 176 7576 5576 (WhatsApp / звонок)"
    ),
    'about': (
        "🖤 *Чёрный Ретрит · Болгария · 2026*\n\n"
        "10 дней настоящей работы с телом и психикой на берегу Чёрного моря.\n\n"
        "*Ведущая:* Ph.Dr. Ольга Турьева\n"
        "Кризисный психолог · физиотерапевт · 34 года практики\n"
        "Данибузский университет, Словакия\n\n"
        "*Для кого:* женщины в выгорании, кризисе, потере себя.\n"
        "Тех, кому отдых уже не помогает — нужна другая работа.\n\n"
        "Это не медитация. Не йога. Не спа.\n"
        "Это встреча с собой — глубокая, настоящая."
    ),
    'food': (
        "🍽 *Питание*\n\n"
        "Трёхразовое питание включено в стоимость.\n"
        "Повар готовит прямо в доме — завтрак, обед, ужин.\n\n"
        "Пожелания по питанию (вегетарианство, аллергии) — "
        "обсуждаем на собеседовании, всё учтём."
    ),
    'group': (
        "👭 *Группа*\n\n"
        "До 8 человек — только русскоязычные.\n"
        "Каждая проходит личное собеседование.\n\n"
        "Случайных людей нет. Как правило — женщины, которые уже пробовали "
        "терапию или курсы и понимают, что нужно что-то глубже.\n\n"
        "Маленькая группа — это не просто комфорт, это условие метода: "
        "пока одна работает с закрытыми глазами, другая становится её опорой."
    ),
    'friend': (
        "👭 *Приехать с подругой*\n\n"
        "Это отличная идея — и выгодная!\n\n"
        "*Реферальная программа:*\n"
        "Пригласите подругу на тот же заезд — "
        "сумма бонуса (10% от её участия) вычитается из вашего остатка наличными в евро.\n\n"
        "Пример: ваш заезд стоит 300 000 ₽ → бонус 30 000 ₽ → "
        "платите наличными на 30 000 меньше.\n\n"
        "Как работает: подруга при записи указывает ваше имя. "
        "После подтверждения её участия бонус применяется автоматически.\n\n"
        "_Без ограничений по количеству приглашений._"
    ),
    'after': (
        "🌱 *После ретрита*\n\n"
        "Ретрит — не точка, а переход.\n\n"
        "• Первые 2–3 недели: психика и тело продолжают перестраиваться — это нормально\n"
        "• Ольга остаётся на связи при острой необходимости\n"
        "• Участницы получают приоритетный доступ к индивидуальной работе с Ольгой\n"
        "• Группа остаётся в контакте — поддержка продолжается\n\n"
        "Многие приезжают снова — уже с другим запросом и из другого места внутри."
    ),
    'think': (
        "💭 *«Надо подумать»*\n\n"
        "Это честно — и правильно.\n\n"
        "Чаще всего за «надо подумать» стоит один из этих вопросов:\n\n"
        "❓ *Смогу ли я уехать на 10 дней?*\n"
        "→ Большинство находит возможность, когда есть настоящий мотив. "
        "На собеседовании разберём конкретно вашу ситуацию.\n\n"
        "❓ *Дорого*\n"
        "→ Майский заезд — самый доступный: 200 000 ₽ с проживанием и питанием. "
        "Это меньше, чем многие тратят на бесполезные курсы за год.\n\n"
        "❓ *Страшно*\n"
        "→ Страх — значит, что тема живая. На собеседовании Ольга честно "
        "скажет, подходит ли вам этот формат прямо сейчас.\n\n"
        "❓ *Не знаю, подойдёт ли мне*\n"
        "→ Именно для этого — собеседование. Не продажа, а разговор.\n\n"
        "_Самый простой шаг — записаться на 20-минутный звонок с Ольгой._"
    ),
    'expensive': (
        "💰 *О стоимости*\n\n"
        "200 000–350 000 ₽ — это 10 дней, которые включают:\n\n"
        "• Проживание в собственных апартаментах у моря\n"
        "• Трёхразовое питание (повар в доме)\n"
        "• Всю программу ретрита с Ph.Dr. психологом\n"
        "• Физиотерапию тела (ноги разной длины, позвоночник)\n"
        "• Кризисную индивидуальную сессию\n"
        "• Технику выхода из стресса — навык на всю жизнь\n"
        "• Поддержку Ольги после ретрита\n\n"
        "Для сравнения: 10 сессий у психолога в Москве — "
        "от 100 000 ₽, без моря, без тела, без глубины.\n\n"
        "_Майский заезд — стартовая цена: 200 000 ₽._"
    ),
}

FAQ_MAP = {
    # Цены / даты
    'цен': 'dates', 'стоимост': 'dates', 'дорого': 'expensive',
    'сколько стоит': 'dates', 'почем': 'dates', 'прайс': 'dates',
    'дат': 'dates', 'когда': 'dates', 'месяц': 'dates',
    'май': 'dates', 'июн': 'dates', 'июл': 'dates',
    'август': 'dates', 'сентябр': 'dates', 'октябр': 'dates',
    'расписан': 'dates',
    # Формат
    'формат': 'format', 'програм': 'format', 'глаза': 'format',
    'повязк': 'format', 'маска': 'format', 'день': 'format',
    'расписани': 'format', '10 дней': 'format', 'телефон': 'format',
    'интернет': 'format', 'вайфай': 'format', 'wifi': 'format',
    # Безопасность
    'безопас': 'safety', 'страшно': 'safety', 'страх': 'safety',
    'противопоказан': 'safety', 'психиатр': 'safety', 'панику': 'safety',
    'накроет': 'safety', 'опасно': 'safety',
    # Оплата
    'оплат': 'payment', 'деньг': 'payment', 'евро': 'payment',
    'перевод': 'payment', 'налич': 'payment', 'границ': 'payment',
    'предоплат': 'payment', 'бронир': 'payment', 'карт': 'payment',
    # Место
    'болгар': 'location', 'квартир': 'location', 'апартам': 'location',
    'добрат': 'location', 'перелет': 'location', 'виза': 'location',
    'аэропорт': 'location', 'бургас': 'location', 'море': 'location',
    'святой влас': 'location', 'черное море': 'location',
    # Питание
    'еда': 'food', 'питан': 'food', 'повар': 'food', 'завтрак': 'food',
    'обед': 'food', 'ужин': 'food', 'аллерг': 'food', 'вегетар': 'food',
    # Группа
    'группа': 'group', 'кто будет': 'group', 'участниц': 'group',
    'сколько человек': 'group', 'кто ещё': 'group',
    # Подруга / реферал
    'подруг': 'friend', 'вместе': 'friend', 'рефер': 'friend',
    'скидк': 'friend', 'пригласит': 'friend',
    # После ретрита
    'после': 'after', 'поддержк': 'after', 'интеграц': 'after',
    # Сомнения
    'надо подумать': 'think', 'подумать': 'think', 'не уверен': 'think',
    'сомнев': 'think', 'боюсь': 'think', 'не знаю': 'think',
    'дорого': 'expensive', 'не могу позволить': 'expensive',
    # О ретрите
    'что такое': 'about', 'что это': 'about', 'расскаж': 'about',
    'подробн': 'about', 'чёрный ретрит': 'about', 'черный ретрит': 'about',
    'об ольге': 'about', 'кто вы': 'about',
}


def main_kb():
    left = seats_left()
    seat_btn = f"🔴 Осталось {left} мест — записаться" if left <= 3 else "📞 Записаться на собеседование"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📅 Даты и цены", callback_data='i_dates'),
         InlineKeyboardButton("🔄 Формат", callback_data='i_format')],
        [InlineKeyboardButton("🛡 Безопасность", callback_data='i_safety'),
         InlineKeyboardButton("📍 Место", callback_data='i_location')],
        [InlineKeyboardButton("🍽 Питание", callback_data='i_food'),
         InlineKeyboardButton("👭 С подругой", callback_data='i_friend')],
        [InlineKeyboardButton("💰 О стоимости", callback_data='i_expensive'),
         InlineKeyboardButton("🌱 После ретрита", callback_data='i_after')],
        [InlineKeyboardButton("❓ Задать вопрос", callback_data='ask_question')],
        [InlineKeyboardButton(seat_btn, callback_data='qualify')],
        [InlineKeyboardButton("📱 WhatsApp Ольги", url='https://wa.me/4917675765576')],
    ])

def qualify_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔥 Выгорание / пустота / нет сил", callback_data='q1_burnout')],
        [InlineKeyboardButton("🌀 Кризис / развод / потеря", callback_data='q1_crisis')],
        [InlineKeyboardButton("🔍 Потеряла себя в ролях", callback_data='q1_lost')],
        [InlineKeyboardButton("✨ Хочу глубоких перемен", callback_data='q1_change')],
    ])

# ═══════════════════════════════════════════════════════════════════════════════
# ОБРАБОТЧИКИ
# ═══════════════════════════════════════════════════════════════════════════════

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    is_new = register_user(user)
    context.user_data.clear()

    if is_new:
        try:
            await context.bot.send_message(
                ADMIN_ID,
                f"👤 *Новый пользователь*\n"
                f"{user.first_name} {user.last_name or ''} · @{user.username or '—'}\n"
                f"ID: `{user.id}`",
                parse_mode='Markdown'
            )
        except Exception:
            pass

    left = seats_left()
    scarcity = f"\n\n{seats_line()}" if left <= 4 else ""

    await update.message.reply_text(
        f"Здравствуйте, {user.first_name}! 🖤\n\n"
        f"Это бот *Чёрного Ретрита Болгария* — "
        f"10 дней работы с телом и психикой на берегу Чёрного моря.\n\n"
        f"Ведущая — Ph.Dr. Ольга Турьева, кризисный психолог, 34 года практики.\n"
        f"Группа до 8 человек. Лето 2026.{scarcity}\n\n"
        f"Выберите что вас интересует — или просто задайте вопрос:",
        parse_mode='Markdown',
        reply_markup=main_kb()
    )


async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = update.message.text
    state = context.user_data.get('state')

    log_message(user, text)

    # ── Ввод имени ──
    if state == 'wait_name':
        context.user_data['name'] = text
        context.user_data['state'] = None
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🌅 До обеда (10:00–13:00)", callback_data='tp_morning')],
            [InlineKeyboardButton("☀️ После обеда (13:00–18:00)", callback_data='tp_afternoon')],
            [InlineKeyboardButton("🌆 Вечером (18:00–21:00)", callback_data='tp_evening')],
        ])
        await update.message.reply_text(
            f"Отлично, {text}! 😊\n\n"
            "Когда удобнее созвониться с Ольгой?\n"
            "_(Время московское, понедельник–суббота)_",
            parse_mode='Markdown',
            reply_markup=kb
        )
        return

    # ── Режим вопроса ──
    if state == 'wait_question':
        context.user_data['state'] = None
        tl = text.lower()
        for kw, key in FAQ_MAP.items():
            if kw in tl:
                try:
                    await context.bot.send_message(
                        ADMIN_ID,
                        f"❓ *Вопрос:* {user.first_name} (@{user.username or '—'})\n_{text}_",
                        parse_mode='Markdown'
                    )
                except Exception:
                    pass
                await update.message.reply_text(
                    INFO[key], parse_mode='Markdown', reply_markup=main_kb()
                )
                return
        # Вопрос не распознан — передать Ольге
        try:
            await context.bot.send_message(
                ADMIN_ID,
                f"❓ *Вопрос без ответа*\n{user.first_name} (@{user.username or '—'}):\n_{text}_",
                parse_mode='Markdown'
            )
        except Exception:
            pass
        await update.message.reply_text(
            "Спасибо за вопрос — я передала его Ольге, она ответит лично.\n\n"
            "Пока можете изучить другие темы:",
            reply_markup=main_kb()
        )
        return

    # ── FAQ по ключевым словам ──
    tl = text.lower()
    for kw, key in FAQ_MAP.items():
        if kw in tl:
            try:
                await context.bot.send_message(
                    ADMIN_ID,
                    f"💬 *Вопрос:* {user.first_name} (@{user.username or '—'})\n_{text}_",
                    parse_mode='Markdown'
                )
            except Exception:
                pass
            await update.message.reply_text(
                INFO[key], parse_mode='Markdown', reply_markup=main_kb()
            )
            return

    # ── Неизвестный вопрос ──
    try:
        await context.bot.send_message(
            ADMIN_ID,
            f"❓ *Вопрос без ответа*\n{user.first_name} (@{user.username or '—'}):\n_{text}_",
            parse_mode='Markdown'
        )
    except Exception:
        pass

    await update.message.reply_text(
        "Этот вопрос я передала Ольге — она ответит лично.\n\n"
        "Или выберите тему из меню:",
        reply_markup=main_kb()
    )


async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = q.data
    user = q.from_user

    # ── Информационные блоки ──
    if data.startswith('i_'):
        key = data[2:]
        if key in INFO:
            await q.message.reply_text(INFO[key], parse_mode='Markdown', reply_markup=main_kb())
        return

    # ── Задать вопрос ──
    if data == 'ask_question':
        context.user_data['state'] = 'wait_question'
        await q.message.reply_text(
            "✍️ Напишите ваш вопрос — я отвечу сразу.\n\n"
            "_Спрашивайте про программу, диагнозы, противопоказания, формат, "
            "стоимость, визу, питание — всё что важно для вашего решения._",
            parse_mode='Markdown'
        )
        return

    # ── Начало квалификации ──
    if data == 'qualify':
        if seats_left() == 0:
            await q.message.reply_text(
                "😔 На ближайший заезд мест не осталось.\n\n"
                "Хотите попасть в *лист ожидания*? "
                "Если кто-то откажется или откроется следующий заезд — сообщим первой.",
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("✅ Добавить в лист ожидания", callback_data='waitlist')
                ]])
            )
            return
        await q.message.reply_text(
            "Чтобы Ольга подготовилась к разговору — один короткий вопрос:\n\n"
            "*Что привело вас сюда?*",
            parse_mode='Markdown',
            reply_markup=qualify_kb()
        )
        return

    # ── Квалификация: ситуация ──
    if data.startswith('q1_'):
        situations = {
            'q1_burnout': 'Выгорание / пустота / нет сил',
            'q1_crisis':  'Кризис / развод / потеря',
            'q1_lost':    'Потеряла себя в ролях',
            'q1_change':  'Хочу глубоких перемен',
        }
        update_user_qual(user.id, 'situation', situations[data])
        try:
            await context.bot.send_message(
                ADMIN_ID,
                f"🔍 *Квалификация:* {user.first_name} (@{user.username or '—'})\n"
                f"Ситуация: _{situations[data]}_",
                parse_mode='Markdown'
            )
        except Exception:
            pass

        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🌸 Май (от 200 000 ₽)", callback_data='q2_may'),
             InlineKeyboardButton("☀️ Июнь (300 000 ₽)", callback_data='q2_jun')],
            [InlineKeyboardButton("🏖 Июль (350 000 ₽)", callback_data='q2_jul'),
             InlineKeyboardButton("🌊 Август (350 000 ₽)", callback_data='q2_aug')],
            [InlineKeyboardButton("🍂 Сентябрь (300 000 ₽)", callback_data='q2_sep'),
             InlineKeyboardButton("🍁 Октябрь (200 000 ₽)", callback_data='q2_oct')],
        ])
        await q.message.reply_text(
            "Какой месяц вам ближе?",
            reply_markup=kb
        )
        return

    # ── Квалификация: месяц ──
    if data.startswith('q2_'):
        months = {
            'q2_may': 'Май', 'q2_jun': 'Июнь', 'q2_jul': 'Июль',
            'q2_aug': 'Август', 'q2_sep': 'Сентябрь', 'q2_oct': 'Октябрь',
        }
        update_user_qual(user.id, 'preferred_month', months[data])
        try:
            await context.bot.send_message(
                ADMIN_ID,
                f"📅 {user.first_name} (@{user.username or '—'}) выбрал(а) *{months[data]}*",
                parse_mode='Markdown'
            )
        except Exception:
            pass

        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("Одна", callback_data='q3_alone')],
            [InlineKeyboardButton("С подругой / ищу пару", callback_data='q3_friend')],
        ])
        await q.message.reply_text(
            "Планируете приехать одна или с подругой?\n\n"
            "_Группа камерная — нам важно сохранить парность состава_",
            parse_mode='Markdown',
            reply_markup=kb
        )
        return

    # ── Квалификация: с кем едет ──
    if data.startswith('q3_'):
        with_friend = 'С подругой' if data == 'q3_friend' else 'Одна'
        update_user_qual(user.id, 'with_friend', with_friend)

        extra = ''
        if data == 'q3_friend':
            extra = "\n\n👭 Отлично! Если подруга тоже запишется — получите бонус 10% от её стоимости на ваш остаток."
        else:
            left = seats_left()
            if left <= 3:
                extra = f"\n\n🔴 Осталось {left} места — советуем не откладывать запись."

        context.user_data['state'] = 'wait_name'
        await q.message.reply_text(
            f"Отлично!{extra}\n\n"
            "Как вас зовут? Напишите имя и фамилию:",
            parse_mode='Markdown'
        )
        return

    # ── Выбор времени суток ──
    if data.startswith('tp_'):
        pref = data[3:]
        hours = {
            'morning':   range(10, 13),
            'afternoon': range(13, 18),
            'evening':   range(18, 21),
        }[pref]
        slots = get_available_slots(hours)

        if not slots:
            await q.message.reply_text(
                "В это время нет свободных слотов на ближайшую неделю.\n"
                "Попробуйте другое время или напишите Ольге напрямую: @OlgaTurreva",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("⬅️ Другое время", callback_data='tp_back')
                ]])
            )
            return

        keyboard = [[InlineKeyboardButton(d, callback_data=f's_{v}')] for d, v in slots]
        keyboard.append([InlineKeyboardButton("⬅️ Другое время", callback_data='tp_back')])
        await q.message.reply_text("Выберите удобное время:", reply_markup=InlineKeyboardMarkup(keyboard))
        return

    if data == 'tp_back':
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🌅 До обеда (10:00–13:00)", callback_data='tp_morning')],
            [InlineKeyboardButton("☀️ После обеда (13:00–18:00)", callback_data='tp_afternoon')],
            [InlineKeyboardButton("🌆 Вечером (18:00–21:00)", callback_data='tp_evening')],
        ])
        await q.message.reply_text("Когда удобнее?", reply_markup=kb)
        return

    # ── Выбор слота ──
    if data.startswith('s_'):
        slot = data[2:]
        if is_slot_taken(slot):
            await q.message.reply_text(
                "Это время только что заняли 😔",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("⬅️ Выбрать другое", callback_data='tp_back')
                ]])
            )
            return

        context.user_data['slot'] = slot
        name = context.user_data.get('name', user.first_name)
        display = format_slot(slot)
        context.user_data['slot_display'] = display

        await q.message.reply_text(
            f"*Подтвердите запись:*\n\n"
            f"👤 {name}\n"
            f"📅 {display}\n\n"
            f"После подтверждения Ольга получит уведомление и свяжется с вами накануне.",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("✅ Подтвердить", callback_data='confirm'),
                InlineKeyboardButton("✏️ Изменить время", callback_data='tp_back'),
            ]])
        )
        return

    # ── Подтверждение записи ──
    if data == 'confirm':
        slot    = context.user_data.get('slot', '')
        name    = context.user_data.get('name', user.first_name)
        display = context.user_data.get('slot_display', slot)

        if is_slot_taken(slot):
            await q.message.reply_text("Время заняли 😔 Выберите другое.", reply_markup=main_kb())
            return

        save_booking(user.id, user.username, name, slot)
        context.user_data.clear()
        left = seats_left()

        # Уведомление админу
        try:
            situation = ''
            month = ''
            with get_db() as c:
                row = c.execute('SELECT situation, preferred_month, with_friend FROM users WHERE user_id=?',
                                (user.id,)).fetchone()
                if row:
                    situation = row[0] or '—'
                    month     = row[1] or '—'
                    friend    = row[2] or '—'
            await context.bot.send_message(
                ADMIN_ID,
                f"🎯 *Новая запись на собеседование!*\n\n"
                f"👤 {name}\n"
                f"📱 @{user.username or '—'} · ID: `{user.id}`\n"
                f"📅 {display}\n\n"
                f"Ситуация: _{situation}_\n"
                f"Предпочтительный месяц: _{month}_\n"
                f"С кем едет: _{friend}_\n\n"
                f"Осталось мест: {left}",
                parse_mode='Markdown'
            )
        except Exception:
            pass

        # Онбординг после записи
        await q.message.reply_text(
            f"✅ *Запись подтверждена!*\n\n"
            f"📅 {display}\n\n"
            f"Ольга свяжется с вами в указанное время для знакомства и ответов на вопросы.\n\n"
            f"*Что взять на созвон:*\n"
            f"• Зачем вы хотите на ретрит — в паре предложений\n"
            f"• Ваши вопросы и сомнения — всё лучше обсудить честно\n"
            f"• 20–30 минут свободного времени\n\n"
            f"_Если нужно перенести — напишите @OlgaTurreva_",
            parse_mode='Markdown'
        )
        return

    # ── Лист ожидания ──
    if data == 'waitlist':
        context.user_data['state'] = 'wait_name'
        context.user_data['waitlist'] = True
        await q.message.reply_text("Как вас зовут? Напишите имя и фамилию:")
        return


# ═══════════════════════════════════════════════════════════════════════════════
# ADMIN КОМАНДЫ
# ═══════════════════════════════════════════════════════════════════════════════

async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    today = date.today().strftime('%Y-%m-%d')
    with get_db() as c:
        total_users   = c.execute('SELECT COUNT(*) FROM users').fetchone()[0]
        new_today     = c.execute('SELECT COUNT(*) FROM users WHERE joined_at LIKE ?', (f'{today}%',)).fetchone()[0]
        total_bookings= c.execute("SELECT COUNT(*) FROM bookings WHERE status='active'").fetchone()[0]
        waitlist_count= c.execute('SELECT COUNT(*) FROM waitlist').fetchone()[0]
        msgs_today    = c.execute('SELECT COUNT(*) FROM log WHERE created_at LIKE ?', (f'{today}%',)).fetchone()[0]

    await update.message.reply_text(
        f"📊 *Статистика*\n\n"
        f"👤 Всего пользователей: {total_users}\n"
        f"🆕 Новых сегодня: {new_today}\n"
        f"📅 Записей на собеседование: {total_bookings}\n"
        f"🔴 Мест осталось: {seats_left()}\n"
        f"⏳ Лист ожидания: {waitlist_count}\n"
        f"💬 Сообщений сегодня: {msgs_today}",
        parse_mode='Markdown'
    )

async def cmd_bookings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    with get_db() as c:
        rows = c.execute(
            "SELECT name, username, slot FROM bookings WHERE status='active' ORDER BY slot"
        ).fetchall()

    if not rows:
        await update.message.reply_text("Записей нет.")
        return

    text = "📅 *Все активные записи:*\n\n"
    for name, username, slot in rows:
        d, t = slot.split(' ')
        dt = datetime.strptime(d, '%Y-%m-%d')
        text += f"• {dt.day} {MONTHS_SHORT[dt.month]} {t} — {name} (@{username or '—'})\n"
    await update.message.reply_text(text, parse_mode='Markdown')

async def cmd_leads(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    with get_db() as c:
        rows = c.execute(
            "SELECT first_name, username, joined_at, situation, preferred_month, with_friend, temperature "
            "FROM users ORDER BY joined_at DESC LIMIT 20"
        ).fetchall()

    if not rows:
        await update.message.reply_text("Лидов нет.")
        return

    text = "🎯 *Последние 20 лидов:*\n\n"
    for fn, un, ja, sit, mon, fri, temp in rows:
        text += (f"*{fn}* @{un or '—'} · {ja[:10]}\n"
                 f"  _{sit or '—'}_ · {mon or '—'} · {fri or '—'}\n\n")
    await update.message.reply_text(text, parse_mode='Markdown')


# ═══════════════════════════════════════════════════════════════════════════════
# ЕЖЕДНЕВНЫЙ ОТЧЁТ
# ═══════════════════════════════════════════════════════════════════════════════

async def daily_report(context: ContextTypes.DEFAULT_TYPE):
    tomorrow  = (date.today() + timedelta(days=1)).strftime('%Y-%m-%d')
    today_str = date.today().strftime('%Y-%m-%d')
    td        = date.today()

    with get_db() as c:
        bookings   = c.execute(
            "SELECT name, username, slot FROM bookings WHERE slot LIKE ? AND status='active' ORDER BY slot",
            (f'{tomorrow}%',)
        ).fetchall()
        new_users  = c.execute('SELECT COUNT(*) FROM users WHERE joined_at LIKE ?', (f'{today_str}%',)).fetchone()[0]
        messages   = c.execute('SELECT COUNT(*) FROM log WHERE created_at LIKE ?', (f'{today_str}%',)).fetchone()[0]
        activity   = c.execute(
            'SELECT first_name, username, text, created_at FROM log WHERE created_at LIKE ? ORDER BY created_at',
            (f'{today_str}%',)
        ).fetchall()
        waitlist   = c.execute('SELECT COUNT(*) FROM waitlist').fetchone()[0]

    report = (
        f"📊 *Отчёт за {td.day} {MONTHS_SHORT[td.month]}*\n\n"
        f"👤 Новых: {new_users} · 💬 Сообщений: {messages}\n"
        f"🔴 Мест осталось: {seats_left()} · ⏳ Лист ожидания: {waitlist}\n\n"
    )

    if bookings:
        report += "*Созвоны завтра:*\n"
        for name, username, slot in bookings:
            t = slot.split(' ')[1]
            report += f"• {t} — {name} (@{username or '—'})\n"
    else:
        report += "Созвонов завтра нет.\n"

    if activity:
        report += f"\n*Сообщения за день:*\n"
        for fn, un, text, at in activity[:10]:
            short = text[:40] + ('…' if len(text) > 40 else '')
            report += f"• {at[11:16]} {fn}: _{short}_\n"
        if len(activity) > 10:
            report += f"_...ещё {len(activity)-10}_\n"

    try:
        await context.bot.send_message(ADMIN_ID, report, parse_mode='Markdown')
    except Exception as e:
        logger.error(f"daily_report error: {e}")


# ═══════════════════════════════════════════════════════════════════════════════
# ЗАПУСК
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    init_db()
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('stats', cmd_stats))
    app.add_handler(CommandHandler('bookings', cmd_bookings))
    app.add_handler(CommandHandler('leads', cmd_leads))
    app.add_handler(CallbackQueryHandler(on_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_message))

    app.job_queue.run_daily(daily_report, time=dtime(hour=21, minute=0, tzinfo=MSK))

    logger.info("Бот запущен")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()
