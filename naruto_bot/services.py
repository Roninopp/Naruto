# naruto_bot/services.py
import logging
from .config import config
from .game_data import JUTSU_LIBRARY, HAND_SIGNS

logger = logging.getLogger(__name__)

# --- Helper Functions ---

def health_bar(current: int, maximum: int, length: int = 10) -> str:
    """Generates a text-based health bar."""
    if maximum == 0:
        return f"[░░░░░░░░░░] 0/0"
    filled = int((current / maximum) * length)
    empty = length - filled
    bar = f"[{'█' * filled}{'░' * empty}]"
    return f"{bar} {current}/{maximum}"

def chakra_bar(current: int, maximum: int, length: int = 8) -> str:
    """Generates an emoji-based chakra bar."""
    if maximum == 0:
        return f"[⚪⚪⚪⚪⚪⚪⚪⚪] 0/0"
    filled = int((current / maximum) * length)
    empty = length - filled
    return f"[{'🔵' * filled}{'⚪' * empty}] {current}/{maximum}"

async def safe_animation(message, animation_func, fallback_text: str):
    """Wraps an animation function in a try/except block."""
    try:
        await animation_func(message)
    except Exception as e:
        logger.warning(f"Animation failed, editing to fallback. Error: {e}")
        try:
            await message.edit_text(fallback_text)
        except Exception as e2:
            logger.error(f"Failed to even edit to fallback text! Error: {e2}")

# --- Jutsu Service Functions ---

def get_jutsu_by_name(jutsu_name: str) -> tuple[str, dict] | None:  # FIX: Returns tuple
    """
    Finds a jutsu in the JUTSU_LIBRARY by its name or key.
    Returns (jutsu_key, jutsu_dict) tuple or None.
    """
    jutsu_name = jutsu_name.lower().strip()
    
    # Check if it's a direct key match
    if jutsu_name in JUTSU_LIBRARY:
        return jutsu_name, JUTSU_LIBRARY[jutsu_name]
    
    # Allow searching by full name
    for key, jutsu in JUTSU_LIBRARY.items():
        if jutsu['name'].lower() == jutsu_name:
            return key, jutsu
            
    return None

def get_jutsu_by_signs(signs: list[str]) -> tuple[str, dict] | None:
    """
    Finds a jutsu in the JUTSU_LIBRARY by its hand sign combination.
    Returns (jutsu_key, jutsu_dict).
    """
    combo_str = ' '.join(signs)
    for key, jutsu in JUTSU_LIBRARY.items():
        if ' '.join(jutsu['signs']) == combo_str:
            return key, jutsu
    return None

def get_hand_signs_for_jutsu(jutsu_key: str) -> list[str]:
    """Gets the hand signs for a given jutsu key."""
    jutsu = JUTSU_LIBRARY.get(jutsu_key)
    return jutsu['signs'] if jutsu else []

def validate_hand_signs(signs: list[str]) -> bool:
    """Checks if all provided signs are valid."""
    return all(sign in HAND_SIGNS for sign in signs)
