# main.py (Simplified - Letting PTB manage loop)
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

async def main_async_logic():
    """Contains the main async setup and run logic."""
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
    # Let run_polling handle the loop internally
    await application.run_polling()
    # Code here will run after run_polling stops (e.g., on shutdown signal)
    logger.info("Bot polling stopped.")


if __name__ == "__main__":
    try:
        # Use asyncio.run() - the standard way to run the main async function
        asyncio.run(main_async_logic())
    except KeyboardInterrupt:
        logger.info("Bot shutdown requested (KeyboardInterrupt).")
    except RuntimeError as e:
         if "Cannot close a running event loop" in str(e) or "This event loop is already running" in str(e):
             logger.critical(f"Caught known event loop error: {e}. This likely indicates an environment conflict.")
         else:
             logger.critical(f"Caught unexpected runtime error: {e}", exc_info=True)
    except Exception as e:
        logger.critical(f"Unhandled exception in __main__: {e}", exc_info=True)
    finally:
        logger.info("Main script finished.")
