#!/usr/bin/env python3
"""
WhatsApp-бот Чёрного Ретрита Болгария через Green API
Воронка: квалификация → прогрев → собеседование
"""

import os
import time
import sqlite3
import requests
from datetime import datetime
import pytz

INSTANCE_ID    = os.environ.get('GREEN_INSTANCE_ID', '')
INSTANCE_TOKEN = os.environ.get('GREEN_TOKEN', '')
ADMIN_PHONE    = os.environ.get('ADMIN_PHONE', '4917675765576')
BASE_URL       = f"https://api.green-api.com/waInstance{INSTANCE_ID}"
MSK            = pytz.timezone('Europe/Moscow')

os.makedirs('data', exist_ok=True)

# ═══════════════════════════════════════════════════════════════════════════════
# БАЗА ДАННЫХ
# ═══════════════════════════════════════════════════════════════════════════════

def get_db():
    return sqlite3.connect('data/whatsapp.db')

def init_db():
    with get_db() as c:
        c.execute('''CREATE TABLE IF NOT EXISTS users (
            phone TEXT PRIMARY KEY,
            name TEXT,
            state TEXT DEFAULT 'menu',
            situation TEXT,
            preferred_month TEXT,
            joined_at TEXT
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            phone TEXT, name TEXT, text TEXT, created_at TEXT
        )''')

def get_user(phone):
    with get_db() as c:
        row = c.execute('SELECT phone,name,state,situation,preferred_month FROM users WHERE phone=?',
                        (phone,)).fetchone()
        if row:
            return {'phone': row[0], 'name': row[1], 'state': row[2],
                    'situation': row[3], 'preferred_month': row[4]}
    return None

def upsert_user(phone, **kwargs):
    with get_db() as c:
        existing = c.execute('SELECT 1 FROM users WHERE phone=?', (phone,)).fetchone()
        if not existing:
            c.execute('INSERT INTO users (phone, joined_at) VALUES (?, ?)',
                      (phone, datetime.now(MSK).strftime('%Y-%m-%d %H:%M')))
        for key, val in kwargs.items():
            c.execute(f'UPDATE users SET {key}=? WHERE phone=?', (val, phone))

def log_msg(phone, name, text):
    with get_db() as c:
        c.execute('INSERT INTO log (phone,name,text,created_at) VALUES (?,?,?,?)',
                  (phone, name, text, datetime.now(MSK).strftime('%Y-%m-%d %H:%M')))

# ═══════════════════════════════════════════════════════════════════════════════
# GREEN API
# ═══════════════════════════════════════════════════════════════════════════════

def send(phone, text):
    url = f"{BASE_URL}/sendMessage/{INSTANCE_TOKEN}"
    try:
        r = requests.post(url, json={"chatId": f"{phone}@c.us", "message": text}, timeout=15)
        return r.status_code == 200
    except Exception as e:
        print(f"[send error] {e}")
        return False

def notify_admin(text):
    send(ADMIN_PHONE, text)

def enable_incoming():
    url = f"{BASE_URL}/setSettings/{INSTANCE_TOKEN}"
    payload = {
        "incomingWebhook": "yes",
        "outgoingWebhook": "yes",
        "outgoingMessageWebhook": "yes",
        "outgoingAPIMessageWebhook": "yes",
        "markIncomingMessagesReaded": "no"
    }
    try:
        r = requests.post(url, json=payload, timeout=15)
        print(f"[settings] {r.status_code} {r.text}")
    except Exception as e:
        print(f"[settings error] {e}")

def receive_notification():
    url = f"{BASE_URL}/receiveNotification/{INSTANCE_TOKEN}"
    try:
        r = requests.get(url, timeout=25)
        if r.status_code == 200 and r.text and r.text != 'null':
            return r.json()
    except Exception as e:
        print(f"[receive error] {e}")
    return None

def delete_notification(receipt_id):
    url = f"{BASE_URL}/deleteNotification/{INSTANCE_TOKEN}/{receipt_id}"
    try:
        requests.delete(url, timeout=10)
    except Exception as e:
        print(f"[delete error] {e}")

# ═══════════════════════════════════════════════════════════════════════════════
# КОНТЕНТ
# ═══════════════════════════════════════════════════════════════════════════════

MENU_TEXT = (
    "🖤 *Чёрный Ретрит Болгария*\n\n"
    "10 дней работы с телом и психикой на берегу Чёрного моря.\n"
    "Ведущая — Ph.Dr. Ольга Турьева, кризисный психолог, 34 года практики.\n\n"
    "Напишите цифру или задайте вопрос:\n\n"
    "1 — Даты и цены\n"
    "2 — Формат программы\n"
    "3 — Безопасность\n"
    "4 — Место и как добраться\n"
    "5 — Питание\n"
    "6 — Приехать с подругой\n"
    "7 — О стоимости\n"
    "8 — После ретрита\n"
    "9 — Записаться на собеседование\n\n"
    "Или просто напишите свой вопрос ✍️"
)

INFO = {
    'dates': (
        "📅 *Даты и стоимость 2026*\n\n"
        "• Май 20–30 — 200 000 ₽ (стартовая цена первого заезда)\n"
        "• Июнь 20–30 — 300 000 ₽\n"
        "• Июль 20–30 — 350 000 ₽\n"
        "• Август 20–30 — 350 000 ₽\n"
        "• Сентябрь 3–13 — 300 000 ₽\n"
        "• Октябрь 1–10 — 200 000 ₽\n\n"
        "Включено: проживание 10 дней, питание 3 раза (повар в доме), вся программа, "
        "физиотерапия, кризисная индивидуальная сессия, все материалы.\n"
        "Не включено: перелёт, личные расходы.\n\n"
        "Чем раньше бронируете — тем ниже цена."
    ),
    'format': (
        "🔄 *Формат ретрита*\n\n"
        "10 дней / 9 ночей. Это единый цикл — нельзя приехать на часть.\n\n"
        "• Дни 1–2: замедление, знакомство с группой\n"
        "• Дни 3–5: Группа А — работа с закрытыми глазами, Группа Б — поддержка\n"
        "• День 6: интеграция, обмен, смена ролей\n"
        "• Дни 7–9: Группа Б погружается, Группа А — опора\n"
        "• День 10: ритуал закрытия, личный план на 3 месяца\n\n"
        "Каждый день: телесные практики, психологическая работа, физиотерапия, медитация у воды.\n\n"
        "Телефон — с собой, но в практиках рекомендуем убирать. WiFi есть."
    ),
    'safety': (
        "🛡 *Безопасность*\n\n"
        "• Ольга рядом 24/7 — 34 года кризисной практики\n"
        "• Страх и слёзы — нормальная часть процесса\n"
        "• Выйти из практики можно в любой момент без объяснений\n"
        "• Рядом всегда есть участница — поддержка в каждый момент\n"
        "• Предварительное собеседование — исключаем противопоказания\n\n"
        "Противопоказания: острые психотические состояния, тяжёлые психиатрические "
        "диагнозы в обострении, беременность.\n\n"
        "Всё обсуждаем на личном созвоне — честно."
    ),
    'location': (
        "📍 *Место — Святой Влас, Болгария*\n\n"
        "• 200 метров от Чёрного моря\n"
        "• Собственные апартаменты Ольги — куплены специально для ретрита\n"
        "• Новый ремонт, балкон, кухня, кондиционер\n"
        "• Трёхразовое питание — повар готовит прямо в доме\n\n"
        "Как добраться:\n"
        "Москва / Питер → Стамбул → Бургас (~4 часа)\n"
        "Бургас → Святой Влас — 35 км. Трансфер при раннем бронировании — бесплатно.\n\n"
        "Виза:\n"
        "Нужен загранпаспорт и болгарская виза. Болгария — в Шенгене, "
        "но для граждан России виза оформляется отдельно.\n"
        "Консульство Болгарии в Москве и Санкт-Петербурге. Подаётся заранее.\n\n"
        "Связь с Ольгой: +49 176 7576 5576"
    ),
    'food': (
        "🍽 *Питание*\n\n"
        "Трёхразовое питание включено в стоимость.\n"
        "Повар готовит прямо в доме — завтрак, обед, ужин.\n\n"
        "Пожелания по питанию (вегетарианство, аллергии) — "
        "обсуждаем на собеседовании, всё учтём."
    ),
    'friend': (
        "👭 *Приехать с подругой*\n\n"
        "Отличная идея — и выгодная!\n\n"
        "Реферальная программа:\n"
        "Пригласите подругу на тот же заезд — "
        "сумма бонуса (10% от её участия) вычитается из вашего остатка.\n\n"
        "Пример: ваш заезд 300 000 ₽ → бонус 30 000 ₽ → "
        "платите наличными на 30 000 меньше.\n\n"
        "Подруга при записи указывает ваше имя — бонус применяется автоматически."
    ),
    'expensive': (
        "💰 *О стоимости*\n\n"
        "200 000–350 000 ₽ — это 10 дней, которые включают:\n\n"
        "• Проживание у моря в собственных апартаментах\n"
        "• Трёхразовое питание (повар в доме)\n"
        "• Всю программу с Ph.Dr. психологом\n"
        "• Физиотерапию тела\n"
        "• Кризисную индивидуальную сессию\n"
        "• Технику выхода из стресса — навык на всю жизнь\n"
        "• Поддержку Ольги после ретрита\n\n"
        "Для сравнения: 10 сессий у психолога в Москве — от 100 000 ₽, "
        "без моря, без тела, без глубины.\n\n"
        "Майский заезд — стартовая цена: 200 000 ₽."
    ),
    'after': (
        "🌱 *После ретрита*\n\n"
        "Ретрит — не точка, а переход.\n\n"
        "• Первые 2–3 недели: психика и тело продолжают перестраиваться — это нормально\n"
        "• Ольга остаётся на связи при острой необходимости\n"
        "• Участницы получают приоритетный доступ к индивидуальной работе с Ольгой\n"
        "• Группа остаётся в контакте — поддержка продолжается\n\n"
        "Многие приезжают снова — уже с другим запросом."
    ),
    'about': (
        "🖤 *Чёрный Ретрит · Болгария · 2026*\n\n"
        "10 дней настоящей работы с телом и психикой на берегу Чёрного моря.\n\n"
        "Ведущая: Ph.Dr. Ольга Турьева\n"
        "Кризисный психолог · физиотерапевт · 34 года практики\n"
        "Данибузский университет, Словакия\n\n"
        "Для кого: женщины в выгорании, кризисе, потере себя.\n"
        "Тех, кому отдых уже не помогает — нужна другая работа.\n\n"
        "Это не медитация. Не йога. Не спа.\n"
        "Это встреча с собой — глубокая, настоящая."
    ),
}

MENU_MAP = {'1': 'dates', '2': 'format', '3': 'safety', '4': 'location',
            '5': 'food', '6': 'friend', '7': 'expensive', '8': 'after'}

FAQ_MAP = {
    'цен': 'dates', 'стоимост': 'dates', 'дорого': 'expensive',
    'сколько стоит': 'dates', 'почем': 'dates', 'прайс': 'dates',
    'дат': 'dates', 'когда': 'dates', 'месяц': 'dates',
    'май': 'dates', 'июн': 'dates', 'июл': 'dates',
    'август': 'dates', 'сентябр': 'dates', 'октябр': 'dates',
    'формат': 'format', 'програм': 'format', 'глаза': 'format',
    'повязк': 'format', 'маска': 'format', '10 дней': 'format',
    'телефон': 'format', 'интернет': 'format', 'вайфай': 'format',
    'безопас': 'safety', 'страшно': 'safety', 'страх': 'safety',
    'противопоказан': 'safety', 'психиатр': 'safety', 'опасно': 'safety',
    'диагноз': 'safety', 'паника': 'safety',
    'оплат': 'dates', 'деньг': 'dates', 'евро': 'dates',
    'перевод': 'dates', 'налич': 'dates', 'предоплат': 'dates',
    'болгар': 'location', 'квартир': 'location', 'апартам': 'location',
    'добрат': 'location', 'перелет': 'location', 'виза': 'location',
    'аэропорт': 'location', 'бургас': 'location', 'море': 'location',
    'святой влас': 'location',
    'еда': 'food', 'питан': 'food', 'повар': 'food', 'завтрак': 'food',
    'аллерг': 'food', 'вегетар': 'food',
    'группа': 'about', 'участниц': 'about', 'сколько человек': 'about',
    'подруг': 'friend', 'вместе': 'friend', 'рефер': 'friend', 'скидк': 'friend',
    'после': 'after', 'поддержк': 'after', 'интеграц': 'after',
    'надо подумать': 'expensive', 'подумать': 'expensive',
    'что такое': 'about', 'расскаж': 'about', 'ретрит': 'about',
    'кто вы': 'about', 'об ольге': 'about', 'ольга': 'about',
}

# ═══════════════════════════════════════════════════════════════════════════════
# ОБРАБОТКА СООБЩЕНИЙ
# ═══════════════════════════════════════════════════════════════════════════════

def process(phone, name, text):
    log_msg(phone, name, text)
    user = get_user(phone)
    tl = text.lower().strip()

    # Новый пользователь
    if user is None:
        upsert_user(phone, name=name, state='menu')
        notify_admin(f"👤 Новый контакт WhatsApp\n{name} · +{phone}")
        send(phone, MENU_TEXT)
        return

    state = user['state'] or 'menu'

    # Сброс в меню
    if tl in ['меню', 'menu', 'старт', 'start', '/start', 'привет',
              'здравствуйте', 'добрый день', 'добрый вечер', 'доброе утро']:
        upsert_user(phone, state='menu')
        send(phone, MENU_TEXT)
        return

    # Числовое меню
    if tl in MENU_MAP:
        send(phone, INFO[MENU_MAP[tl]])
        send(phone, "Для меню напишите *меню*")
        return

    # Запись на собеседование
    if tl == '9':
        upsert_user(phone, state='qualify_situation')
        send(phone,
            "Чтобы Ольга подготовилась к разговору — один короткий вопрос:\n\n"
            "Что привело вас сюда?\n\n"
            "1 — Выгорание / пустота / нет сил\n"
            "2 — Кризис / развод / потеря\n"
            "3 — Потеряла себя в ролях\n"
            "4 — Хочу глубоких перемен"
        )
        return

    # Квалификация: ситуация
    if state == 'qualify_situation' and tl in ['1', '2', '3', '4']:
        sits = {'1': 'Выгорание / пустота', '2': 'Кризис / развод / потеря',
                '3': 'Потеряла себя в ролях', '4': 'Хочу глубоких перемен'}
        upsert_user(phone, situation=sits[tl], state='qualify_month')
        notify_admin(f"🔍 Квалификация WhatsApp\n+{phone} · {name}\nСитуация: {sits[tl]}")
        send(phone,
            "Какой месяц вам ближе?\n\n"
            "1 — Май (от 200 000 ₽)\n"
            "2 — Июнь (300 000 ₽)\n"
            "3 — Июль (350 000 ₽)\n"
            "4 — Август (350 000 ₽)\n"
            "5 — Сентябрь (300 000 ₽)\n"
            "6 — Октябрь (200 000 ₽)"
        )
        return

    # Квалификация: месяц
    if state == 'qualify_month' and tl in ['1', '2', '3', '4', '5', '6']:
        months = {'1': 'Май', '2': 'Июнь', '3': 'Июль',
                  '4': 'Август', '5': 'Сентябрь', '6': 'Октябрь'}
        m = months[tl]
        upsert_user(phone, preferred_month=m, state='menu')
        notify_admin(f"✅ Заявка WhatsApp\n+{phone} · {name}\nМесяц: {m}\nСитуация: {user.get('situation','—')}")
        send(phone,
            f"Отлично! Я передала ваш запрос Ольге.\n\n"
            f"Она свяжется с вами по этому номеру для короткого знакомства (15–20 минут).\n\n"
            f"Ольга также доступна напрямую:\n"
            f"📱 WhatsApp: +49 176 7576 5576\n"
            f"✈️ Telegram: @OlgaTurreva\n\n"
            f"До встречи! 🖤"
        )
        return

    # FAQ по ключевым словам
    for kw, key in FAQ_MAP.items():
        if kw in tl:
            notify_admin(f"💬 Вопрос WhatsApp: {name} (+{phone})\n{text}")
            send(phone, INFO[key])
            send(phone, "Для меню напишите *меню*")
            return

    # Неизвестный вопрос
    notify_admin(f"❓ Вопрос без ответа WhatsApp\n{name} (+{phone}):\n{text}")
    send(phone,
        "Спасибо за вопрос — я передала его Ольге, она ответит лично.\n\n"
        "Для меню напишите *меню*"
    )

# ═══════════════════════════════════════════════════════════════════════════════
# ГЛАВНЫЙ ЦИКЛ
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    init_db()
    print(f"WhatsApp-бот запущен. Instance: {INSTANCE_ID}")
    enable_incoming()

    while True:
        try:
            notification = receive_notification()
            if notification:
                receipt_id = notification.get('receiptId')
                body = notification.get('body', {})
                webhook_type = body.get('typeWebhook', 'unknown')
                print(f"[notification] type={webhook_type} receiptId={receipt_id}")

                if webhook_type == 'incomingMessageReceived':
                    sender = body.get('senderData', {})
                    phone  = sender.get('sender', '').replace('@c.us', '')
                    name   = sender.get('senderName', phone)
                    msg    = body.get('messageData', {})
                    msg_type = msg.get('typeMessage', '')
                    print(f"[message] from={phone} name={name} type={msg_type}")

                    if msg_type == 'textMessage':
                        text = msg.get('textMessageData', {}).get('textMessage', '').strip()
                        print(f"[text] {text}")
                        if text and phone and phone != ADMIN_PHONE:
                            process(phone, name, text)

                if receipt_id:
                    delete_notification(receipt_id)
            else:
                time.sleep(2)

        except Exception as e:
            print(f"[main error] {e}")
            time.sleep(5)

if __name__ == '__main__':
    main()
