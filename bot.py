import os
import logging
import re
import threading
import time
import requests
from datetime import datetime, timedelta
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
if not TELEGRAM_TOKEN:
    raise ValueError("TELEGRAM_TOKEN is required")

# Global storage: user_id → list of active watches
user_watches = {}   # {user_id: [{"event_code": "...", "title": "...", "thread": thread_object}]}

BMS_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

# ── Helpers ──────────────────────────────────────────────────────────────────
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

# ── Seed session with Playwright ─────────────────────────────────────────────
def seed_session(event_code, movie_slug):
    from playwright.sync_api import sync_playwright
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
            context = browser.new_context(user_agent=BMS_UA)
            page = context.new_page()

            seat_payloads = []
            def handle(response):
                if "seatlayout" in response.url.lower():
                    seat_payloads.append({"url": response.url, "json": response.json()})

            page.on("response", handle)

            page.goto(f"https://in.bookmyshow.com/movies/chennai/{movie_slug}/{event_code}", timeout=60000)
            page.wait_for_timeout(12000)

            page.locator('text=/Book tickets|Buy tickets/i').first.click()
            page.wait_for_timeout(15000)

            cookies = {c["name"]: c["value"] for c in context.cookies()}
            headers = {"User-Agent": BMS_UA}

            if seat_payloads:
                return {
                    "cookies": cookies,
                    "headers": headers,
                    "seatlayout_url": seat_payloads[0]["url"]
                }
    except Exception as e:
        logger.error(f"Seeding failed for {event_code}: {e}")
    return None

# ── Poll for ELITE seats ─────────────────────────────────────────────────────
def poll_seats(session):
    try:
        resp = requests.get(
            session["seatlayout_url"],
            cookies=session["cookies"],
            headers=session["headers"],
            timeout=15
        )
        if resp.status_code == 200:
            data = resp.json()
            categories = data.get("data", {}).get("categories") or data.get("categories", [])
            for cat in categories:
                name = cat.get("name", "").lower()
                seats = int(cat.get("availableSeats") or 0)
                if "elite" in name and seats > 0:
                    return True
    except:
        pass
    return False

# ── Background monitoring thread ─────────────────────────────────────────────
def start_monitoring(user_id, event_code, title):
    logger.info(f"[{user_id}] Starting monitoring for {title} ({event_code})")

    session = seed_session(event_code, _slugify(title))
    if not session:
        logger.error(f"[{user_id}] Failed to seed session for {event_code}")
        return

    logger.info(f"[{user_id}] Monitoring started successfully for {title}")

    while True:
        if poll_seats(session):
            logger.info(f"[{user_id}] 🎉 ELITE seats found for {title}!")
            # TODO: Send real Telegram message to user
            break
        time.sleep(30)

# ── Bot Handlers ─────────────────────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎬 *BMS Watchlist Bot*\n\n"
        "Paste the full BMS movie link to start monitoring.\n"
        "Use /list to see your watches\n"
        "Use /stop ETxxxxxx to stop monitoring a movie."
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
        f"Monitoring ELITE seats at your 3 PVRs...\n"
        f"I'll alert you when back seats open."
    )

    # Start monitoring
    threading.Thread(target=start_monitoring, args=(user_id, event_code, title), daemon=True).start()

async def list_watches(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    watches = user_watches.get(user_id, [])
    if not watches:
        await update.message.reply_text("You have no active watches.")
        return
    msg = "Your active watches:\n" + "\n".join([f"• {w['title']} ({w['event_code']})" for w in watches])
    await update.message.reply_text(msg)

async def stop_watch(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    event_code = extract_event_code(text)
    if not event_code:
        await update.message.reply_text("Please provide the ET code to stop. Example: /stop ET00485590")
        return

    user_id = update.effective_user.id
    if user_id in user_watches:
        user_watches[user_id] = [w for w in user_watches[user_id] if w['event_code'] != event_code]

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