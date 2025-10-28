# naruto_bot/handlers/jutsu_handlers.py
import logging
import json
import sqlite3
import asyncio
from datetime import datetime, timezone
from typing import Optional, List, Any
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from telegram.constants import ParseMode
from ..models import get_player, Player
from ..game_data import JUTSU_LIBRARY, HAND_SIGNS
from ..services import validate_hand_signs, get_jutsu_by_signs
from ..database import get_db_connection
from ..animations import animate_jutsu_discovery

logger = logging.getLogger(__name__)


async def jutsus_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the /jutsus command, listing known jutsus."""
    user_id = update.effective_user.id
    if not user_id: 
        return
    logger.debug(f"Received /jutsus command from {user_id}")
    
    player = await get_player(user_id)
    if not player:
        await update.message.reply_text("You must /start your journey first.")
        return

    if not player.known_jutsus:
        await update.message.reply_text("You don't know any jutsus yet! Try `/combine` to discover some.", parse_mode=ParseMode.MARKDOWN)
        return

    message = f"**Your Known Jutsus ({len(player.known_jutsus)}/25)**\n\n"
    found_any_valid = False
    for jutsu_key in player.known_jutsus:
        jutsu = JUTSU_LIBRARY.get(jutsu_key)
        if jutsu and isinstance(jutsu, dict):
            name = jutsu.get('name', jutsu_key)
            element = jutsu.get('element', 'Unknown').capitalize()
            power = jutsu.get('power', '?')
            cost = jutsu.get('chakra_cost', '?')
            signs = jutsu.get('signs', [])

            signs_str = ' '.join(signs) if isinstance(signs, (list, tuple)) else 'Error'

            message += (
                f"**{name}** [{element}]\n"
                f"  (Power: {power}, Cost: {cost})\n"
                f"  Signs: `{signs_str}`\n\n"
            )
            found_any_valid = True
        else:
            logger.warning(f"Jutsu key '{jutsu_key}' in player {user_id}'s list is missing or invalid in JUTSU_LIBRARY.")
            message += f"- {jutsu_key} (Data Error)\n"

    if not found_any_valid:
         message = "You know some techniques, but their data seems corrupted."

    try:
        await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN)
        logger.debug(f"Jutsu list sent to {user_id}")
    except Exception as e:
         logger.error(f"Failed to send jutsu list to {user_id}: {e}", exc_info=True)


async def combine_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the /combine command for jutsu discovery."""
    user_id = update.effective_user.id
    if not user_id: 
        return
    logger.debug(f"Received /combine command from {user_id} with args: {context.args}")
    
    player = await get_player(user_id)
    if not player:
        await update.message.reply_text("You must /start your journey first.")
        return

    if not context.args:
        await update.message.reply_text(
            "You must provide a combination of hand signs.\n"
            f"Usage: `/combine [sign1] [sign2] ...`\n\n"
            f"Available signs: `{', '.join(HAND_SIGNS)}`",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    signs = [sign.lower() for sign in context.args]

    # Validate signs
    if not validate_hand_signs(signs):
        invalid_signs = [s for s in signs if s not in HAND_SIGNS]
        await update.message.reply_text(
            f"Invalid hand sign(s) detected: `{', '.join(invalid_signs)}`.\n"
            f"Available signs: `{', '.join(HAND_SIGNS)}`",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    # Check if this combination yields a known jutsu
    combo_str = ' '.join(signs)
    jutsu_match = get_jutsu_by_signs(signs)

    if not jutsu_match:
        await update.message.reply_text(
            f"You perform the signs: `{combo_str}`...\n"
            "But nothing happens. It seems this combination yields no technique.",
            parse_mode=ParseMode.MARKDOWN
        )
        logger.debug(f"Combination '{combo_str}' by {user_id} yielded no jutsu.")
        return

    jutsu_key, jutsu_data = jutsu_match

    if not isinstance(jutsu_data, dict) or not all(k in jutsu_data for k in ['name', 'level_required', 'power', 'chakra_cost', 'element']):
         logger.error(f"JUTSU_LIBRARY data for key '{jutsu_key}' (from combo '{combo_str}') is incomplete or invalid.")
         await update.message.reply_text("An error occurred while retrieving data for this jutsu combination.")
         return

    logger.debug(f"Combination '{combo_str}' matches jutsu '{jutsu_key}' ({jutsu_data['name']})")

    # Check level requirement
    if player.level < jutsu_data['level_required']:
        await update.message.reply_text(
            f"You perform the signs: `{combo_str}`...\n"
            "You feel a resonance, but your control isn't refined enough for this technique yet. "
            f"(Requires Level {jutsu_data['level_required']})",
            parse_mode=ParseMode.MARKDOWN
        )
        logger.debug(f"Player {user_id} (Lvl {player.level}) failed level requirement for {jutsu_key} (Req Lvl {jutsu_data['level_required']})")
        return

    # Check if combo string already discovered
    if combo_str in player.discovered_combinations:
        await update.message.reply_text(
            f"You recognize this sequence: `{combo_str}`.\n"
            f"It forms the **{jutsu_data['name']}** jutsu.",
            parse_mode=ParseMode.MARKDOWN
        )
        if player.add_jutsu(jutsu_key):
            player.save()
        logger.debug(f"Player {user_id} tried already discovered combination '{combo_str}'.")
        return

    # --- NEW DISCOVERY ---
    logger.info(f"NEW DISCOVERY by {user_id}! Combination '{combo_str}' -> Jutsu '{jutsu_key}' ({jutsu_data['name']})")

    # Add to player's lists and save
    player.add_discovered_combination(combo_str)
    player.add_jutsu(jutsu_key)
    player.save()

    # Log discovery globally (synchronous)
    _log_jutsu_discovery(combo_str, jutsu_key, player)

    # Play discovery animation
    message = None
    try:
        message = await update.message.reply_text("You weave together an unfamiliar sequence of hand signs...")

        anim_data = jutsu_data.copy()
        anim_data['signs'] = signs
        anim_data['name'] = jutsu_data['name']

        await animate_jutsu_discovery(message, player.username, anim_data)

    except Exception as e:
        logger.error(f"Jutsu discovery animation failed for {user_id}: {e}", exc_info=True)
        fallback_text = (
            f"🌟 **NEW JUTSU DISCOVERED!**\n"
            f"Through experimentation, you have learned **{jutsu_data.get('name', jutsu_key)}**!"
        )
        try:
            if message:
                 await message.edit_text(fallback_text, parse_mode=ParseMode.MARKDOWN)
            else:
                 await update.message.reply_text(fallback_text, parse_mode=ParseMode.MARKDOWN)
        except Exception as fallback_e:
             logger.error(f"Failed to send fallback discovery message for {user_id}: {fallback_e}")
             await context.bot.send_message(user_id, fallback_text, parse_mode=ParseMode.MARKDOWN)


def _log_jutsu_discovery(combo_str: str, jutsu_key: str, player: Player):
    """Logs a new jutsu discovery to the database (synchronous)."""
    sql = """
    INSERT INTO jutsu_discoveries (combination, jutsu_name, discovered_by_id, discovered_by_name, discovered_at)
    VALUES (?, ?, ?, ?, ?)
    ON CONFLICT(combination) DO NOTHING;
    """
    now_iso = datetime.now(timezone.utc).isoformat()
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, (combo_str, jutsu_key, player.user_id, player.username, now_iso))
            conn.commit()
            if cursor.rowcount > 0:
                 logger.info(f"New jutsu discovery logged to DB: {player.username} found {jutsu_key} via '{combo_str}'")
    except sqlite3.Error as e:
        logger.error(f"Failed to log jutsu discovery to DB: {e}", exc_info=True)
    except Exception as e:
         logger.error(f"Unexpected error logging jutsu discovery: {e}", exc_info=True)


def register_jutsu_handlers(application: Application):
    logger.debug("Registering jutsu handlers...")
    application.add_handler(CommandHandler('jutsus', jutsus_command))
    application.add_handler(CommandHandler('combine', combine_command))
    logger.debug("Jutsu handlers registered.")
