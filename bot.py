import os
import logging
import re
import asyncio
import requests
import threading
import time
from datetime import datetime, timedelta
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
if not TELEGRAM_TOKEN:
    raise ValueError("TELEGRAM_TOKEN is required")

# Global storage: user_id → list of watches
user_watches = {}   # {user_id: [{"event_code": "...", "title": "...", "session_data": {...}}]}

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

# ── Seed session with Playwright (once per movie) ────────────────────────────
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

# ── Poll seats ───────────────────────────────────────────────────────────────
def poll_seats(session_data):
    try:
        resp = requests.get(
            session_data["seatlayout_url"],
            cookies=session_data["cookies"],
            headers=session_data["headers"],
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

# ── Background monitoring ────────────────────────────────────────────────────
def start_monitoring(user_id, event_code, title):
    session = seed_session(event_code, _slugify(title))
    if not session:
        logger.error(f"Failed to seed session for {event_code}")
        return

    watch = {"event_code": event_code, "title": title, "session": session}
    if user_id not in user_watches:
        user_watches[user_id] = []
    user_watches[user_id].append(watch)

    logger.info(f"Started monitoring {title} ({event_code}) for user {user_id}")

    # Simple polling loop (for now fixed 30s - we can improve later)
    while True:
        if poll_seats(session):
            # Send alert
            asyncio.run(send_alert(user_id, title))
            break
        time.sleep(30)

async def send_alert(user_id, title):
    # For now just log. Later we can send Telegram message to user
    logger.info(f"🎉 ELITE seats opened for {title}!")

# ── Bot Handlers ─────────────────────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎬 *BMS Watchlist Bot*\n\n"
        "Send the full BMS movie link to start monitoring ELITE seats."
    )

async def add_movie(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    event_code = extract_event_code(text)
    if not event_code:
        await update.message.reply_text("❌ Could not find ET code. Please paste the full BMS movie link.")
        return

    title = "Unknown Movie"
    if "youth" in text.lower():
        title = "Youth"

    user_id = update.effective_user.id

    # Start monitoring in background thread
    threading.Thread(target=start_monitoring, args=(user_id, event_code, title), daemon=True).start()

    await update.message.reply_text(
        f"✅ Added **{title}** ({event_code})\n\n"
        f"Monitoring ELITE seats at Sathyam, HDFC Express Avenue & Palazzo.\n"
        f"I'll alert you when back seats open."
    )

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, add_movie))

    logger.info("🚀 BMS Watchlist Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()