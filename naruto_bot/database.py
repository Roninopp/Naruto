import sqlite3
import logging
import os
from .config import config

logger = logging.getLogger(__name__)

# --- Database Schema (Prompt 16) ---
DB_SCHEMA = [
    """
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
        chakra_regen_rate INTEGER DEFAULT 5,
        strength INTEGER DEFAULT 10,
        speed INTEGER DEFAULT 10,
        intelligence INTEGER DEFAULT 10,
        stamina INTEGER DEFAULT 10,
        known_jutsus TEXT DEFAULT '[]',
        discovered_combinations TEXT DEFAULT '[]',
        equipment TEXT DEFAULT '{}',
        ryo INTEGER DEFAULT 100,
        rank TEXT DEFAULT 'Academy Student',
        wins INTEGER DEFAULT 0,
        losses INTEGER DEFAULT 0,
        current_mission TEXT,
        battle_cooldown TEXT,
        last_regen TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS jutsu_discoveries (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        combination TEXT UNIQUE,
        jutsu_name TEXT,
        discovered_by_id INTEGER,
        discovered_by_name TEXT,
        discovered_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS battle_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        player1_id INTEGER,
        player2_id INTEGER,
        winner_id INTEGER,
        battle_log TEXT,
        fought_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    """
]

def get_db_connection() -> sqlite3.Connection:
    """Establishes a connection to the SQLite database."""
    try:
        conn = sqlite3.connect(config.DATABASE_PATH)
        conn.row_factory = sqlite3.Row
        return conn
    except sqlite3.Error as e:
        logger.critical(f"Failed to connect to database at {config.DATABASE_PATH}: {e}")
        raise

def init_database():
    """
    Initializes the database and creates tables based on the schema.
    """
    if not os.path.exists(config.DATABASE_PATH):
        logger.info(f"Database file not found at {config.DATABASE_PATH}. Creating new file.")

    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            for table_sql in DB_SCHEMA:
                cursor.execute(table_sql)
            conn.commit()
            logger.info("Database tables verified and created successfully.")
    except sqlite3.Error as e:
        logger.error(f"An error occurred during database initialization: {e}")
        raise
    except Exception as e:
        logger.critical(f"A critical error occurred setting up the database: {e}")
        raise
```

### 2. Commit All Fixes and Redeploy

1.  **Commit the `database.py` file** (and the other corrected files from before if they aren't committed yet).
    ```bash
    # In your local terminal (GitHub repo folder)
    git add .
    git commit -m "FIX: Add missing init_database function and push all handler fixes."
    git push origin main
    
