import os
import logging
import re
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
if not TELEGRAM_TOKEN:
    raise ValueError("TELEGRAM_TOKEN is required")

user_watches = {}   # user_id → list of event_codes

def extract_event_code(text: str):
    # Try to find ET followed by numbers
    match = re.search(r'(ET\d{7,})', text, re.I)
    if match:
        return match.group(1).upper()
    
    # Try to extract from full BMS URL
    match = re.search(r'/([A-Z]{2}\d{7,})', text)
    if match:
        return match.group(1).upper()
    
    return None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎬 *BMS Watchlist Bot*\n\n"
        "Send me a movie name or the **full BMS link** to start monitoring ELITE seats at Sathyam, HDFC Express Avenue & Palazzo.\n\n"
        "Examples:\n"
        "• `/add Youth`\n"
        "• Paste the full BMS movie page link"
    )

async def add_movie(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    event_code = extract_event_code(text)
    
    if not event_code:
        await update.message.reply_text(
            "❌ Could not find ET code.\n\n"
            "Please paste the **full BMS movie link**.\n"
            "Example: https://in.bookmyshow.com/movies/chennai/youth/ET00485590"
        )
        return

    user_id = update.effective_user.id
    if user_id not in user_watches:
        user_watches[user_id] = []

    if event_code in user_watches[user_id]:
        await update.message.reply_text(f"✅ Already monitoring {event_code}")
        return

    user_watches[user_id].append(event_code)

    movie_name = text.replace("/add", "").strip() or event_code

    await update.message.reply_text(
        f"✅ Added **{movie_name}** ({event_code}) to your watchlist.\n\n"
        f"I'll monitor ELITE seats at your 3 PVRs and alert you when back seats open."
    )

    # TODO: Start actual monitoring here (next step)

async def list_watches(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    watches = user_watches.get(user_id, [])
    if not watches:
        await update.message.reply_text("You have no active watches.")
        return
    await update.message.reply_text("Your watches:\n" + "\n".join(watches))

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("add", add_movie))
    app.add_handler(CommandHandler("list", list_watches))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, add_movie))

    logger.info("🚀 BMS Watchlist Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()