# naruto_bot/models.py
import json
import logging
import random
from datetime import datetime, timedelta
from .database import get_db_connection
from .cache import cache_manager
from .config import config
from .game_data import get_exp_for_level, RANKS, RANK_UP_LEVELS, STAT_GROWTH_PER_LEVEL, JUTSU_LIBRARY, VILLAGES

logger = logging.getLogger(__name__)

class Player:
    """
    Represents a player in the game.
    All data is loaded from the database row.
    """
    def __init__(self, db_row):
        self.user_id: int = db_row['user_id']
        self.username: str = db_row['username']
        self.village: str = db_row['village']
        self.level: int = db_row['level']
        self.exp: int = db_row['exp']
        self.total_exp: int = db_row['total_exp']
        
        self.max_hp: int = db_row['max_hp']
        self.current_hp: int = db_row['current_hp']
        self.max_chakra: int = db_row['max_chakra']
        self.current_chakra: int = db_row['current_chakra']
        
        self.strength: int = db_row['strength']
        self.speed: int = db_row['speed']
        self.intelligence: int = db_row['intelligence']
        self.stamina: int = db_row['stamina']
        
        self.ryo: int = db_row['ryo']
        self.rank: str = db_row['rank']
        self.wins: int = db_row['wins']
        self.losses: int = db_row['losses']
        self.current_mission: str | None = db_row['current_mission']
        
        # --- Deserialization ---
        # Load known jutsus (list of strings)
        try:
            self.known_jutsus: list[str] = json.loads(db_row['known_jutsus'])
        except (TypeError, json.JSONDecodeError):
            self.known_jutsus = []
            
        # Load discovered combinations (list of strings)
        try:
            self.discovered_combinations: list[str] = json.loads(db_row['discovered_combinations'])
        except (TypeError, json.JSONDecodeError):
            self.discovered_combinations = []
            
        # Load battle cooldown (datetime object)
        try:
            self.battle_cooldown: datetime | None = datetime.fromisoformat(db_row['battle_cooldown'])
        except (TypeError, ValueError):
            self.battle_cooldown = None
            
        # Equipment (from Prompt 2) - This is not in the DB schema from Prompt 16.
        # We will add it as a class attribute, but it will NOT be persisted.
        # This should be fixed later by adding an 'equipment' TEXT column.
        self.equipment: dict = {"weapon": None, "armor": None, "accessory": None}
        
        # In-memory battle attributes
        self.in_battle = False
        self.battle_effects = {} # e.g., {'evasion_up': 2, 'defense_up': 3}

    def save(self):
        """Saves the player's current state to the database and cache."""
        logger.debug(f"Saving player {self.user_id}...")
        
        # --- Serialization ---
        known_jutsus_json = json.dumps(self.known_jutsus)
        discovered_combinations_json = json.dumps(self.discovered_combinations)
        battle_cooldown_iso = self.battle_cooldown.isoformat() if self.battle_cooldown else None
        
        sql = """
        UPDATE players
        SET
            username = ?, village = ?, level = ?, exp = ?, total_exp = ?,
            max_hp = ?, current_hp = ?, max_chakra = ?, current_chakra = ?,
            strength = ?, speed = ?, intelligence = ?, stamina = ?,
            known_jutsus = ?, discovered_combinations = ?,
            ryo = ?, rank = ?, wins = ?, losses = ?,
            battle_cooldown = ?, current_mission = ?
        WHERE user_id = ?
        """
        
        params = (
            self.username, self.village, self.level, self.exp, self.total_exp,
            self.max_hp, self.current_hp, self.max_chakra, self.current_chakra,
            self.strength, self.speed, self.intelligence, self.stamina,
            known_jutsus_json, discovered_combinations_json,
            self.ryo, self.rank, self.wins, self.losses,
            battle_cooldown_iso, self.current_mission,
            self.user_id
        )
        
        try:
            with get_db_connection() as conn:
                conn.execute(sql, params)
                conn.commit()
            
            # Update the cache
            cache_manager.set_data("player", self.user_id, self, ttl=config.PLAYER_CACHE_TTL)
            logger.debug(f"Player {self.user_id} saved to DB and cache.")
            
        except sqlite3.Error as e:
            logger.error(f"Failed to save player {self.user_id}: {e}")

    def add_exp(self, amount: int) -> tuple[bool, str]:
        """Adds EXP, handles level-ups, and returns (level_up_bool, message)."""
        if self.level >= 60:
            return False, ""
            
        self.exp += amount
        self.total_exp += amount
        exp_needed = get_exp_for_level(self.level)
        level_up_message = ""
        
        while self.exp >= exp_needed and self.level < 60:
            self.level += 1
            self.exp -= exp_needed
            level_up_message += self._process_level_up()
            
            # Check for rank up
            rank_up_message = self.check_for_rank_up()
            if rank_up_message:
                level_up_message += f"\n{rank_up_message}"
                
            exp_needed = get_exp_for_level(self.level)
            
        return bool(level_up_message), f"Gained +{amount} EXP!\n{level_up_message}"

    def _process_level_up(self) -> str:
        """Applies stat gains for a single level up (Prompt 4)."""
        # Auto-distribute 6 points
        gains = {'strength': 0, 'speed': 0, 'intelligence': 0, 'stamina': 0}
        for _ in range(STAT_GROWTH_PER_LEVEL):
            stat_to_increase = random.choice(['strength', 'speed', 'intelligence', 'stamina'])
            gains[stat_to_increase] += 1
            
        self.strength += gains['strength']
        self.speed += gains['speed']
        self.intelligence += gains['intelligence']
        self.stamina += gains['stamina']
        
        # Increase HP and Chakra
        hp_gain = 10 + (self.stamina // 10)
        chakra_gain = 5 + (self.intelligence // 10)
        
        self.max_hp += hp_gain
        self.max_chakra += chakra_gain
        
        # Heal on level up
        self.current_hp = self.max_hp
        self.current_chakra = self.max_chakra
        
        return (
            f"🎉 **LEVEL UP!** You are now Level {self.level}!\n"
            f"❤️ Max HP +{hp_gain}!\n"
            f"🔵 Max Chakra +{chakra_gain}!\n"
            f"💪 Str +{gains['strength']}, ⚡ Spd +{gains['speed']}, "
            f"🧠 Int +{gains['intelligence']}, 맷 Sta +{gains['stamina']}!"
        )

    def check_for_rank_up(self) -> str | None:
        """Checks if the player meets the requirements for a rank-up (Prompt 4)."""
        current_rank_index = RANKS.index(self.rank)
        if current_rank_index + 1 >= len(RANKS):
            return None # Already max rank
            
        next_rank = RANKS[current_rank_index + 1]
        level_req = RANK_UP_LEVELS[self.rank]
        
        if self.level >= level_req:
            self.rank = next_rank
            return f"🌟 **RANK UP!** You have been promoted to **{next_rank}**! 🌟"
        return None

    def add_jutsu(self, jutsu_key: str) -> bool:
        """Adds a jutsu to the player's known list if not already present."""
        if jutsu_key not in self.known_jutsus:
            if len(self.known_jutsus) >= 25:
                return False # Max jutsus reached
            self.known_jutsus.append(jutsu_key)
            return True
        return False
        
    def add_discovered_combination(self, combo_str: str):
        """Adds a hand sign combination to the player's discovered list."""
        if combo_str not in self.discovered_combinations:
            self.discovered_combinations.append(combo_str)
            
    def is_on_cooldown(self, cooldown_type: str) -> tuple[bool, str]:
        """Checks if a player is on a specific cooldown (e.g., 'battle')."""
        if cooldown_type == 'battle':
            if self.battle_cooldown and datetime.now() < self.battle_cooldown:
                remaining = self.battle_cooldown - datetime.now()
                return True, f"{remaining.seconds} seconds"
        # Can add 'mission', 'train' cooldowns here
        return False, ""

    def set_cooldown(self, cooldown_type: str, seconds: int):
        """Sets a cooldown for the player."""
        if cooldown_type == 'battle':
            self.battle_cooldown = datetime.now() + timedelta(seconds=seconds)
    
    def get_village_bonus(self) -> tuple[str, float]:
        """Gets the player's elemental bonus from their village (Prompt 3)."""
        village_info = VILLAGES.get(self.village, {})
        return village_info.get('element_bonus', 'none'), village_info.get('bonus_percent', 0.0)

# --- Player Management Functions ---

def get_player(user_id: int) -> Player | None:
    """
    Fetches a player from the cache or database.
    This is the primary function for loading players.
    """
    # 1. Check cache
    cached_player = cache_manager.get_data("player", user_id)
    if cached_player:
        logger.debug(f"Cache hit for player {user_id}.")
        return cached_player
        
    # 2. If miss, check database
    logger.debug(f"Cache miss for player {user_id}. Checking DB.")
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM players WHERE user_id = ?", (user_id,))
            row = cursor.fetchone()
            
            if row:
                # 3. If found, create object, cache it, and return
                player = Player(row)
                cache_manager.set_data("player", user_id, player, ttl=config.PLAYER_CACHE_TTL)
                return player
            else:
                # 4. If not found
                return None
                
    except sqlite3.Error as e:
        logger.error(f"Error fetching player {user_id} from DB: {e}")
        return None

def create_player(user_id: int, username: str, village: str) -> Player | None:
    """Creates a new player and saves them to the database."""
    if village not in VILLAGES:
        logger.warning(f"Invalid village choice {village} for user {user_id}")
        return None
        
    # Start with base stats and add default learned jutsus
    base_jutsus = ['clone_jutsu', 'substitution']
    # Add village-specific starter jutsu
    if village == 'konoha':
        base_jutsus.append('flame_bullet')
    elif village == 'kiri':
        base_jutsus.append('water_bullet')
    elif village == 'suna':
        base_jutsus.append('air_bullet')
    elif village == 'kumo':
        base_jutsus.append('lightning_strike')
    elif village == 'iwa':
        base_jutsus.append('stone_bullet')

    sql = """
    INSERT INTO players (user_id, username, village, known_jutsus)
    VALUES (?, ?, ?, ?)
    """
    params = (user_id, username, village, json.dumps(base_jutsus))
    
    try:
        with get_db_connection() as conn:
            conn.execute(sql, params)
            conn.commit()
        logger.info(f"New player created: {user_id} ({username}) in {village}")
        
        # Load the newly created player (which also caches them)
        return get_player(user_id)
        
    except sqlite3.IntegrityError:
        logger.warning(f"Attempted to create player {user_id}, but they already exist.")
        return get_player(user_id) # Return existing player
    except sqlite3.Error as e:
        logger.error(f"Error creating player {user_id}: {e}")
        return None
