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

---

### Final Steps to Run (Again)

1.  **Commit to GitHub:** Ensure the code above is in your local `naruto_bot/database.py` file. Then commit and push to GitHub.
    ```bash
    git add naruto_bot/database.py
    git commit -m "Ensure database.py has the correct init_database function"
    git push origin main
    ```
2.  **Clean Redeploy on VPS:**
    ```bash
    # Stop any running bot first!
    pkill -f 'python main.py'
    cd ~
    rm -rf Naruto
    git clone https://github.com/Roninopp/Naruto
    cd Naruto
    
    # Re-create .env and venv
    echo '# .env file' > .env
    echo 'BOT_TOKEN=7473579334:AAHzx7x0qTTV0ak-HzCiMFTN0fotqS91qMw' >> .env
    echo 'ADMIN_IDS=6837532865' >> .env
    echo 'REDIS_URL=redis://localhost:6379' >> .env
    echo 'DATABASE_PATH=naruto_bot.db' >> .env
    echo 'DEBUG=False' >> .env
    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
    
    # RUN THE BOT
    python main.py
    
