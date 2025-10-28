# main.py
import logging
import asyncio
from telegram.ext import Application
from telegram.constants import ParseMode

# --- Local Imports ---
from naruto_bot.config import config
from naruto_bot.database import init_database
from naruto_bot.cache import cache_manager, test_redis_connection
# from naruto_bot.scheduler import setup_scheduler  # <-- FIX: Disabled to prevent loop conflict
from naruto_bot.handlers import register_all_handlers

# --- Logging Setup ---
logging.basicConfig(
    level=logging.DEBUG if config.DEBUG else logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("naruto_bot.log")
    ]
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("telegram.ext").setLevel(logging.INFO)

logger = logging.getLogger(__name__)

async def main():
    """Main function to set up and run the bot."""
    
    logger.info("--- Starting Naruto RPG Bot ---")

    # --- 1. Test Connections ---
    logger.info(f"Database path set to: {config.DATABASE_PATH}")
    
    # Test Redis connection
    if not await test_redis_connection():
        logger.critical("Failed to connect to Redis. Please check your REDIS_URL.")
        return
    logger.info(f"Successfully connected to Redis at {config.REDIS_URL}")
    
    # --- 2. Initialize Database ---
    try:
        init_database()
        logger.info("Database initialized successfully.")
    except Exception as e:
        logger.critical(f"Failed to initialize database: {e}")
        return

    # --- 3. Create Bot Application ---
    if not config.BOT_TOKEN:
        logger.critical("BOT_TOKEN is not set. Exiting.")
        return
        
    defaults = {"parse_mode": ParseMode.MARKDOWN}
    
    application = (
        Application.builder()
        .token(config.BOT_TOKEN)
        .defaults(defaults)
        .build()
    )

    # --- 4. Register All Handlers ---
    register_all_handlers(application)
    logger.info("All command and message handlers registered.")

    # --- 5. Start Scheduler ---
    # setup_scheduler()  # <-- FIX: Disabled to prevent loop conflict
    # logger.info("Background scheduler started.") # <-- FIX: Disabled
    
    # NOTE: The bot's built-in job_queue (used for missions/training) 
    # will still work. This fix only disables the separate 'apscheduler'.

    # --- 6. Run the Bot ---
    logger.info("Bot is starting to poll...")
    try:
        await application.run_polling()
    except Exception as e:
        logger.critical(f"Bot polling failed: {e}")
    finally:
        # Graceful shutdown
        logger.info("Shutting down bot...")
        await application.shutdown()
        await cache_manager.close()
        logger.info("Bot has been shut down.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot shutdown requested (KeyboardInterrupt).")
    except Exception as e:
        logger.critical(f"Unhandled exception in main: {e}")
