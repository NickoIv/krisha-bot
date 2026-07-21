"""Telegram бот для поиска квартир на Krisha.kz"""
import asyncio
import logging
from datetime import datetime, timedelta

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

from config import BOT_TOKEN, ADMIN_ID, CHECK_INTERVAL
from database import (
    init_db, get_user_filters, set_user_filters,
    save_listing, was_notified, mark_notified, get_all_users,
    add_to_favorites, get_favorites, remove_from_favorites
)
from parser import parse_listings

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Районы Алматы
DISTRICTS = [
    "Медеу", "Бостандык", "Алмалы", "Ауэзов", "Жетысу",
    "Турксиб", "Наурызбай", "Алатау", "Карасайский", "Любой"
]

# Метро Алматы
METRO_STATIONS = [
    "Райымбек батыра", "Жибек жолы", "Алмалы", "Абай",
    "Байконур", "Театральная", "Любая"
]

# ====== ПОСТОЯННОЕ МЕНЮ ======

def get_main_menu():
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton("🔍 Поиск"), KeyboardButton("⚙️ Фильтры")],
            [KeyboardButton("⭐ Избранное"), KeyboardButton("📊 Статистика")],
            [KeyboardButton("❓ Помощь")]
        ],
        resize_keyboard=True
    )

# ====== СОСТОЯНИЯ ПОЛЬЗОВАТЕЛЯ ======

def get_state(context):
    return context.user_data.get("state", None)

def set_state(context, state):
    context.user_data["state"] = state

def clear_state(context):
    context.user_data.pop("state", None)
    context.user_data.pop("filters", None)

# ====== КОМАНДЫ ======

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    clear_state(context)
    await update.message.reply_text(
        f"🏠 *Привет, {user.first_name}!*\n\n"
        f"Я бот для поиска квартир в *Алматы* на [Krisha.kz](https://krisha.kz).\n"
        f"Буду присылать тебе новые объявления по твоим параметрам.\n\n"
        f"Нажми *'Поиск'* чтобы начать!",
        parse_mode="Markdown",
        reply_markup=get_main_menu()
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    clear_state(context)
    await update.message.reply_text(
        "📋 *Команды бота:*\n\n"
        "🔍 *Поиск* — Найти квартиры сейчас\n"
        "⚙️ *Фильтры* — Настроить фильтры поиска\n"
        "⭐ *Избранное* — Сохранённые объявления\n"
        "📊 *Статистика* — Аналитика рынка\n\n"
        "*Дополнительно:*\n"
        "/filters — Настроить фильтры\n"
        "/search — Поиск\n"
        "/stop — Остановить уведомления",
        parse_mode="Markdown",
        reply_markup=get_main_menu()
    )

# ====== ОБРАБОТКА ТЕКСТОВЫХ КНОПОК ======

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    state = get_state(context)

    # Если пользователь вводит данные для фильтров
    if state == "price_from":
        await handle_price_from(update, context)
        return
    elif state == "price_to":
        await handle_price_to(update, context)
        return
    elif state == "area_from":
        await handle_area_from(update, context)
        return
    elif state == "area_to":
        await handle_area_to(update, context)
        return

    # Главное меню
    if text == "🔍 Поиск" or text == "/search":
        await search_now(update, context)
    elif text == "⚙️ Фильтры" or text == "/filters":
        await set_filters_start(update, context)
    elif text == "⭐ Избранное":
        await show_favorites(update, context)
    elif text == "📊 Статистика":
        await show_stats(update, context)
    elif text == "❓ Помощь" or text == "/help":
        await help_command(update, context)
    else:
        await update.message.reply_text(
            "Используй кнопки меню ниже:",
            reply_markup=get_main_menu()
        )

# ====== НАСТРОЙКА ФИЛЬТРОВ ======

async def set_filters_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    clear_state(context)
    context.user_data["filters"] = {}

    keyboard = [
        [InlineKeyboardButton("1 комната", callback_data="rooms_1"),
         InlineKeyboardButton("2 комнаты", callback_data="rooms_2")],
        [InlineKeyboardButton("3 комнаты", callback_data="rooms_3"),
         InlineKeyboardButton("4+ комнаты", callback_data="rooms_4")],
        [InlineKeyboardButton("Любое", callback_data="rooms_any")],
        [InlineKeyboardButton("❌ Отмена", callback_data="cancel_filter")],
    ]

    await update.message.reply_text(
        "🔍 *Настройка фильтров*\n\n"
        "Шаг 1/8: *Выбери количество комнат:*",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "cancel_filter":
        clear_state(context)
        await query.edit_message_text("❌ Настройка отменена.")
        return

    # Комнаты
    if data.startswith("rooms_"):
        rooms = data.replace("rooms_", "")
        context.user_data["filters"] = {"rooms": None if rooms == "any" else int(rooms)}
        set_state(context, "price_from")
        await query.edit_message_text(
            "🔍 *Настройка фильтров*\n\n"
            "Шаг 2/8: *Введи минимальную цену* (в тенге) или отправь 0:\n\n"
            "_Пример: 150000_",
            parse_mode="Markdown"
        )
        return

    # Район
    if data.startswith("district_"):
        district = data.replace("district_", "")
        if district == "skip":
            context.user_data["filters"]["district"] = None
        else:
            context.user_data["filters"]["district"] = district

        keyboard = []
        row = []
        for i, metro in enumerate(METRO_STATIONS):
            row.append(InlineKeyboardButton(metro, callback_data=f"metro_{metro}"))
            if (i + 1) % 3 == 0 or i == len(METRO_STATIONS) - 1:
                keyboard.append(row)
                row = []
        keyboard.append([InlineKeyboardButton("❌ Пропустить", callback_data="metro_skip")])

        await query.edit_message_text(
            "🔍 *Настройка фильтров*\n\n"
            "Шаг 7/8: *Выбери станцию метро:*",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
        return

    # Метро
    if data.startswith("metro_"):
        metro = data.replace("metro_", "")
        if metro == "skip":
            context.user_data["filters"]["metro"] = None
        else:
            context.user_data["filters"]["metro"] = metro

        keyboard = [
            [InlineKeyboardButton("За всё время", callback_data="date_any")],
            [InlineKeyboardButton("За сегодня", callback_data="date_today")],
            [InlineKeyboardButton("За неделю", callback_data="date_week")],
            [InlineKeyboardButton("За месяц", callback_data="date_month")],
        ]

        await query.edit_message_text(
            "🔍 *Настройка фильтров*\n\n"
            "Шаг 8/8: *Выбери период публикации:*",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
        return

    # Дата
    if data.startswith("date_"):
        date_filter = data.replace("date_", "")
        context.user_data["filters"]["date_filter"] = date_filter
        await show_filter_summary(update, context)
        return

    # Сохранение
    if data == "save_filters":
        user_id = update.effective_user.id
        filters_data = context.user_data.get("filters", {})
        clean_filters = {k: v for k, v in filters_data.items() if v is not None}
        set_user_filters(user_id, clean_filters)
        clear_state(context)

        await query.edit_message_text(
            "✅ *Фильтры сохранены!*\n\n"
            "Буду присылать тебе новые объявления.\n"
            "Проверка каждые 5 минут.\n\n"
            "Используй 🔍 *Поиск* для немедленного поиска.",
            parse_mode="Markdown"
        )

        # Запускаем фоновую задачу
        context.job_queue.run_repeating(
            check_new_listings,
            interval=CHECK_INTERVAL,
            first=10,
            data={"user_id": user_id},
            name=f"check_{user_id}"
        )
        return

    if data == "restart_filters":
        await set_filters_start(update, context)
        return

    # Избранное
    if data.startswith("fav_"):
        await add_favorite(update, context)
        return

    # Поиск из inline
    if data == "search_now":
        await search_now_inline(update, context)
        return


async def handle_price_from(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        price = int(update.message.text.strip())
        context.user_data["filters"]["price_from"] = price if price > 0 else None
        set_state(context, "price_to")
        await update.message.reply_text(
            "🔍 *Настройка фильтров*\n\n"
            "Шаг 3/8: *Введи максимальную цену* (в тенге) или отправь 0:\n\n"
            "_Пример: 300000_",
            parse_mode="Markdown"
        )
    except ValueError:
        await update.message.reply_text("❌ Введи число. Попробуй ещё раз:")


async def handle_price_to(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        price = int(update.message.text.strip())
        context.user_data["filters"]["price_to"] = price if price > 0 else None
        set_state(context, "area_from")
        await update.message.reply_text(
            "🔍 *Настройка фильтров*\n\n"
            "Шаг 4/8: *Введи минимальную площадь* (м²) или отправь 0:\n\n"
            "_Пример: 35_",
            parse_mode="Markdown"
        )
    except ValueError:
        await update.message.reply_text("❌ Введи число. Попробуй ещё раз:")


async def handle_area_from(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        area = int(update.message.text.strip())
        context.user_data["filters"]["area_from"] = area if area > 0 else None
        set_state(context, "area_to")
        await update.message.reply_text(
            "🔍 *Настройка фильтров*\n\n"
            "Шаг 5/8: *Введи максимальную площадь* (м²) или отправь 0:\n\n"
            "_Пример: 60_",
            parse_mode="Markdown"
        )
    except ValueError:
        await update.message.reply_text("❌ Введи число. Попробуй ещё раз:")


async def handle_area_to(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        area = int(update.message.text.strip())
        context.user_data["filters"]["area_to"] = area if area > 0 else None
        clear_state(context)

        # Выбор района
        keyboard = []
        row = []
        for i, district in enumerate(DISTRICTS):
            row.append(InlineKeyboardButton(district, callback_data=f"district_{district}"))
            if (i + 1) % 3 == 0 or i == len(DISTRICTS) - 1:
                keyboard.append(row)
                row = []
        keyboard.append([InlineKeyboardButton("❌ Пропустить", callback_data="district_skip")])

        await update.message.reply_text(
            "🔍 *Настройка фильтров*\n\n"
            "Шаг 6/8: *Выбери район:*",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
    except ValueError:
        await update.message.reply_text("❌ Введи число. Попробуй ещё раз:")


async def show_filter_summary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    filters_data = context.user_data.get("filters", {})

    text = "📋 *Твои фильтры:*\n\n"
    text += f"🛏 Комнат: {filters_data.get('rooms') or 'Любое'}\n"
    text += f"💰 Цена: {filters_data.get('price_from') or '0'} — {filters_data.get('price_to') or '∞'} тенге\n"
    text += f"📐 Площадь: {filters_data.get('area_from') or '0'} — {filters_data.get('area_to') or '∞'} м²\n"
    text += f"🗺 Район: {filters_data.get('district') or 'Любой'}\n"
    text += f"🚇 Метро: {filters_data.get('metro') or 'Любая'}\n"
    text += f"📅 Период: {filters_data.get('date_filter') or 'За всё время'}\n\n"
    text += "Сохранить фильтры?"

    keyboard = [
        [InlineKeyboardButton("✅ Сохранить", callback_data="save_filters")],
        [InlineKeyboardButton("🔄 Начать заново", callback_data="restart_filters")],
        [InlineKeyboardButton("❌ Отмена", callback_data="cancel_filter")],
    ]

    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )


async def show_filters(update: Update, context: ContextTypes.DEFAULT_TYPE):
    clear_state(context)
    user_id = update.effective_user.id
    filters_data = get_user_filters(user_id)

    if not filters_data:
        text = "📋 *У тебя пока нет фильтров.*\n\n"
        text += "Нажми ⚙️ *Фильтры* чтобы начать."
    else:
        text = "📋 *Твои текущие фильтры:*\n\n"
        text += f"🛏 Комнат: {filters_data.get('rooms') or 'Любое'}\n"
        text += f"💰 Цена: {filters_data.get('price_from') or '0'} — {filters_data.get('price_to') or '∞'} тенге\n"
        text += f"📐 Площадь: {filters_data.get('area_from') or '0'} — {filters_data.get('area_to') or '∞'} м²\n"
        text += f"🗺 Район: {filters_data.get('district') or 'Любой'}\n"
        text += f"🚇 Метро: {filters_data.get('metro') or 'Любая'}\n"
        text += f"📅 Период: {filters_data.get('date_filter') or 'За всё время'}"

    keyboard = [
        [InlineKeyboardButton("🔧 Изменить", callback_data="restart_filters")],
        [InlineKeyboardButton("🔍 Поиск", callback_data="search_now")],
    ]

    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")


# ====== ПОИСК ======

async def search_now(update: Update, context: ContextTypes.DEFAULT_TYPE):
    clear_state(context)
    user_id = update.effective_user.id
    filters_data = get_user_filters(user_id)

    if not filters_data:
        await update.message.reply_text(
            "❌ *Сначала настрой фильтры!*\n\n"
            "Нажми ⚙️ *Фильтры* чтобы настроить поиск.",
            parse_mode="Markdown",
            reply_markup=get_main_menu()
        )
        return

    await update.message.reply_text("🔍 *Ищу квартиры...*", parse_mode="Markdown")

    listings = parse_listings(filters_data)

    if not listings:
        await update.message.reply_text(
            "😔 *По твоим фильтрам ничего не найдено.*\n\n"
            "Попробуй расширить параметры в ⚙️ *Фильтры*.",
            parse_mode="Markdown",
            reply_markup=get_main_menu()
        )
        return

    # Фильтр по дате
    date_filter = filters_data.get("date_filter")
    if date_filter and date_filter != "any":
        now = datetime.now()
        if date_filter == "today":
            cutoff = now - timedelta(days=1)
        elif date_filter == "week":
            cutoff = now - timedelta(days=7)
        elif date_filter == "month":
            cutoff = now - timedelta(days=30)
        else:
            cutoff = None

        if cutoff:
            filtered = []
            for l in listings:
                try:
                    if datetime.fromisoformat(l.get("published_at", "")) > cutoff:
                        filtered.append(l)
                except:
                    filtered.append(l)
            listings = filtered

    # Фильтр по району
    district = filters_data.get("district")
    if district and district != "Любой":
        listings = [l for l in listings if district.lower() in l.get("address", "").lower()]

    if not listings:
        await update.message.reply_text(
            "😔 *Ничего не найдено за выбранный период.*\n\n"
            "Попробуй увеличить период в ⚙️ *Фильтры*.",
            parse_mode="Markdown",
            reply_markup=get_main_menu()
        )
        return

    for i, listing in enumerate(listings[:5]):
        text = format_listing(listing, i+1)
        keyboard = [
            [InlineKeyboardButton("🔗 Открыть на Krisha", url=listing["url"])],
            [InlineKeyboardButton("⭐ В избранное", callback_data=f"fav_{listing['id']}")]
        ]

        if listing.get("photo_url"):
            await context.bot.send_photo(
                chat_id=update.effective_chat.id,
                photo=listing["photo_url"],
                caption=text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="Markdown"
            )
        else:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="Markdown"
            )

    if len(listings) > 5:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"📊 *Найдено {len(listings)} объявлений.* Показаны первые 5.",
            parse_mode="Markdown",
            reply_markup=get_main_menu()
        )


async def search_now_inline(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    clear_state(context)

    user_id = update.effective_user.id
    filters_data = get_user_filters(user_id)

    if not filters_data:
        await query.edit_message_text(
            "❌ *Сначала настрой фильтры!*\n\n"
            "Нажми ⚙️ *Фильтры* чтобы настроить поиск.",
            parse_mode="Markdown"
        )
        return

    await query.edit_message_text("🔍 *Ищу квартиры...*", parse_mode="Markdown")

    listings = parse_listings(filters_data)

    if not listings:
        await query.edit_message_text(
            "😔 *По твоим фильтрам ничего не найдено.*",
            parse_mode="Markdown"
        )
        return

    for i, listing in enumerate(listings[:5]):
        text = format_listing(listing, i+1)
        keyboard = [
            [InlineKeyboardButton("🔗 Открыть на Krisha", url=listing["url"])],
            [InlineKeyboardButton("⭐ В избранное", callback_data=f"fav_{listing['id']}")]
        ]

        if listing.get("photo_url"):
            await context.bot.send_photo(
                chat_id=update.effective_chat.id,
                photo=listing["photo_url"],
                caption=text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="Markdown"
            )
        else:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="Markdown"
            )


def format_listing(listing: dict, num: int = None) -> str:
    price_formatted = f"{listing['price']:,}".replace(",", " ")
    text = ""
    if num:
        text += f"#{num} "
    text += f"🏠 *{listing['title']}*\n\n"
    text += f"💰 *Цена:* {price_formatted} ₸/мес\n"
    text += f"🛏 *Комнат:* {listing['rooms']}\n"
    text += f"📐 *Площадь:* {listing['area']} м²\n"
    text += f"🏢 *Этаж:* {listing['floor']}\n"
    text += f"📍 *Адрес:* {listing['address']}\n"

    if listing.get("district"):
        text += f"🗺 *Район:* {listing['district']}\n"

    if listing.get("published_at"):
        try:
            dt = datetime.fromisoformat(listing["published_at"])
            text += f"📅 *Дата:* {dt.strftime('%d.%m.%Y %H:%M')}\n"
        except:
            pass

    if listing.get("description"):
        desc = listing["description"][:150] + "..." if len(listing["description"]) > 150 else listing["description"]
        text += f"\n📝 *Описание:*\n{desc}"

    return text


# ====== ИЗБРАННОЕ ======

async def show_favorites(update: Update, context: ContextTypes.DEFAULT_TYPE):
    clear_state(context)
    user_id = update.effective_user.id
    favorites = get_favorites(user_id)

    if not favorites:
        await update.message.reply_text(
            "⭐ *Избранное*\n\n"
            "У тебя пока нет сохранённых объявлений.\n"
            "Нажми ⭐ *В избранное* на понравившемся объявлении.",
            parse_mode="Markdown",
            reply_markup=get_main_menu()
        )
        return

    text = f"⭐ *Избранное ({len(favorites)})*\n\n"
    for i, fav in enumerate(favorites[:10]):
        listing_id, title, price, url, added_at = fav
        price_fmt = f"{price:,}".replace(",", " ")
        text += f"{i+1}. *{title}*\n"
        text += f"   💰 {price_fmt} ₸\n"
        text += f"   [🔗 Открыть]({url})\n\n"

    await update.message.reply_text(
        text,
        parse_mode="Markdown",
        reply_markup=get_main_menu(),
        disable_web_page_preview=True
    )


async def add_favorite(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("Добавлено в избранное!")

    data = query.data
    if data.startswith("fav_"):
        listing_id = data.replace("fav_", "")
        # Получаем данные из сообщения
        message = query.message
        if message.photo:
            caption = message.caption
        else:
            caption = message.text

        # Создаём минимальные данные для избранного
        listing = {
            "id": listing_id,
            "title": caption.split('\n')[0].replace('#', '').strip() if caption else "Без названия",
            "price": 0,
            "url": ""
        }

        # Извлекаем URL из кнопки
        if message.reply_markup and message.reply_markup.inline_keyboard:
            for row in message.reply_markup.inline_keyboard:
                for btn in row:
                    if btn.url:
                        listing["url"] = btn.url
                        break

        # Извлекаем цену из текста
        if caption and "Цена:" in caption:
            try:
                price_str = caption.split("Цена:")[1].split("₸")[0].strip().replace(" ", "")
                listing["price"] = int(price_str)
            except:
                pass

        user_id = update.effective_user.id
        add_to_favorites(user_id, listing)

        # Обновляем кнопку
        new_keyboard = []
        if message.reply_markup and message.reply_markup.inline_keyboard:
            for row in message.reply_markup.inline_keyboard:
                new_row = []
                for btn in row:
                    if btn.callback_data and btn.callback_data.startswith("fav_"):
                        new_row.append(InlineKeyboardButton("✅ В избранном", callback_data="done"))
                    else:
                        new_row.append(btn)
                new_keyboard.append(new_row)

        try:
            if message.photo:
                await query.edit_message_caption(
                    caption=caption,
                    reply_markup=InlineKeyboardMarkup(new_keyboard),
                    parse_mode="Markdown"
                )
            else:
                await query.edit_message_reply_markup(
                    reply_markup=InlineKeyboardMarkup(new_keyboard)
                )
        except Exception as e:
            logger.error(f"Ошибка обновления кнопки: {e}")


# ====== СТАТИСТИКА ======

async def show_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    clear_state(context)
    user_id = update.effective_user.id
    filters_data = get_user_filters(user_id)

    if not filters_data:
        await update.message.reply_text(
            "📊 *Статистика*\n\n"
            "Сначала настрой фильтры чтобы увидеть статистику.",
            parse_mode="Markdown",
            reply_markup=get_main_menu()
        )
        return

    listings = parse_listings(filters_data)

    if not listings:
        text = "📊 *Статистика*\n\n"
        text += "Нет данных для анализа."
    else:
        prices = [l["price"] for l in listings if l["price"] > 0]
        areas = [l["area"] for l in listings if l["area"] > 0]

        avg_price = sum(prices) / len(prices) if prices else 0
        avg_area = sum(areas) / len(areas) if areas else 0
        price_per_m2 = avg_price / avg_area if avg_area > 0 else 0

        text = "📊 *Статистика рынка*\n\n"
        text += f"📈 *Всего объявлений:* {len(listings)}\n"
        text += f"💰 *Средняя цена:* {avg_price:,.0f} ₸\n".replace(",", " ")
        text += f"📐 *Средняя площадь:* {avg_area:.1f} м²\n"
        text += f"📊 *Цена за м²:* {price_per_m2:,.0f} ₸\n".replace(",", " ")
        text += f"🏠 *Комнат:* {filters_data.get('rooms') or 'Любое'}\n"
        text += f"🗺 *Район:* {filters_data.get('district') or 'Любой'}\n\n"
        text += "_Данные актуальны на момент запроса_"

    await update.message.reply_text(
        text,
        parse_mode="Markdown",
        reply_markup=get_main_menu()
    )


# ====== ФОНОВАЯ ПРОВЕРКА ======

async def check_new_listings(context: ContextTypes.DEFAULT_TYPE):
    job_data = context.job.data
    user_id = job_data.get("user_id")
    if not user_id:
        return
    filters_data = get_user_filters(user_id)
    if not filters_data:
        return
    try:
        listings = parse_listings(filters_data)
        new_listings = []
        for listing in listings:
            is_new = save_listing(listing)
            if is_new and not was_notified(user_id, listing["id"]):
                new_listings.append(listing)
                mark_notified(user_id, listing["id"])
        for listing in new_listings[:3]:
            text = "🆕 *Новое объявление!*\n\n" + format_listing(listing)
            keyboard = [
                [InlineKeyboardButton("🔗 Открыть на Krisha", url=listing["url"])],
                [InlineKeyboardButton("⭐ В избранное", callback_data=f"fav_{listing['id']}")]
            ]
            try:
                if listing.get("photo_url"):
                    await context.bot.send_photo(
                        chat_id=user_id,
                        photo=listing["photo_url"],
                        caption=text,
                        reply_markup=InlineKeyboardMarkup(keyboard),
                        parse_mode="Markdown"
                    )
                else:
                    await context.bot.send_message(
                        chat_id=user_id,
                        text=text,
                        reply_markup=InlineKeyboardMarkup(keyboard),
                        parse_mode="Markdown"
                    )
            except Exception as e:
                logger.error(f"Ошибка отправки: {e}")
    except Exception as e:
        logger.error(f"Ошибка проверки: {e}")


# ====== ОСТАНОВКА ======

async def stop_notifications(update: Update, context: ContextTypes.DEFAULT_TYPE):
    clear_state(context)
    user_id = update.effective_user.id
    jobs = context.job_queue.get_jobs_by_name(f"check_{user_id}")
    for job in jobs:
        job.schedule_removal()
    set_user_filters(user_id, {})
    await update.message.reply_text(
        "❌ *Уведомления остановлены.*\n\n"
        "Фильтры удалены. Чтобы возобновить, настрой фильтры заново.",
        parse_mode="Markdown",
        reply_markup=get_main_menu()
    )


# ====== ЗАПУСК ======

def main():
    init_db()
    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("search", search_now))
    application.add_handler(CommandHandler("myfilters", show_filters))
    application.add_handler(CommandHandler("stop", stop_notifications))

    # Все callback'и через один обработчик
    application.add_handler(CallbackQueryHandler(handle_callback))

    # Текстовые сообщения (включая ввод данных для фильтров)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    async def restore_jobs(app):
        users = get_all_users()
        for user_id, filters_json in users:
            if filters_json and filters_json != "{}":
                app.job_queue.run_repeating(
                    check_new_listings,
                    interval=CHECK_INTERVAL,
                    first=30,
                    data={"user_id": user_id},
                    name=f"check_{user_id}"
                )
                logger.info(f"Восстановлена задача для {user_id}")

    application.job_queue.run_once(lambda ctx: asyncio.create_task(restore_jobs(application)), when=1)
    logger.info("Бот запущен!")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
