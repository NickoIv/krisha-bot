"""Telegram бот для поиска квартир на Krisha.kz - v2"""
import asyncio
import logging
from datetime import datetime, timedelta

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ConversationHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

from config import BOT_TOKEN, ADMIN_ID, CHECK_INTERVAL
from database import (
    init_db, get_user_filters, set_user_filters,
    save_listing, was_notified, mark_notified, get_all_users
)
from parser import parse_listings

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Районы Алматы
DISTRICTS = [
    "Medeu", "Bostandyk", "Almaly", "Auezov", "Zhetysu", 
    "Turksib", "Nauryzbay", "Alatau", "Karasaisky", "Any"
]

# Метро Алматы
METRO_STATIONS = [
    "Raiymbek batyr", "Zhibek zholy", "Almaly", "Abay", 
    "Baikonur", "Teatralnaya", "Any metro"
]

SET_ROOMS, SET_PRICE_FROM, SET_PRICE_TO, SET_AREA_FROM, SET_AREA_TO, SET_DISTRICT, SET_METRO, SET_DATE, CONFIRM = range(9)

# ====== ПОСТОЯННОЕ МЕНЮ ======

def get_main_menu():
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton("🔍 Poisk"), KeyboardButton("⚙️ Filtry")],
            [KeyboardButton("⭐ Izbrannoe"), KeyboardButton("📊 Statistika")],
            [KeyboardButton("❓ Pomoshch")]
        ],
        resize_keyboard=True
    )

# ====== КОМАНДЫ ======

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await update.message.reply_text(
        f"🏠 *Privet, {user.first_name}!*\n\n"
        f"Ja bot dlja poiska kvartir v *Almaty* na Krisha.kz.\n"
        f"Budu prisylat tebe novye objavlenija po tvoyim parametram.\n\n"
        f"Nazhmi *'Poisk'* chtoby nachat!",
        parse_mode="Markdown",
        reply_markup=get_main_menu()
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📋 *Komandy bota:*\n\n"
        "🔍 *Poisk* — Najti kvartiry sejchas\n"
        "⚙️ *Filtry* — Nastroit filtry poiska\n"
        "⭐ *Izbrannoe* — Sohranennye objavlenija\n"
        "📊 *Statistika* — Analitika rynka\n\n"
        "*Dopolnitelno:*\n"
        "/filters — Nastroit filtry\n"
        "/search — Poisk\n"
        "/stop — Ostanovit uvedomlenija",
        parse_mode="Markdown",
        reply_markup=get_main_menu()
    )

# ====== ОБРАБОТКА ТЕКСТОВЫХ КНОПОК ======

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text

    if text == "🔍 Poisk" or text == "/search":
        await search_now(update, context)
    elif text == "⚙️ Filtry" or text == "/filters":
        await set_filters_start(update, context)
    elif text == "⭐ Izbrannoe":
        await show_favorites(update, context)
    elif text == "📊 Statistika":
        await show_stats(update, context)
    elif text == "❓ Pomoshch" or text == "/help":
        await help_command(update, context)
    else:
        await update.message.reply_text(
            "Ispolzuj knopki menju nizhu:",
            reply_markup=get_main_menu()
        )

# ====== НАСТРОЙКА ФИЛЬТРОВ ======

async def set_filters_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
        message = query.edit_message_text
    else:
        message = update.message.reply_text

    keyboard = [
        [InlineKeyboardButton("1 komnata", callback_data="rooms_1"),
         InlineKeyboardButton("2 komnaty", callback_data="rooms_2")],
        [InlineKeyboardButton("3 komnaty", callback_data="rooms_3"),
         InlineKeyboardButton("4+ komnaty", callback_data="rooms_4")],
        [InlineKeyboardButton("Ljuboje", callback_data="rooms_any")],
        [InlineKeyboardButton("❌ Otmena", callback_data="cancel")],
    ]

    await message(
        "🔍 *Nastrojka filtroj*\n\n"
        "Shag 1/8: *Vyberi kolichestvo komnat:*",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )
    return SET_ROOMS


async def set_rooms(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    if data == "cancel":
        await query.edit_message_text("❌ Nastrojka otmenena.")
        return ConversationHandler.END
    rooms = data.replace("rooms_", "")
    context.user_data["filters"] = {"rooms": None if rooms == "any" else int(rooms)}
    await query.edit_message_text(
        "🔍 *Nastrojka filtroj*\n\n"
        "Shag 2/8: *Vvedi minimalnuju cenu* (v tenge) ili otprav 0:\n\n"
        "_Primer: 150000_",
        parse_mode="Markdown"
    )
    return SET_PRICE_FROM


async def set_price_from(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        price = int(update.message.text.strip())
        context.user_data["filters"]["price_from"] = price if price > 0 else None
        await update.message.reply_text(
            "🔍 *Nastrojka filtroj*\n\n"
            "Shag 3/8: *Vvedi maksimalnuju cenu* (v tenge) ili otprav 0:\n\n"
            "_Primer: 300000_",
            parse_mode="Markdown"
        )
        return SET_PRICE_TO
    except ValueError:
        await update.message.reply_text("❌ Vvedi chislo. Poprobuj eshche raz:")
        return SET_PRICE_FROM


async def set_price_to(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        price = int(update.message.text.strip())
        context.user_data["filters"]["price_to"] = price if price > 0 else None
        await update.message.reply_text(
            "🔍 *Nastrojka filtroj*\n\n"
            "Shag 4/8: *Vvedi minimalnuju ploshchad* (m²) ili otprav 0:\n\n"
            "_Primer: 35_",
            parse_mode="Markdown"
        )
        return SET_AREA_FROM
    except ValueError:
        await update.message.reply_text("❌ Vvedi chislo. Poprobuj eshche raz:")
        return SET_PRICE_TO


async def set_area_from(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        area = int(update.message.text.strip())
        context.user_data["filters"]["area_from"] = area if area > 0 else None
        await update.message.reply_text(
            "🔍 *Nastrojka filtroj*\n\n"
            "Shag 5/8: *Vvedi maksimalnuju ploshchad* (m²) ili otprav 0:\n\n"
            "_Primer: 60_",
            parse_mode="Markdown"
        )
        return SET_AREA_TO
    except ValueError:
        await update.message.reply_text("❌ Vvedi chislo. Poprobuj eshche raz:")
        return SET_AREA_FROM


async def set_area_to(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        area = int(update.message.text.strip())
        context.user_data["filters"]["area_to"] = area if area > 0 else None

        # Выбор района
        keyboard = []
        row = []
        for i, district in enumerate(DISTRICTS):
            row.append(InlineKeyboardButton(district, callback_data=f"district_{district}"))
            if (i + 1) % 3 == 0 or i == len(DISTRICTS) - 1:
                keyboard.append(row)
                row = []
        keyboard.append([InlineKeyboardButton("❌ Propustit", callback_data="district_skip")])

        await update.message.reply_text(
            "🔍 *Nastrojka filtroj*\n\n"
            "Shag 6/8: *Vyberi rajon:*",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
        return SET_DISTRICT
    except ValueError:
        await update.message.reply_text("❌ Vvedi chislo. Poprobuj eshche raz:")
        return SET_AREA_TO


async def set_district(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    if data == "district_skip":
        context.user_data["filters"]["district"] = None
    else:
        context.user_data["filters"]["district"] = data.replace("district_", "")

    keyboard = []
    row = []
    for i, metro in enumerate(METRO_STATIONS):
        row.append(InlineKeyboardButton(metro, callback_data=f"metro_{metro}"))
        if (i + 1) % 3 == 0 or i == len(METRO_STATIONS) - 1:
            keyboard.append(row)
            row = []
    keyboard.append([InlineKeyboardButton("❌ Propustit", callback_data="metro_skip")])

    await query.edit_message_text(
        "🔍 *Nastrojka filtroj*\n\n"
        "Shag 7/8: *Vyberi stanciju metro:*",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )
    return SET_METRO


async def set_metro(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    if data == "metro_skip":
        context.user_data["filters"]["metro"] = None
    else:
        context.user_data["filters"]["metro"] = data.replace("metro_", "")

    keyboard = [
        [InlineKeyboardButton("Za vse vremja", callback_data="date_any")],
        [InlineKeyboardButton("Za segodnja", callback_data="date_today")],
        [InlineKeyboardButton("Za nedelju", callback_data="date_week")],
        [InlineKeyboardButton("Za mesjac", callback_data="date_month")],
    ]

    await query.edit_message_text(
        "🔍 *Nastrojka filtroj*\n\n"
        "Shag 8/8: *Vyberi period publikacii:*",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )
    return SET_DATE


async def set_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    date_filter = data.replace("date_", "")
    context.user_data["filters"]["date_filter"] = date_filter

    filters_data = context.user_data["filters"]
    text = "📋 *Tvoi filtry:*\n\n"
    text += f"🛏 Komnat: {filters_data.get('rooms') or 'Ljuboje'}\n"
    text += f"💰 Cena: {filters_data.get('price_from') or '0'} — {filters_data.get('price_to') or '∞'} tenge\n"
    text += f"📐 Ploshchad: {filters_data.get('area_from') or '0'} — {filters_data.get('area_to') or '∞'} m²\n"
    text += f"🗺 Rajon: {filters_data.get('district') or 'Ljuboj'}\n"
    text += f"🚇 Metro: {filters_data.get('metro') or 'Ljubaja'}\n"
    text += f"📅 Period: {filters_data.get('date_filter') or 'Za vse vremja'}\n\n"
    text += "Sohranit filtry?"

    keyboard = [
        [InlineKeyboardButton("✅ Sohranit", callback_data="save_filters")],
        [InlineKeyboardButton("🔄 Nachat zanovo", callback_data="set_filters")],
        [InlineKeyboardButton("❌ Otmena", callback_data="cancel")],
    ]

    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )
    return CONFIRM


async def confirm_filters(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "save_filters":
        user_id = update.effective_user.id
        filters_data = context.user_data.get("filters", {})
        clean_filters = {k: v for k, v in filters_data.items() if v is not None}
        set_user_filters(user_id, clean_filters)
        await query.edit_message_text(
            "✅ *Filtry sohraneny!*\n\n"
            "Budu prisylat tebe novye objavlenija.\n"
            "Proverka kazhdye 5 minut.\n\n"
            "Ispolzuj 🔍 *Poisk* dlja nemedlennogo poiska.",
            parse_mode="Markdown"
        )
        context.job_queue.run_repeating(
            check_new_listings,
            interval=CHECK_INTERVAL,
            first=10,
            data={"user_id": user_id},
            name=f"check_{user_id}"
        )
    elif query.data == "set_filters":
        return await set_filters_start(update, context)
    else:
        await query.edit_message_text("❌ Nastrojka otmenena.")
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Nastrojka otmenena.", reply_markup=get_main_menu())
    return ConversationHandler.END


async def show_filters(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
    user_id = update.effective_user.id
    filters_data = get_user_filters(user_id)
    if not filters_data:
        text = "📋 *U tebja poka net filtroj.*\n\n"
        text += "Nazhmi ⚙️ *Filtry* chtoby nastroit."
    else:
        text = "📋 *Tvoi filtry:*\n\n"
        text += f"🛏 Komnat: {filters_data.get('rooms') or 'Ljuboje'}\n"
        text += f"💰 Cena: {filters_data.get('price_from') or '0'} — {filters_data.get('price_to') or '∞'} tenge\n"
        text += f"📐 Ploshchad: {filters_data.get('area_from') or '0'} — {filters_data.get('area_to') or '∞'} m²\n"
        text += f"🗺 Rajon: {filters_data.get('district') or 'Ljuboj'}\n"
        text += f"🚇 Metro: {filters_data.get('metro') or 'Ljubaja'}\n"
        text += f"📅 Period: {filters_data.get('date_filter') or 'Za vse vremja'}"

    keyboard = [
        [InlineKeyboardButton("🔧 Izmenit", callback_data="set_filters")],
        [InlineKeyboardButton("🔍 Poisk", callback_data="search_now")],
    ]

    if query:
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    else:
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")


# ====== ПОИСК ======

async def search_now(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
        message = query.edit_message_text
    else:
        message = update.message.reply_text

    user_id = update.effective_user.id
    filters_data = get_user_filters(user_id)

    if not filters_data:
        await message(
            "❌ *Snachala nastoj filtry!*\n\n"
            "Nazhmi ⚙️ *Filtry* chtoby nastroit poisk.",
            parse_mode="Markdown",
            reply_markup=get_main_menu()
        )
        return

    await message("🔍 *Ishyu kvartiry...*", parse_mode="Markdown")

    listings = parse_listings(filters_data)

    if not listings:
        await message(
            "😔 *Po tvoyim filtram nichego ne najdeno.*\n\n"
            "Poprobuj rashirit parametry v ⚙️ *Filtry*.",
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
            listings = [l for l in listings if datetime.fromisoformat(l.get("published_at", "")) > cutoff]

    # Фильтр по району (если указан)
    district = filters_data.get("district")
    if district and district != "Any":
        listings = [l for l in listings if district.lower() in l.get("address", "").lower()]

    if not listings:
        await message(
            "😔 *Nichego ne najdeno za vybrannyj period.*\n\n"
            "Poprobuj uvelichit period v ⚙️ *Filtry*.",
            parse_mode="Markdown",
            reply_markup=get_main_menu()
        )
        return

    for i, listing in enumerate(listings[:5]):
        text = format_listing(listing, i+1)
        keyboard = [
            [InlineKeyboardButton("🔗 Otkryt na Krisha", url=listing["url"])],
            [InlineKeyboardButton("⭐ V izbrannoe", callback_data=f"fav_{listing['id']}")]
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
            text=f"📊 *Najdeno {len(listings)} objavlenij.* Pokazany pervye 5.",
            parse_mode="Markdown",
            reply_markup=get_main_menu()
        )


def format_listing(listing: dict, num: int = None) -> str:
    price_formatted = f"{listing['price']:,}".replace(",", " ")
    text = ""
    if num:
        text += f"#{num} "
    text += f"🏠 *{listing['title']}*\n\n"
    text += f"💰 *Cena:* {price_formatted} ₸/mes\n"
    text += f"🛏 *Komnat:* {listing['rooms']}\n"
    text += f"📐 *Ploshchad:* {listing['area']} m²\n"
    text += f"🏢 *Etazh:* {listing['floor']}\n"
    text += f"📍 *Adres:* {listing['address']}\n"

    if listing.get("district"):
        text += f"🗺 *Rajon:* {listing['district']}\n"

    if listing.get("published_at"):
        try:
            dt = datetime.fromisoformat(listing["published_at"])
            text += f"📅 *Data:* {dt.strftime('%d.%m.%Y %H:%M')}\n"
        except:
            pass

    if listing.get("description"):
        desc = listing["description"][:150] + "..." if len(listing["description"]) > 150 else listing["description"]
        text += f"\n📝 *Opisanie:*\n{desc}"

    return text


# ====== ИЗБРАННОЕ ======

async def show_favorites(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "⭐ *Izbrannoe*\n\n"
        "Funkcija v razrabotke.\n"
        "Skoro mozhno budet sohranjat ponravivshiesja objavlenija.",
        parse_mode="Markdown",
        reply_markup=get_main_menu()
    )


# ====== СТАТИСТИКА ======

async def show_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    filters_data = get_user_filters(user_id)

    if not filters_data:
        await update.message.reply_text(
            "📊 *Statistika*\n\n"
            "Snachala nastoj filtry chtoby uvidet statistiku.",
            parse_mode="Markdown",
            reply_markup=get_main_menu()
        )
        return

    listings = parse_listings(filters_data)

    if not listings:
        text = "📊 *Statistika*\n\n"
        text += "Net dannyh dlja analiza."
    else:
        prices = [l["price"] for l in listings if l["price"] > 0]
        areas = [l["area"] for l in listings if l["area"] > 0]

        avg_price = sum(prices) / len(prices) if prices else 0
        avg_area = sum(areas) / len(areas) if areas else 0
        price_per_m2 = avg_price / avg_area if avg_area > 0 else 0

        text = "📊 *Statistika rynka*\n\n"
        text += f"📈 *Vsego objavlenij:* {len(listings)}\n"
        text += f"💰 *Srednjaja cena:* {avg_price:,.0f} ₸\n".replace(",", " ")
        text += f"📐 *Srednjaja ploshchad:* {avg_area:.1f} m²\n"
        text += f"📊 *Cena za m²:* {price_per_m2:,.0f} ₸\n".replace(",", " ")
        text += f"🏠 *Komnat:* {filters_data.get('rooms') or 'Ljuboje'}\n"
        text += f"🗺 *Rajon:* {filters_data.get('district') or 'Ljuboj'}\n\n"
        text += "_Dannye aktualny na moment zaprosa_"

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
            text = "🆕 *Novoje objavlenie!*\n\n" + format_listing(listing)
            keyboard = [
                [InlineKeyboardButton("🔗 Otkryt na Krisha", url=listing["url"])],
                [InlineKeyboardButton("⭐ V izbrannoe", callback_data=f"fav_{listing['id']}")]
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
                logger.error(f"Oshibka otpravki: {e}")
    except Exception as e:
        logger.error(f"Oshibka proverki: {e}")


# ====== ОСТАНОВКА ======

async def stop_notifications(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
    user_id = update.effective_user.id
    jobs = context.job_queue.get_jobs_by_name(f"check_{user_id}")
    for job in jobs:
        job.schedule_removal()
    set_user_filters(user_id, {})
    text = "❌ *Uvedomlenija ostanovleny.*\n\n"
    text += "Filtry udaleny. Chtoby vozobnovit, nastoj filtry zanovo."
    if query:
        await query.edit_message_text(text, parse_mode="Markdown")
    else:
        await update.message.reply_text(text, parse_mode="Markdown", reply_markup=get_main_menu())


# ====== ЗАПУСК ======

def main():
    init_db()
    application = Application.builder().token(BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(set_filters_start, pattern="^set_filters$"),
            CommandHandler("filters", set_filters_start)
        ],
        states={
            SET_ROOMS: [CallbackQueryHandler(set_rooms, pattern="^rooms_")],
            SET_PRICE_FROM: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_price_from)],
            SET_PRICE_TO: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_price_to)],
            SET_AREA_FROM: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_area_from)],
            SET_AREA_TO: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_area_to)],
            SET_DISTRICT: [CallbackQueryHandler(set_district, pattern="^district_")],
            SET_METRO: [CallbackQueryHandler(set_metro, pattern="^metro_")],
            SET_DATE: [CallbackQueryHandler(set_date, pattern="^date_")],
            CONFIRM: [CallbackQueryHandler(confirm_filters, pattern="^save_filters$|^set_filters$|^cancel$")],
        },
        fallbacks=[
            CallbackQueryHandler(cancel, pattern="^cancel$"),
            CommandHandler("cancel", cancel),
        ],
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("search", search_now))
    application.add_handler(CommandHandler("myfilters", show_filters))
    application.add_handler(CommandHandler("stop", stop_notifications))
    application.add_handler(conv_handler)
    application.add_handler(CallbackQueryHandler(show_filters, pattern="^show_filters$"))
    application.add_handler(CallbackQueryHandler(search_now, pattern="^search_now$"))
    application.add_handler(CallbackQueryHandler(stop_notifications, pattern="^stop$"))
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
                logger.info(f"Vosstanovlena zadacha dlja {user_id}")

    application.job_queue.run_once(lambda ctx: asyncio.create_task(restore_jobs(application)), when=1)
    logger.info("Bot zapushchen!")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
