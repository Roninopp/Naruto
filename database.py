# naruto_bot/database.py
import sqlite3
import logging
from .config import config

# Configure logging
logging.basicConfig(
    level=logging.INFO if not config.DEBUG else logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def get_db_connection():
    """Establishes a connection to the SQLite database."""
    try:
        conn = sqlite3.connect(config.DATABASE_PATH)
        conn.row_factory = sqlite3.Row
        return conn
    except sqlite3.Error as e:
        logger.critical(f"Failed to connect to database: {e}")
        raise

def initialize_database():
    """
    Creates all necessary tables in the database if they don't already exist.
    Based on prompt 16.
    """
    logger.info("Initializing database...")
    
    # SQL commands to create tables
    # Note: Added 'current_hp' and 'current_chakra' as discussed in Player class.
    # Note: 'battle_cooldown' is stored as TEXT (ISO format datetime)
    create_players_table = """
    CREATE TABLE IF NOT EXISTS players (
        user_id INTEGER PRIMARY KEY,
        username TEXT NOT NULL,
        village TEXT NOT NULL,
        level INTEGER DEFAULT 1,
        exp INTEGER DEFAULT 0,
        total_exp INTEGER DEFAULT 0,
        max_hp INTEGER DEFAULT 100,
        current_hp INTEGER DEFAULT 100,
        max_chakra INTEGER DEFAULT 100,
        current_chakra INTEGER DEFAULT 100,
        strength INTEGER DEFAULT 10,
        speed INTEGER DEFAULT 10,
        intelligence INTEGER DEFAULT 10,
        stamina INTEGER DEFAULT 10,
        known_jutsus TEXT DEFAULT '[]',
        discovered_combinations TEXT DEFAULT '[]',
        ryo INTEGER DEFAULT 100,
        rank TEXT DEFAULT 'Academy Student',
        wins INTEGER DEFAULT 0,
        losses INTEGER DEFAULT 0,
        battle_cooldown TEXT,
        current_mission TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    """
    
    # Note: 'combination' MUST be unique.
    create_jutsu_discoveries_table = """
    CREATE TABLE IF NOT EXISTS jutsu_discoveries (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        combination TEXT UNIQUE NOT NULL,
        jutsu_name TEXT NOT NULL,
        discovered_by_id INTEGER,
        discovered_by_name TEXT,
        discovered_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    """
    
    create_battle_history_table = """
    CREATE TABLE IF NOT EXISTS battle_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        player1_id INTEGER,
        player2_id INTEGER,
        winner_id INTEGER,
        battle_log TEXT,
        duration_seconds INTEGER,
        fought_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    """
    
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            logger.debug("Creating 'players' table...")
            cursor.execute(create_players_table)
            
            logger.debug("Creating 'jutsu_discoveries' table...")
            cursor.execute(create_jutsu_discoveries_table)
            
            logger.debug("Creating 'battle_history' table...")
            cursor.execute(create_battle_history_table)
            
            conn.commit()
            logger.info("Database tables initialized successfully.")
    except sqlite3.Error as e:
        logger.critical(f"Database initialization failed: {e}")
        raise

if __name__ == "__main__":
    # Allows running this file directly to initialize the database
    # python -m naruto_bot.database
    initialize_database()
