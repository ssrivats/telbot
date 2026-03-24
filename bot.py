import os
import logging
import re
import threading
import time
import requests
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
if not TELEGRAM_TOKEN:
    raise ValueError("TELEGRAM_TOKEN is required")

user_watches = {}   # user_id → list of event_codes

BMS_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

def extract_event_code(text: str):
    match = re.search(r'(ET\d{7,})', text, re.I)
    if match:
        return match.group(1).upper()
    match = re.search(r'/([A-Z]{2}\d{7,})', text)
    if match:
        return match.group(1).upper()
    return None

def _slugify(name):
    s = name.lower()
    s = re.sub(r'[^a-z0-9\s-]', '', s)
    s = re.sub(r'[\s-]+', '-', s)
    return s.strip('-')

# Simple monitoring function (placeholder for now)
def start_monitoring(user_id, event_code, title):
    logger.info(f"[{user_id}] Monitoring started for {title} ({event_code})")
    # Simulate monitoring for testing
    time.sleep(8)
    logger.info(f"[{user_id}] Still monitoring {title}...")
    # In real version we will add Playwright + polling here

# Bot Handlers
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎬 *BMS Watchlist Bot*\n\n"
        "Paste the full BMS movie link to start monitoring ELITE seats.\n"
        "Commands:\n"
        "/list - Show your watches\n"
        "/stop ETxxxxxx - Stop monitoring a movie"
    )

async def add_movie(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    event_code = extract_event_code(text)
    if not event_code:
        await update.message.reply_text("❌ Could not find ET code. Please paste the full BMS movie link.")
        return

    title = "Youth" if "youth" in text.lower() else event_code
    user_id = update.effective_user.id

    await update.message.reply_text(
        f"✅ Added **{title}** ({event_code})\n\n"
        f"Monitoring ELITE seats at Sathyam, HDFC Express Avenue & Palazzo.\n"
        f"I'll alert you when back seats open."
    )

    # Start monitoring thread
    threading.Thread(target=start_monitoring, args=(user_id, event_code, title), daemon=True).start()

async def list_watches(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    watches = user_watches.get(user_id, [])
    if not watches:
        await update.message.reply_text("You have no active watches.")
        return
    msg = "Your active watches:\n" + "\n".join(watches)
    await update.message.reply_text(msg)

async def stop_watch(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    event_code = extract_event_code(text)
    if not event_code:
        await update.message.reply_text("Please provide the ET code. Example: /stop ET00485590")
        return

    user_id = update.effective_user.id
    if user_id in user_watches:
        user_watches[user_id] = [w for w in user_watches[user_id] if w != event_code]

    await update.message.reply_text(f"✅ Stopped monitoring {event_code}.")

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("list", list_watches))
    app.add_handler(CommandHandler("stop", stop_watch))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, add_movie))

    logger.info("🚀 BMS Watchlist Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()