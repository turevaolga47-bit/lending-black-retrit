# Инструкции для Claude — landing.html (Чёрный Ретрит)

## Файл

`landing.html` — единственный рабочий файл лендинга.  
Всё в одном файле: HTML + CSS + JS. Внешние библиотеки не подключать.

---

## Цвета и дизайн

| Переменная | Значение | Использование |
|-----------|----------|---------------|
| `--dark` | `#0a0a0f` | основной фон |
| `--dark2` | `#0f0f18` | фон секций |
| `--gold` | `#c9a84c` | акцент, кнопки, иконки |
| `--gold-light` | `#e8c96d` | заголовки, выделения |
| `--rose` | `#d4829a` | вторичный акцент |
| `--text-dim` | `#9a9298` | второстепенный текст |

---

## Правила редактирования

- Перед правкой — прочитать нужный фрагмент файла
- Не добавлять комментарии в код
- Не подключать jQuery, Bootstrap и другие библиотеки
- Не создавать отдельные CSS/JS файлы — всё в `landing.html`
- Обращение к пользователю — на «вы» (с маленькой буквы)
- Язык — русский, без канцелярита

---

## Паттерны в коде

### Раскрывающиеся карточки
```js
toggleMore(btn) // для .whom-card, .card, .info-card, .bonus-card, .retreat-block, .review-card
toggleFaq(btn)  // для .faq-item
toggleBento(btn) // для .bento-card
```
CSS: `.open .whom-more { max-height: 700px; opacity: 1; }`

### Появление при скролле
Все новые элементы добавлять в селектор `initReveal()`.  
Класс `.reveal` → при попадании в viewport добавляется `.visible`.

### Модалки
`openPrivacy(event)` — политика конфиденциальности  
`openOffer(event)` — публичная оферта

---

## Структура секций (порядок в файле)

1. Hero
2. Pain (боли аудитории)
3. Marquee (бегущая строка)
4. About (о ведущей)
5. For whom (для кого)
6. About Retreat (что такое ретрит) ← важно: до отзывов
7. Testimonial (видео Лена + история)
8. Reviews (текстовые отзывы)
9. Video Reviews (видео отзывы)
10. Gallery (фото локации)
11. Accommodation (фото квартир)
12. Benefits (выгоды)
13. Details / Bento (формат)
14. Bonuses (бонусы)
15. FAQ
16. Info Cards (стоимость + программа + почему работает)
17. CTA (финальный призыв)

---

## Деплой

```bash
git add landing.html
git commit -m "описание изменений"
git push origin master
```

GitHub Pages: `https://turevaolga47-bit.github.io/lending-black-retrit/landing.html`

---

## Что ещё нужно добавить

- Видео квартир на YouTube → добавить в секцию `#accommodation` (`.apt-video-row`)
- После первого ретрита (май 2026) — добавить отзывы участниц
