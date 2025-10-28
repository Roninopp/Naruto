# main.py (Simplified - Loop Management Test - Corrected)
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
        logger.info("Shutting down bot (in finally block)...")
        # Ensure shutdown is awaited if run_polling raises exception early
        # FIX: Use _initialized (with underscore)
        if hasattr(application, '_initialized') and application._initialized:
            await application.shutdown()
        logger.info("Bot shutdown process complete.")

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(main())
    except KeyboardInterrupt:
        logger.info("Bot shutdown requested (KeyboardInterrupt).")
        # Ensure loop stops cleanly on Ctrl+C
        loop.stop()
    except RuntimeError as e:
        if "Cannot close a running event loop" in str(e) or "This event loop is already running" in str(e):
             logger.critical(f"Caught known event loop error: {e}. This likely indicates an environment conflict.")
        else:
             logger.critical(f"Caught unexpected runtime error: {e}", exc_info=True)
    except Exception as e:
        logger.critical(f"Unhandled exception in __main__: {e}", exc_info=True)
    finally:
        # Ensure the loop is closed if it's still running
        if loop.is_running():
            loop.stop() # Ensure it stops before closing
        if not loop.is_closed():
            logger.info("Closing event loop...")
            # Wait briefly for tasks to finish cancellation if needed
            # loop.run_until_complete(asyncio.sleep(0.1)) # Optional small delay
            loop.close()
            logger.info("Event loop closed.")
