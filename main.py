# main.py (Simplified for Testing)
import logging
import asyncio
from telegram.ext import Application
from telegram import Update
from telegram.ext import CommandHandler, ContextTypes
import os
from dotenv import load_dotenv

# --- Basic Logging ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# --- Load Token Directly ---
load_dotenv()
BOT_TOKEN = os.getenv('BOT_TOKEN')

# --- Dummy Handler ---
async def simple_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Simplified bot is running!")

async def main():
    logger.info("--- Starting Simplified Bot Test ---")

    if not BOT_TOKEN:
        logger.critical("BOT_TOKEN is not set. Exiting.")
        return

    # --- Create Minimal Bot Application ---
    application = Application.builder().token(BOT_TOKEN).build()

    # --- Add ONLY a simple start handler ---
    application.add_handler(CommandHandler('start', simple_start))
    logger.info("Added simple /start handler.")

    # --- Run the Bot ---
    logger.info("Bot is starting to poll...")
    try:
        # Use run_polling directly
        await application.run_polling()
    except Exception as e:
        logger.critical(f"Bot polling failed: {e}", exc_info=True) # Add exc_info for more details
    finally:
        # Graceful shutdown
        logger.info("Shutting down bot...")
        await application.shutdown()
        logger.info("Bot has been shut down.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot shutdown requested (KeyboardInterrupt).")
    except Exception as e:
        logger.critical(f"Unhandled exception in main: {e}", exc_info=True) # Add exc_info
