# naruto_bot/handlers/jutsu_handlers.py
import logging
import json
from datetime import datetime
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from telegram.constants import ParseMode
from ..models import get_player
from ..game_data import JUTSU_LIBRARY, HAND_SIGNS
from ..services import validate_hand_signs, get_jutsu_by_signs
from ..database import get_db_connection
from ..animations import animate_jutsu_discovery

logger = logging.getLogger(__name__)

async def jutsus_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the /jutsus command, listing known jutsus."""
    player = get_player(update.effective_user.id)
    if not player:
        await update.message.reply_text("You must /start your journey first.")
        return
        
    if not player.known_jutsus:
        await update.message.reply_text("You don't know any jutsus! Learn some from your sensei or /combine hand signs.")
        return
        
    message = f"**Your Known Jutsus ({len(player.known_jutsus)}/25)**\n\n"
    for jutsu_key in player.known_jutsus:
        jutsu = JUTSU_LIBRARY.get(jutsu_key)
        if jutsu:
            message += (
                f"**{jutsu['name']}** [{jutsu['element'].capitalize()}]\n"
                f"  (Power: {jutsu['power']}, Cost: {jutsu['chakra_cost']})\n"
                f"  Signs: `{' '.join(jutsu['signs'])}`\n"
            )
    
    await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN)

async def combine_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handles the /combine command for jutsu discovery (Prompt 9).
    """
    player = get_player(update.effective_user.id)
    if not player:
        await update.message.reply_text("You must /start your journey first.")
        return
        
    if not context.args:
        await update.message.reply_text(
            "You must provide a combination of hand signs.\n"
            f"Usage: `/combine tiger snake bird`\n\n"
            f"Available signs: `{', '.join(HAND_SIGNS)}`",
            parse_mode=ParseMode.MARKDOWN
        )
        return
        
    signs = [sign.lower() for sign in context.args]
    
    # Validate signs
    if not validate_hand_signs(signs):
        await update.message.reply_text(
            f"Invalid hand sign(s) detected.\n"
            f"Available signs: `{', '.join(HAND_SIGNS)}`",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    # Check if this combination exists
    combo_str = ' '.join(signs)
    jutsu_match = get_jutsu_by_signs(signs)
    
    if not jutsu_match:
        await update.message.reply_text(
            f"You perform the signs: `{combo_str}`...\n"
            "But nothing happens. It seems this combination is incorrect."
        )
        return
        
    jutsu_key, jutsu_data = jutsu_match
    
    # Check if player is high enough level
    if player.level < jutsu_data['level_required']:
        await update.message.reply_text(
            f"You perform the signs: `{combo_str}`...\n"
            "You feel a surge of chakra, but you are not yet skilled enough to control this jutsu. "
            f"(Requires Level {jutsu_data['level_required']})"
        )
        return

    # Check if they already discovered this combo
    if combo_str in player.discovered_combinations:
        await update.message.reply_text(
            f"You already know this combination.\n"
            f"It's for **{jutsu_data['name']}**."
        )
        # Ensure they have the jutsu in their list
        if player.add_jutsu(jutsu_key):
            player.save()
        return

    # --- NEW DISCOVERY ---
    
    # Add to player's lists
    player.add_discovered_combination(combo_str)
    player.add_jutsu(jutsu_key)
    player.save()
    
    # Log discovery globally (Prompt 16)
    _log_jutsu_discovery(combo_str, jutsu_key, player)
    
    # Play discovery animation (Prompt 10)
    message = await update.message.reply_text("You begin to try a new combination...")
    
    # We must pass a *copy* of the jutsu_data dict
    anim_data = jutsu_data.copy()
    anim_data['signs'] = signs # Use the signs the player entered
    
    try:
        await animate_jutsu_discovery(message, player.username, anim_data)
    except Exception as e:
        logger.error(f"Jutsu discovery animation failed: {e}")
        await message.edit_text(
            f"🌟 **NEW JUTSU DISCOVERED!**\n"
            f"You have learned **{jutsu_data['name']}**!",
            parse_mode=ParseMode.MARKDOWN
        )

def _log_jutsu_discovery(combo_str: str, jutsu_key: str, player: Player):
    """Logs a new jutsu discovery to the database."""
    sql = """
    INSERT INTO jutsu_discoveries (combination, jutsu_name, discovered_by_id, discovered_by_name)
    VALUES (?, ?, ?, ?)
    """
    try:
        with get_db_connection() as conn:
            conn.execute(sql, (combo_str, jutsu_key, player.user_id, player.username))
            conn.commit()
        logger.info(f"New jutsu discovery logged: {player.username} found {jutsu_key}")
    except sqlite3.IntegrityError:
        logger.warning(f"Attempted to log discovery for {combo_str}, but it already exists.")
    except sqlite3.Error as e:
        logger.error(f"Failed to log jutsu discovery: {e}")

def register_jutsu_handlers(application: Application):
    application.add_handler(CommandHandler('jutsus', jutsus_command))
    application.add_handler(CommandHandler('combine', combine_command))
