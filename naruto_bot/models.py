import logging
import json
import sqlite3
import asyncio # Import asyncio
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Optional, Tuple

from .database import get_db_connection
from .cache import cache_manager
from .config import config
# Assuming game_data.py defines these properly
from .game_data import VILLAGES, RANKS, JUTSU_LIBRARY

logger = logging.getLogger(__name__)

# --- Player Class ---

class Player:
    """Represents a player in the Naruto RPG bot."""

    def __init__(self, user_id: int, username: str, village: str, level: int = 1,
                 exp: int = 0, total_exp: int = 0, max_hp: int = 100, current_hp: int = 100,
                 max_chakra: int = 100, current_chakra: int = 100, chakra_regen_rate: int = 5,
                 strength: int = 10, speed: int = 10, intelligence: int = 10, stamina: int = 10,
                 known_jutsus: list = None, discovered_combinations: list = None,
                 equipment: dict = None, ryo: int = 100, rank: str = 'Academy Student',
                 wins: int = 0, losses: int = 0, current_mission: Optional[str] = None,
                 battle_cooldown: Optional[str] = None, last_regen: Optional[str] = None,
                 created_at: Optional[str] = None):

        self.user_id = user_id
        self.username = username
        self.village = village
        self.level = level
        self.exp = exp
        self.total_exp = total_exp
        # Calculate max_hp based on stamina
        self.max_hp = 100 + (stamina * 10)
        self.current_hp = min(current_hp, self.max_hp) # Ensure current isn't > max on load
        # Calculate max_chakra based on intelligence
        self.max_chakra = 100 + (intelligence * 5)
        self.current_chakra = min(current_chakra, self.max_chakra) # Ensure current isn't > max
        self.chakra_regen_rate = chakra_regen_rate # Chakra points per 5 minutes
        self.strength = strength
        self.speed = speed
        self.intelligence = intelligence
        self.stamina = stamina
        self.known_jutsus = known_jutsus if known_jutsus is not None else []
        self.discovered_combinations = discovered_combinations if discovered_combinations is not None else []
        self.equipment = equipment if equipment is not None else {}
        self.ryo = ryo
        self.rank = rank
        self.wins = wins
        self.losses = losses
        self.current_mission = current_mission
        self.battle_cooldown = battle_cooldown # ISO format string
        self.last_regen = last_regen # ISO format string
        self.created_at = created_at or datetime.now(timezone.utc).isoformat()

        # Internal flag for saving
        self._modified = False

    # --- Properties and Basic Info ---

    def mark_modified(self):
        """Flags the player object as modified."""
        self._modified = True

    def get_village_bonus(self) -> Tuple[str, float]:
        """Returns the element and bonus multiplier for the player's village."""
        village_data = VILLAGES.get(self.village)
        if village_data and 'element' in village_data and 'bonus' in village_data:
            return village_data['element'], village_data['bonus']
        logger.warning(f"Village data incomplete or missing for key '{self.village}'")
        return 'none', 1.0 # Default if village not found or data missing

    def get_exp_for_level(self, level: int) -> int:
        """Calculates EXP needed for a given level (Prompt 4)."""
        # Using a simple formula first, can switch to EXP_TABLE if needed
        if level <= 0: return 0
        return level * 150

    # --- Resource Management ---

    def regenerate_resources(self, save: bool = False) -> bool:
        """Regenerates HP and Chakra based on time passed since last_regen."""
        now = datetime.now(timezone.utc)
        time_elapsed_minutes = 0

        if self.last_regen:
            try:
                last_regen_time = datetime.fromisoformat(self.last_regen)
                # Ensure last_regen_time is timezone-aware for comparison
                if last_regen_time.tzinfo is None:
                     last_regen_time = last_regen_time.replace(tzinfo=timezone.utc)

                time_diff = now - last_regen_time
                # Only regen if at least a minute has passed
                if time_diff.total_seconds() >= 60:
                     time_elapsed_minutes = time_diff.total_seconds() / 60
                else:
                     return False # Not enough time passed

            except (ValueError, TypeError):
                 logger.warning(f"Could not parse last_regen timestamp '{self.last_regen}' for player {self.user_id}. Resetting.")
                 self.last_regen = now.isoformat() # Reset on error
                 self.mark_modified()
                 # Allow regen calculation to proceed based on reset time (effectively 0 elapsed)

        # Proceed only if enough time passed or last_regen was invalid/reset
        regenerated = False
        if time_elapsed_minutes > 0 or not self.last_regen:
            # Simple HP regen (e.g., 1 HP per minute, up to max)
            hp_to_regen = min(int(time_elapsed_minutes), self.max_hp - self.current_hp)
            # Chakra regen (rate defined per 5 mins, calculate per minute)
            chakra_per_minute = self.chakra_regen_rate / 5.0
            chakra_to_regen = min(int(time_elapsed_minutes * chakra_per_minute), self.max_chakra - self.current_chakra)

            if hp_to_regen > 0:
                self.current_hp += hp_to_regen
                self.mark_modified()
                regenerated = True
                logger.debug(f"Player {self.user_id} regenerated {hp_to_regen} HP.")
            if chakra_to_regen > 0:
                self.current_chakra += chakra_to_regen
                self.mark_modified()
                regenerated = True
                logger.debug(f"Player {self.user_id} regenerated {chakra_to_regen} Chakra.")

        # Always update last_regen time if we calculated regen (even if amounts were 0)
        # or if it was invalid before
        if time_elapsed_minutes > 0 or not self.last_regen:
            self.last_regen = now.isoformat()
            self.mark_modified()
            if save and self._modified: # Only save if something actually changed
                self.save()
            return regenerated # Return True if HP or Chakra actually increased

        return False # Not enough time passed initially


    # --- Cooldowns ---

    def set_cooldown(self, cooldown_type: str, duration_seconds: int):
        """Sets a cooldown timestamp."""
        now = datetime.now(timezone.utc)
        cooldown_end = now + timedelta(seconds=duration_seconds)
        cooldown_str = cooldown_end.isoformat()

        if cooldown_type == 'battle':
            self.battle_cooldown = cooldown_str
            self.mark_modified()
            logger.debug(f"Battle cooldown set for player {self.user_id} until {cooldown_str}")
        else:
            logger.warning(f"Attempted to set unknown cooldown type '{cooldown_type}' for player {self.user_id}")

    def is_on_cooldown(self, cooldown_type: str) -> Tuple[bool, str]:
        """Checks if a cooldown is active and returns remaining time."""
        now = datetime.now(timezone.utc)
        cooldown_end_str = None

        if cooldown_type == 'battle':
            cooldown_end_str = self.battle_cooldown
        else:
            logger.warning(f"Checked unknown cooldown type '{cooldown_type}' for player {self.user_id}")
            return False, "0s"

        if cooldown_end_str:
            try:
                cooldown_end = datetime.fromisoformat(cooldown_end_str)
                # Ensure timezone aware
                if cooldown_end.tzinfo is None:
                     cooldown_end = cooldown_end.replace(tzinfo=timezone.utc)

                if now < cooldown_end:
                    remaining = cooldown_end - now
                    # Format remaining time nicely (e.g., 1m 30s)
                    total_seconds = int(remaining.total_seconds())
                    minutes, seconds = divmod(total_seconds, 60)
                    if minutes > 0:
                         return True, f"{minutes}m {seconds}s"
                    else:
                         return True, f"{seconds}s"
                else:
                    # Cooldown expired, clear it
                    if cooldown_type == 'battle':
                        self.battle_cooldown = None
                        self.mark_modified() # Mark modified only if cleared
                    return False, "0s"
            except (ValueError, TypeError):
                logger.error(f"Could not parse {cooldown_type} cooldown '{cooldown_end_str}' for player {self.user_id}. Clearing cooldown.")
                # Clear invalid cooldown
                if cooldown_type == 'battle':
                    self.battle_cooldown = None
                    self.mark_modified() # Mark modified only if cleared
                return False, "0s"
        return False, "0s"


    # --- Progression ---

    def add_exp(self, amount: int) -> Tuple[str, str]:
        """Adds experience points and handles level ups."""
        if amount <= 0:
            return "", "No EXP gained."

        self.exp += amount
        self.total_exp += amount
        self.mark_modified()

        exp_message = f"You gained {amount} EXP."
        level_up_messages = []
        exp_needed = self.get_exp_for_level(self.level)

        # Handle multiple level ups
        while self.exp >= exp_needed and self.level < 60: # Max level check
            self.level += 1
            self.exp -= exp_needed
            level_up_messages.append(f"🎉 **LEVEL UP!** You reached Level {self.level}! 🎉")

            # Stat growth (+6 points auto-distributed)
            # Example: +2 stamina, +1 str, +1 spd, +1 int, +1 chakra_regen_rate
            self.stamina += 2
            self.strength += 1
            self.speed += 1
            self.intelligence += 1
            # self.chakra_regen_rate += 1 # Or maybe increase max chakra/regen rate slightly?

            # Recalculate max HP/Chakra
            old_max_hp = self.max_hp
            old_max_chakra = self.max_chakra
            self.max_hp = 100 + (self.stamina * 10)
            self.max_chakra = 100 + (self.intelligence * 5)

            # Heal/Restore partially on level up (e.g., heal difference + 25%)
            hp_increase = self.max_hp - old_max_hp
            chakra_increase = self.max_chakra - old_max_chakra
            heal_amount = hp_increase + int(self.max_hp * 0.25)
            chakra_restore_amount = chakra_increase + int(self.max_chakra * 0.25)
            self.current_hp = min(self.max_hp, self.current_hp + heal_amount)
            self.current_chakra = min(self.max_chakra, self.current_chakra + chakra_restore_amount)

            level_up_messages.append(
                f"💪 Stats increased! (+2 STA, +1 STR, +1 SPD, +1 INT)\n"
                f"❤️ Max HP: {self.max_hp} (+{hp_increase}) | Current HP: {self.current_hp}\n"
                f"🔵 Max Chakra: {self.max_chakra} (+{chakra_increase}) | Current Chakra: {self.current_chakra}"
            )

            # Check for rank up
            new_rank = self.check_rank_up()
            if new_rank != self.rank:
                level_up_messages.append(f"🌟 **RANK UP!** You have been promoted to **{new_rank}**! 🌟")
                self.rank = new_rank

            self.mark_modified()
            exp_needed = self.get_exp_for_level(self.level) # Exp for the *new* level
            if self.level == 60: # Stop checking if max level reached
                 # Adjust EXP if overshot at max level
                 self.exp = min(self.exp, exp_needed -1 if exp_needed > 0 else 0) # Cap EXP at max level
                 break

        return "\n".join(level_up_messages), exp_message

    def check_rank_up(self) -> str:
        """Determines the player's rank based on their level."""
        # Define level thresholds for ranks clearly
        if self.level >= 50: return 'Kage'
        if self.level >= 35: return 'Jonin'
        if self.level >= 20: return 'Chunin'
        if self.level >= 5: return 'Genin'
        return 'Academy Student' # Default


    # --- Jutsus & Combinations ---

    def add_jutsu(self, jutsu_key: str) -> bool:
        """Adds a jutsu if not already known and below the limit."""
        if jutsu_key not in self.known_jutsus and len(self.known_jutsus) < 25:
            self.known_jutsus.append(jutsu_key)
            self.mark_modified()
            logger.debug(f"Player {self.user_id} learned jutsu: {jutsu_key}")
            return True
        elif jutsu_key in self.known_jutsus:
             logger.debug(f"Player {self.user_id} already knows jutsu: {jutsu_key}")
             return False # Already known
        else:
             logger.warning(f"Player {self.user_id} failed to learn {jutsu_key} (limit reached).")
             # Optionally inform the player they need to forget a jutsu
             return False # Limit reached

    def add_discovered_combination(self, combo_str: str) -> bool:
        """Adds a discovered hand sign combination."""
        if combo_str not in self.discovered_combinations:
            self.discovered_combinations.append(combo_str)
            self.mark_modified()
            logger.debug(f"Player {self.user_id} discovered combination: {combo_str}")
            return True
        return False

    # --- Database Operations ---

    def save(self):
        """Saves the player's current state to the database and updates cache."""
        # Use hasattr for robustness, ensure _modified exists before checking
        if not hasattr(self, '_modified') or not self._modified:
            # logger.debug(f"Player {self.user_id} save skipped, no modifications detected.")
            return

        # Ensure all fields match the database schema
        sql = """
        UPDATE players SET
            username = ?, village = ?, level = ?, exp = ?, total_exp = ?,
            max_hp = ?, current_hp = ?, max_chakra = ?, current_chakra = ?,
            chakra_regen_rate = ?, strength = ?, speed = ?, intelligence = ?, stamina = ?,
            known_jutsus = ?, discovered_combinations = ?, equipment = ?, ryo = ?,
            rank = ?, wins = ?, losses = ?, current_mission = ?, battle_cooldown = ?,
            last_regen = ?
        WHERE user_id = ?
        """
        # Ensure lists/dicts are saved as valid JSON strings, handle None cases
        params = (
            self.username, self.village, self.level, self.exp, self.total_exp,
            self.max_hp, self.current_hp, self.max_chakra, self.current_chakra,
            self.chakra_regen_rate, self.strength, self.speed, self.intelligence, self.stamina,
            json.dumps(self.known_jutsus or []),
            json.dumps(self.discovered_combinations or []),
            json.dumps(self.equipment or {}),
            self.ryo, self.rank, self.wins, self.losses,
            self.current_mission, self.battle_cooldown, self.last_regen,
            self.user_id
        )

        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(sql, params)
                conn.commit()
                # Verify update occurred (rowcount indicates rows affected)
                if cursor.rowcount == 0:
                     logger.warning(f"Failed to update player {self.user_id} in DB (user might not exist?). Modifications not saved.")
                     # Keep _modified = True if save failed? Or reset anyway? Resetting might hide issues.
                     # Let's keep it True so the next save attempt happens.
                else:
                     logger.info(f"Player {self.user_id} ({self.username}) data saved to database.")
                     # --- FIX: REMOVED CONFLICTING ASYNCIO CALL ---
                     # asyncio.create_task(cache_manager.set_data("players", str(self.user_id), self, ttl=config.PLAYER_CACHE_TTL))
                     self._modified = False # Reset modified flag ONLY on successful save

        except sqlite3.Error as e:
            logger.error(f"Failed to save player {self.user_id} data to DB: {e}", exc_info=True)
            # Do not reset _modified flag on DB error
        except Exception as e:
            logger.error(f"Unexpected error saving player {self.user_id}: {e}", exc_info=True)
            # Do not reset _modified flag on other errors


    @classmethod
    def _load_from_db(cls, user_id: int) -> Optional['Player']:
        """Loads player data directly from the database (synchronous helper)."""
        logger.debug(f"DB load: Attempting to load player {user_id} from database.")
        sql = "SELECT * FROM players WHERE user_id = ?"
        try:
            with get_db_connection() as conn:
                 conn.row_factory = sqlite3.Row
                 row = conn.execute(sql, (user_id,)).fetchone()

            if row:
                logger.debug(f"DB load: Player {user_id} found in database.")
                # Deserialize JSON fields safely
                try:
                    known_jutsus = json.loads(row['known_jutsus']) if row['known_jutsus'] else []
                    discovered_combinations = json.loads(row['discovered_combinations']) if row['discovered_combinations'] else []
                    equipment = json.loads(row['equipment']) if row['equipment'] else {}
                except json.JSONDecodeError as json_e:
                     logger.error(f"JSON decode error loading player {user_id} from DB: {json_e}. Corrupted data found. Returning None.")
                     return None # Treat corrupted data as not found

                # Convert row to dict for easier initialization
                player_data = dict(row)
                player_data['known_jutsus'] = known_jutsus
                player_data['discovered_combinations'] = discovered_combinations
                player_data['equipment'] = equipment

                # Ensure all required keys for __init__ are present or handle missing ones
                # This helps catch schema mismatches
                required_keys = ['user_id', 'username', 'village', 'level', 'exp', 'total_exp',
                                 'max_hp', 'current_hp', 'max_chakra', 'current_chakra',
                                 'chakra_regen_rate', 'strength', 'speed', 'intelligence', 'stamina',
                                 'known_jutsus', 'discovered_combinations', 'equipment', 'ryo', 'rank',
                                 'wins', 'losses', 'current_mission', 'battle_cooldown', 'last_regen', 'created_at']
                
                # Check for missing keys that __init__ expects
                missing_keys = [key for key in required_keys if key not in player_data]
                if missing_keys:
                    logger.error(f"DB data for player {user_id} is missing required keys: {missing_keys}. Cannot create Player object.")
                    return None

                try:
                     # Filter player_data to only include keys expected by __init__
                     init_data = {key: player_data[key] for key in required_keys if key in player_data}
                     player = cls(**init_data)
                     # Don't cache here, let get_player handle it
                     return player
                except TypeError as init_e:
                     logger.error(f"Error initializing Player object for {user_id} from DB data: {init_e}. DB row might have extra/missing columns compared to __init__. Row: {dict(row)}")
                     return None # Failed to create object
            else:
                logger.debug(f"DB load: Player {user_id} not found in database.")
                return None
        except sqlite3.Error as db_e:
            logger.error(f"Database error loading player {user_id}: {db_e}", exc_info=True)
            return None
        except Exception as e:
             logger.error(f"Unexpected error loading player {user_id} from DB: {e}", exc_info=True)
             return None

# --- Global Player Functions ---

async def get_player(user_id: int) -> Optional[Player]:
    """
    Retrieves a player object, checking cache first, then database.
    Returns None if the player doesn't exist or on error. Async version.
    """
    if not isinstance(user_id, int):
        logger.warning(f"get_player called with non-integer user_id: {user_id} ({type(user_id)})")
        return None

    cache_key = str(user_id)
    try:
        # MUST await the async cache call
        cached_player = await cache_manager.get_data("players", cache_key)

        if cached_player:
            if isinstance(cached_player, Player):
                 logger.debug(f"Cache hit for player {user_id}.")
                 # Optionally trigger async resource regen check without saving immediately
                 # asyncio.create_task(cached_player.regenerate_resources(save=False))
                 return cached_player
            else:
                 logger.warning(f"Cache data for player {user_id} is invalid type: {type(cached_player)}. Deleting cache.")
                 await cache_manager.delete_data("players", cache_key)
                 # Fall through to load from DB

        # If not in cache or cache was invalid, load from DB
        logger.debug(f"Cache miss for player {user_id}. Loading from DB...")
        # _load_from_db is synchronous, run it in default executor
        loop = asyncio.get_running_loop()
        player = await loop.run_in_executor(None, Player._load_from_db, user_id)

        if player:
            # Cache the newly loaded player
            await cache_manager.set_data("players", cache_key, player, ttl=config.PLAYER_CACHE_TTL)
            logger.debug(f"Player {user_id} loaded from DB and cached.")
        # Return player (which is None if not found in DB or on load error)
        return player

    except ConnectionError as redis_err:
         logger.error(f"Redis connection error in get_player for {user_id}: {redis_err}. Attempting DB load.")
         # Fallback directly to DB if Redis fails
         loop = asyncio.get_running_loop()
         try:
              player = await loop.run_in_executor(None, Player._load_from_db, user_id)
              # Don't try to cache if Redis is down
              return player
         except Exception as db_fallback_err:
              logger.error(f"DB fallback failed for player {user_id} after Redis error: {db_fallback_err}", exc_info=True)
              return None
    except Exception as e:
         logger.error(f"Unexpected error in get_player for {user_id}: {e}", exc_info=True)
         return None


def create_player(user_id: int, username: str, village: str) -> Optional[Player]:
    """
    Creates a new player entry in the database (Synchronous).
    Returns the new Player object or None on error.
    """
    logger.info(f"Attempting to create new player: {user_id}, {username}, {village}")
    # Validate input
    if not isinstance(user_id, int) or user_id <= 0:
         logger.error(f"Invalid user_id for create_player: {user_id}")
         return None
    if not username or not isinstance(username, str):
         logger.warning(f"Invalid or missing username for create_player (user_id: {user_id}). Using default.")
         username = f"Ninja-{user_id}" # Default username
    if village not in VILLAGES:
         logger.error(f"Invalid village '{village}' for create_player (user_id: {user_id}).")
         return None

    sql = """
    INSERT INTO players (
        user_id, username, village, rank, created_at, last_regen,
        level, exp, total_exp, max_hp, current_hp, max_chakra, current_chakra,
        chakra_regen_rate, strength, speed, intelligence, stamina,
        known_jutsus, discovered_combinations, equipment, ryo, wins, losses
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    now_iso = datetime.now(timezone.utc).isoformat()
    initial_rank = 'Academy Student'
    # Initial stats based on defaults in __init__
    initial_stamina = 10
    initial_intelligence = 10
    initial_max_hp = 100 + (initial_stamina * 10)
    initial_max_chakra = 100 + (initial_intelligence * 5)

    params = (
        user_id, username, village, initial_rank, now_iso, now_iso,
        1, 0, 0, initial_max_hp, initial_max_hp, initial_max_chakra, initial_max_chakra, # level, exp, totals, hp, chakra
        5, 10, 10, initial_intelligence, initial_stamina, # regen, stats
        '[]', '[]', '{}', 100, 0, 0 # jutsus, combos, equip, ryo, wins, losses
    )

    try:
        with get_db_connection() as conn:
            conn.execute(sql, params)
            conn.commit()
        logger.info(f"Player {user_id} ({username}) created successfully in DB.")

        # Load the newly created player using the synchronous helper
        new_player = Player._load_from_db(user_id)
        if new_player:
             # --- FIX: REMOVED CONFLICTING ASYNCIO CALL ---
             # asyncio.create_task(cache_manager.set_data("players", str(user_id), new_player, ttl=config.PLAYER_CACHE_TTL))
             logger.debug(f"Newly created player {user_id} cache update removed.")
             return new_player
        else:
             # This indicates a problem with _load_from_db or immediate data inconsistency
             logger.error(f"CRITICAL: Failed to load player {user_id} immediately after creation.")
             return None

    except sqlite3.IntegrityError:
        logger.warning(f"Attempted to create player {user_id}, but user_id likely already exists (IntegrityError).")
        # Try loading the existing player synchronously as a fallback?
        existing_player = Player._load_from_db(user_id)
        if existing_player:
             logger.warning(f"Loaded existing player {user_id} instead of creating.")
             # --- FIX: REMOVED CONFLICTING ASYNCIO CALL ---
             # asyncio.create_task(cache_manager.set_data("players", str(user_id), existing_player, ttl=config.PLAYER_CACHE_TTL))
             return existing_player # Return existing player if creation failed due to conflict
        return None # Indicate failure
    except sqlite3.Error as e:
        logger.error(f"Database error during player creation {user_id}: {e}", exc_info=True)
        return None
    except Exception as e:
        logger.error(f"Unexpected error during player creation {user_id}: {e}", exc_info=True)
        return None

# --- Add EXP Table if needed ---
# Example calculation for EXP table based on formula level * 150
# EXP_TABLE = {level: level * 150 for level in range(1, 61)}
