"""Telegram бот для поиска квартир на Krisha.kz"""
import asyncio
import logging
from datetime import datetime

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
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

SET_ROOMS, SET_PRICE_FROM, SET_PRICE_TO, SET_AREA_FROM, SET_AREA_TO, CONFIRM = range(6)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    keyboard = [
        [InlineKeyboardButton("Nastroj filtry", callback_data="set_filters")],
        [InlineKeyboardButton("Moi filtry", callback_data="show_filters")],
        [InlineKeyboardButton("Poisk sejchas", callback_data="search_now")],
        [InlineKeyboardButton("Ostanovit uvedomlenija", callback_data="stop")],
    ]
    await update.message.reply_text(
        f"Privet, {user.first_name}!\n\n"
        f"Ja bot dlja poiska kvartir v Almaty na Krisha.kz.\n"
        f"Budu prisylat tebe novye objavlenija po tvoyim parametram.\n\n"
        f"Vyberi dejstvie:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Komandy bota:\n\n"
        "/start - Glavnoe menju\n"
        "/filters - Nastroit filtry poiska\n"
        "/search - Najti kvartiry sejchas\n"
        "/myfilters - Pokazat moi filtry\n"
        "/stop - Ostanovit uvedomlenija\n\n"
        "Bot proverjaet novye objavlenija kazhdye 5 minut."
    )


async def set_filters_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    keyboard = [
        [InlineKeyboardButton("1 komnata", callback_data="rooms_1"),
         InlineKeyboardButton("2 komnaty", callback_data="rooms_2")],
        [InlineKeyboardButton("3 komnaty", callback_data="rooms_3"),
         InlineKeyboardButton("4+ komnaty", callback_data="rooms_4")],
        [InlineKeyboardButton("Ljuboje", callback_data="rooms_any")],
        [InlineKeyboardButton("Otmena", callback_data="cancel")],
    ]
    await query.edit_message_text(
        "Nastrojka filtroj\n\n"
        "Shag 1/5: Vyberi kolichestvo komnat:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return SET_ROOMS


async def set_rooms(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    if data == "cancel":
        await query.edit_message_text("Nastrojka otmenena.")
        return ConversationHandler.END
    rooms = data.replace("rooms_", "")
    context.user_data["filters"] = {"rooms": None if rooms == "any" else int(rooms)}
    await query.edit_message_text(
        "Nastrojka filtroj\n\n"
        "Shag 2/5: Vvedi minimalnuju cenu (v tenge) ili otprav 0:\n\n"
        "Primer: 150000"
    )
    return SET_PRICE_FROM


async def set_price_from(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        price = int(update.message.text.strip())
        context.user_data["filters"]["price_from"] = price if price > 0 else None
        await update.message.reply_text(
            "Nastrojka filtroj\n\n"
            "Shag 3/5: Vvedi maksimalnuju cenu (v tenge) ili otprav 0 dlja bezlimita:\n\n"
            "Primer: 300000"
        )
        return SET_PRICE_TO
    except ValueError:
        await update.message.reply_text("Vvedi chislo. Poprobuj eshche raz:")
        return SET_PRICE_FROM


async def set_price_to(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        price = int(update.message.text.strip())
        context.user_data["filters"]["price_to"] = price if price > 0 else None
        await update.message.reply_text(
            "Nastrojka filtroj\n\n"
            "Shag 4/5: Vvedi minimalnuju ploshchad (m2) ili otprav 0:\n\n"
            "Primer: 35"
        )
        return SET_AREA_FROM
    except ValueError:
        await update.message.reply_text("Vvedi chislo. Poprobuj eshche raz:")
        return SET_PRICE_TO


async def set_area_from(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        area = int(update.message.text.strip())
        context.user_data["filters"]["area_from"] = area if area > 0 else None
        await update.message.reply_text(
            "Nastrojka filtroj\n\n"
            "Shag 5/5: Vvedi maksimalnuju ploshchad (m2) ili otprav 0 dlja bezlimita:\n\n"
            "Primer: 60"
        )
        return SET_AREA_TO
    except ValueError:
        await update.message.reply_text("Vvedi chislo. Poprobuj eshche raz:")
        return SET_AREA_FROM


async def set_area_to(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        area = int(update.message.text.strip())
        context.user_data["filters"]["area_to"] = area if area > 0 else None
        filters_data = context.user_data["filters"]
        text = "Tvoi filtry:\n\n"
        text += f"Komnat: {filters_data.get('rooms') or 'Ljuboje'}\n"
        text += f"Cena: {filters_data.get('price_from') or '0'} - {filters_data.get('price_to') or 'beskonechno'} tenge\n"
        text += f"Ploshchad: {filters_data.get('area_from') or '0'} - {filters_data.get('area_to') or 'beskonechno'} m2\n\n"
        text += "Sohranit filtry?"
        keyboard = [
            [InlineKeyboardButton("Sohranit", callback_data="save_filters")],
            [InlineKeyboardButton("Nachat zanovo", callback_data="set_filters")],
            [InlineKeyboardButton("Otmena", callback_data="cancel")],
        ]
        await update.message.reply_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return CONFIRM
    except ValueError:
        await update.message.reply_text("Vvedi chislo. Poprobuj eshche raz:")
        return SET_AREA_TO


async def confirm_filters(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "save_filters":
        user_id = update.effective_user.id
        filters_data = context.user_data.get("filters", {})
        clean_filters = {k: v for k, v in filters_data.items() if v is not None}
        set_user_filters(user_id, clean_filters)
        await query.edit_message_text(
            "Filtry sohraneny!\n\n"
            "Budu prisylat tebe novye objavlenija po jetim parametram.\n"
            "Proverka proishodit kazhdye 5 minut.\n\n"
            "Ispolzuj /search dlja nemedlennogo poiska."
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
        await query.edit_message_text("Nastrojka otmenena.")
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Nastrojka otmenena.")
    return ConversationHandler.END


async def show_filters(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
    user_id = update.effective_user.id
    filters_data = get_user_filters(user_id)
    if not filters_data:
        text = "U tebja poka net sohranennyh filtroj.\n\n"
        text += "Nazhmi Nastroit filtry chtoby nachat."
    else:
        text = "Tvoi tekushchie filtry:\n\n"
        text += f"Komnat: {filters_data.get('rooms') or 'Ljuboje'}\n"
        text += f"Cena: {filters_data.get('price_from') or '0'} - {filters_data.get('price_to') or 'beskonechno'} tenge\n"
        text += f"Ploshchad: {filters_data.get('area_from') or '0'} - {filters_data.get('area_to') or 'beskonechno'} m2"
    keyboard = [
        [InlineKeyboardButton("Izmenit filtry", callback_data="set_filters")],
        [InlineKeyboardButton("Poisk sejchas", callback_data="search_now")],
        [InlineKeyboardButton("Nazad", callback_data="back_to_start")],
    ]
    if query:
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))


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
        await message("Snachala nastoj filtry cherez /filters")
        return
    await message("Ishyu kvartiry...")
    listings = parse_listings(filters_data)
    if not listings:
        await message("Po tvoyim filtram nichego ne najdeno. Poprobuj rashirit parametry.")
        return
    for listing in listings[:5]:
        text = format_listing(listing)
        keyboard = [[InlineKeyboardButton("Otkryt na Krisha", url=listing["url"])]]
        if listing.get("photo_url"):
            await context.bot.send_photo(
                chat_id=update.effective_chat.id,
                photo=listing["photo_url"],
                caption=text,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        else:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=text,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
    if len(listings) > 5:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"Najdeno {len(listings)} objavlenij. Pokazany pervye 5."
        )


def format_listing(listing: dict) -> str:
    price_formatted = f"{listing['price']:,}".replace(",", " ")
    text = f"{listing['title']}\n\n"
    text += f"Cena: {price_formatted} tg/mes\n"
    text += f"Komnat: {listing['rooms']}\n"
    text += f"Ploshchad: {listing['area']} m2\n"
    text += f"Etazh: {listing['floor']}\n"
    text += f"Adres: {listing['address']}\n"
    if listing.get("district"):
        text += f"Rajon: {listing['district']}\n"
    if listing.get("description"):
        desc = listing["description"][:200] + "..." if len(listing["description"]) > 200 else listing["description"]
        text += f"\nOpisanie:\n{desc}"
    return text


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
            text = "Novoje objavlenie!\n\n" + format_listing(listing)
            keyboard = [[InlineKeyboardButton("Otkryt na Krisha", url=listing["url"])]]
            try:
                if listing.get("photo_url"):
                    await context.bot.send_photo(
                        chat_id=user_id,
                        photo=listing["photo_url"],
                        caption=text,
                        reply_markup=InlineKeyboardMarkup(keyboard)
                    )
                else:
                    await context.bot.send_message(
                        chat_id=user_id,
                        text=text,
                        reply_markup=InlineKeyboardMarkup(keyboard)
                    )
            except Exception as e:
                logger.error(f"Oshibka otpravki: {e}")
    except Exception as e:
        logger.error(f"Oshibka proverki: {e}")


async def stop_notifications(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
    user_id = update.effective_user.id
    jobs = context.job_queue.get_jobs_by_name(f"check_{user_id}")
    for job in jobs:
        job.schedule_removal()
    set_user_filters(user_id, {})
    text = "Uvedomlenija ostanovleny.\n\n"
    text += "Tvoi filtry udaleny. Chtoby vozobnovit poisk, nastoj filtry zanovo."
    if query:
        await query.edit_message_text(text)
    else:
        await update.message.reply_text(text)


async def back_to_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    keyboard = [
        [InlineKeyboardButton("Nastroit filtry", callback_data="set_filters")],
        [InlineKeyboardButton("Moi filtry", callback_data="show_filters")],
        [InlineKeyboardButton("Poisk sejchas", callback_data="search_now")],
        [InlineKeyboardButton("Ostanovit uvedomlenija", callback_data="stop")],
    ]
    await query.edit_message_text(
        "Glavnoe menju. Vyberi dejstvie:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


def main():
    init_db()
    application = Application.builder().token(BOT_TOKEN).build()
    conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(set_filters_start, pattern="^set_filters$")],
        states={
            SET_ROOMS: [CallbackQueryHandler(set_rooms, pattern="^rooms_")],
            SET_PRICE_FROM: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_price_from)],
            SET_PRICE_TO: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_price_to)],
            SET_AREA_FROM: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_area_from)],
            SET_AREA_TO: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_area_to)],
            CONFIRM: [CallbackQueryHandler(confirm_filters, pattern="^save_filters$|^set_filters$|^cancel$")],
        },
        fallbacks=[
            CallbackQueryHandler(cancel, pattern="^cancel$"),
            CommandHandler("cancel", cancel),
        ],
    )
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("filters", set_filters_start))
    application.add_handler(CommandHandler("search", search_now))
    application.add_handler(CommandHandler("myfilters", show_filters))
    application.add_handler(CommandHandler("stop", stop_notifications))
    application.add_handler(conv_handler)
    application.add_handler(CallbackQueryHandler(show_filters, pattern="^show_filters$"))
    application.add_handler(CallbackQueryHandler(search_now, pattern="^search_now$"))
    application.add_handler(CallbackQueryHandler(stop_notifications, pattern="^stop$"))
    application.add_handler(CallbackQueryHandler(back_to_start, pattern="^back_to_start$"))

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
