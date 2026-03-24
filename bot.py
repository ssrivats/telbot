import os
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Temporary storage (in memory for now)
user_watches = {}   # user_id → list of event_codes

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎬 *BMS Watchlist Bot Ready!*\n\n"
        "Send me a movie name or BMS link to start monitoring.\n"
        "Example: `/add Youth` or just paste the full BMS page link."
    )

async def add_movie(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    # Simple extraction for now
    event_code = None
    import re
    match = re.search(r'(ET\d{7,})', text, re.I)
    if match:
        event_code = match.group(1).upper()

    if not event_code:
        await update.message.reply_text("❌ Could not find ET code. Please send the full BMS link.")
        return

    user_id = update.effective_user.id
    if user_id not in user_watches:
        user_watches[user_id] = []

    if event_code in user_watches[user_id]:
        await update.message.reply_text("✅ Already monitoring this movie.")
        return

    user_watches[user_id].append(event_code)
    await update.message.reply_text(f"✅ Added {event_code} to your watchlist.\nI'll alert you when ELITE seats open.")

async def list_watches(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    watches = user_watches.get(user_id, [])
    if not watches:
        await update.message.reply_text("You have no watches yet.")
        return
    await update.message.reply_text("Your watches:\n" + "\n".join(watches))

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("add", add_movie))
    app.add_handler(CommandHandler("list", list_watches))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, add_movie))

    print("🚀 Telegram Bot started...")
    app.run_polling()

if __name__ == "__main__":
    main()