# naruto_bot/config.py
import os
import logging
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class Config:
    """
    Configuration class for the bot, loading values from environment variables.
    """
    
    # --- Bot Token (Required) ---
    BOT_TOKEN = os.getenv('BOT_TOKEN')
    if not BOT_TOKEN:
        logging.error("CRITICAL: BOT_TOKEN not found in .env file!")
        raise ValueError("BOT_TOKEN not found. Please set it in your .env file.")

    # --- Database & Cache ---
    # FIX: Use REDIS_URL directly instead of constructing from HOST/PORT
    REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379')
    DATABASE_PATH = os.getenv('DATABASE_PATH', 'naruto_bot.db')

    # --- Admin & Debug ---
    admin_ids_str = os.getenv('ADMIN_IDS', '')
    try:
        ADMIN_IDS = [int(x.strip()) for x in admin_ids_str.split(',') if x.strip()]
    except ValueError:
        logging.error(f"Invalid ADMIN_IDS format: {admin_ids_str}. Must be comma-separated integers.")
        ADMIN_IDS = []

    DEBUG = os.getenv('DEBUG', 'False').lower() == 'true'

    # --- Performance Config ---
    MAX_CONCURRENT_BATTLES = int(os.getenv('MAX_CONCURRENT_BATTLES', 15))
    BATTLE_TIMEOUT_SECONDS = int(os.getenv('BATTLE_TIMEOUT_SECONDS', 300))
    ANIMATION_DELAY = float(os.getenv('ANIMATION_DELAY', 0.8))
    PLAYER_CACHE_TTL = int(os.getenv('PLAYER_CACHE_TTL', 1800))
    BATTLE_CACHE_TTL = int(os.getenv('BATTLE_CACHE_TTL', 3600))
    CLEANUP_INTERVAL = int(os.getenv('CLEANUP_INTERVAL', 1800))
    DATABASE_BACKUP_HOURS = int(os.getenv('DATABASE_BACKUP_HOURS', 24))

# Create a single config instance
config = Config()
