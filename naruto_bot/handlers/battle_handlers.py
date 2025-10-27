import logging
import uuid
import asyncio
import json
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Any
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters
)
from telegram.constants import ParseMode
from ..models import get_player, Player
from ..cache import cache_manager
from ..config import config
from ..battle import Battle, battle_animation_flow
from ..services import get_jutsu_by_name
from ..database import get_db_connection
from ..game_data import JUTSU_LIBRARY

logger = logging.getLogger(__name__)

# --- Battle Initiation ---

async def battle_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Initiates a battle by replying to a user's message.
    """
    user_id = update.effective_user.id
    if not user_id: return
    logger.debug(f"Received /battle command from {user_id}")
    # --- FIX: Added await ---
    challenger = await get_player(user_id)
    if not challenger:
        await update.message.reply_text("You must /start your journey first.")
        return

    # Check Challenger Status
    if challenger.current_mission:
        await update.message.reply_text(f"You cannot battle while busy: {challenger.current_mission}.")
        return

    # Check if already in battle
    if await cache_manager.is_in_battle(challenger.user_id):
        await update.message.reply_text("You are already in a battle!")
        return

    # Check cooldown (method is synchronous)
    cooldown, remaining = challenger.is_on_cooldown('battle')
    if cooldown:
        await update.message.reply_text(f"You need rest after your last battle. Wait {remaining}.")
        return

    if challenger.current_hp <= 0:
        await update.message.reply_text("You have 0 HP! Regenerate before fighting.")
        return

    # --- Find Opponent ---
    if not update.message.reply_to_message or not update.message.reply_to_message.from_user:
        await update.message.reply_text("To challenge someone, **reply** to one of their messages with `/battle`.")
        return

    opponent_user = update.message.reply_to_message.from_user
    if opponent_user.id == challenger.user_id:
        await update.message.reply_text("You cannot challenge yourself to a duel.")
        return
    if opponent_user.is_bot:
        await update.message.reply_text("You cannot challenge bots (for now!).")
        return

    # --- FIX: Added await ---
    opponent = await get_player(opponent_user.id)
    opponent_name = opponent_user.first_name or f"User {opponent_user.id}"
    if not opponent:
        await update.message.reply_text(f"{opponent_name} hasn't started their ninja journey yet.")
        return

    # --- Check Opponent Status ---
    if opponent.current_mission:
        await update.message.reply_text(f"{opponent.username} is busy ({opponent.current_mission}) and cannot battle now.")
        return

    if await cache_manager.is_in_battle(opponent.user_id):
        await update.message.reply_text(f"{opponent.username} is already in another intense battle.")
        return

    if opponent.current_hp <= 0:
        await update.message.reply_text(f"{opponent.username} has 0 HP and cannot fight right now.")
        return

    # --- Start Battle ---
    logger.info(f"Battle initiated: {challenger.username} vs {opponent.username} (IDs: {challenger.user_id} vs {opponent.user_id})")

    battle_id = f"battle_{uuid.uuid4()}"
    try:
        battle = Battle(challenger, opponent, battle_id)
        battle.chat_id = update.message.chat_id
    except Exception as e:
        logger.error(f"Failed to initialize Battle object: {e}", exc_info=True)
        await update.message.reply_text("An error occurred starting the battle setup.")
        return

    logger.debug(f"Battle object created with ID: {battle_id}")

    # Set locks and cache mappings (await async calls)
    try:
        await cache_manager.set_battle_lock(challenger.user_id, opponent.user_id)
        await cache_manager.set_battle_lock(opponent.user_id, challenger.user_id)
        await cache_manager.set_data("battle_state", battle_id, battle, ttl=config.BATTLE_CACHE_TTL)
        await cache_manager.set_data("user_battle_id", str(challenger.user_id), battle_id, ttl=config.BATTLE_CACHE_TTL)
        await cache_manager.set_data("user_battle_id", str(opponent.user_id), battle_id, ttl=config.BATTLE_CACHE_TTL)
        logger.debug(f"Battle state and user mappings cached for battle {battle_id}.")
    except Exception as cache_e:
         logger.error(f"Failed to set up battle cache for {battle_id}: {cache_e}", exc_info=True)
         await update.message.reply_text("Failed to initialize battle state. Please try again.")
         await _cleanup_battle_cache(battle_id, challenger.user_id, opponent.user_id)
         return

    # --- Send Initial Battle Message ---
    try:
        turn_player_id = battle.turn
        # --- FIX: Added await ---
        turn_player_obj = await get_player(turn_player_id)
        if not turn_player_obj: raise ValueError(f"Could not load player data for starting turn: {turn_player_id}")

        logger.debug(f"First turn: {turn_player_obj.username}. Building keyboard.")
        keyboard = build_jutsu_keyboard(turn_player_obj)
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)

        battle_text = battle.get_battle_state_text()
        if not battle_text: raise ValueError("get_battle_state_text returned empty.")

        logger.debug(f"Sending initial battle message for {battle_id} to chat {battle.chat_id}")
        message = await update.message.reply_text(
            text=battle_text,
            reply_markup=reply_markup,
            parse_mode=ParseMode.MARKDOWN
        )

        battle.battle_message_id = message.message_id
        await cache_manager.set_data("battle_state", battle_id, battle, ttl=config.BATTLE_CACHE_TTL)
        logger.debug(f"Battle message ID {message.message_id} saved for {battle_id}.")

        await context.bot.send_message(
             chat_id=battle.chat_id,
             text=f"⚔️ Battle Start! ⚔️\nIt's {turn_player_obj.username}'s turn!"
        )

    except Exception as e:
        logger.error(f"Error sending initial battle message for {battle_id}: {e}", exc_info=True)
        await update.message.reply_text("An error occurred displaying the battle start message.")
        await _cleanup_battle_cache(battle_id, challenger.user_id, opponent.user_id)


# --- Handling Turns (/use) ---

async def use_jutsu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles jutsu usage via /use command or ReplyKeyboard press."""
    user = update.effective_user
    if not user: return
    logger.debug(f"Received /use handler trigger from {user.id}")

    # --- FIX: Added await ---
    player = await get_player(user.id)
    if not player:
         await update.message.reply_text("Cannot find your player data.", reply_markup=ReplyKeyboardRemove())
         return

    # Check if player is in battle
    battle_id = await cache_manager.get_data("user_battle_id", str(user.id))
    if not battle_id:
        await update.message.reply_text("You are not currently in a battle.", reply_markup=ReplyKeyboardRemove())
        return

    # Retrieve battle state
    battle: Optional[Battle] = await cache_manager.get_data("battle_state", battle_id)
    if not battle or not isinstance(battle, Battle):
        logger.warning(f"Battle state {battle_id} missing/invalid for player {user.id} using jutsu.")
        await _cleanup_battle_cache(battle_id, user.id, None)
        await update.message.reply_text("Your battle data expired or was lost. The battle ends.", reply_markup=ReplyKeyboardRemove())
        return

    # Check turn
    if battle.turn != user.id:
        await update.message.reply_text("Patience, shinobi! It's not your turn.")
        return

    # Parse jutsu name
    jutsu_name_input = ""
    if update.message.text.startswith('/use '):
         jutsu_name_input = update.message.text[5:].strip()
    elif context.args:
        jutsu_name_input = ' '.join(context.args)

    if not jutsu_name_input:
         await update.message.reply_text("Which jutsu will you use? (Select from keyboard)")
         return

    # Find the jutsu
    jutsu_key, jutsu_data = get_jutsu_by_name(jutsu_name_input)
    if not jutsu_key or not jutsu_data:
        await update.message.reply_text(f"Unknown jutsu: '{jutsu_name_input}'.")
        return

    # Check if known
    if jutsu_key not in player.known_jutsus:
        await update.message.reply_text(f"You haven't mastered {jutsu_data['name']} yet!")
        return

    # Check Chakra cost
    chakra_cost = jutsu_data.get('chakra_cost', 0)
    if player.current_chakra < chakra_cost:
        await update.message.reply_text(f"Not enough chakra! {jutsu_data['name']} needs {chakra_cost}, you have {player.current_chakra}.")
        return

    # --- Execute Turn ---
    logger.info(f"Battle {battle_id}: Player {player.username} uses {jutsu_data['name']}")

    # Get opponent object
    opponent_id = await cache_manager.get_battle_opponent(user.id)
    if not opponent_id:
         logger.error(f"Opponent ID missing in cache for player {user.id}, battle {battle_id}.")
         await _end_battle(context, battle, "Internal error: Opponent missing.", winner_id=None)
         return
    # --- FIX: Added await ---
    opponent = await get_player(opponent_id)
    if not opponent:
         logger.error(f"Opponent player data (ID: {opponent_id}) missing for battle {battle_id}.")
         await _end_battle(context, battle, "Internal error: Opponent data missing.", winner_id=user.id)
         return

    # Deduct chakra and save player state
    player.current_chakra -= chakra_cost
    player.mark_modified()
    player.save()

    # Update chakra in the cached battle state
    battle.update_player_resource(user.id, 'current_chakra', player.current_chakra)

    # Message editor helper class
    class BattleMessageEditor:
        def __init__(self, bot, chat_id, message_id):
            self.bot = bot
            self.chat_id = chat_id
            self.message_id = message_id
        async def edit_text(self, text, parse_mode=ParseMode.MARKDOWN, reply_markup=None):
            if not self.message_id: return
            try:
                await self.bot.edit_message_text(
                    chat_id=self.chat_id, message_id=self.message_id,
                    text=text, parse_mode=parse_mode, reply_markup=reply_markup
                )
            except Exception as e:
                logger.warning(f"Failed to edit battle message {self.message_id}: {e}")

    battle_message = BattleMessageEditor(context.bot, battle.chat_id, battle.battle_message_id)

    # Call battle logic/animation
    winner_id = None
    turn_log_msg = "Error during turn execution."
    try:
        winner_id, turn_log_msg = await battle_animation_flow(
            message_editor=battle_message, attacker=player, defender=opponent,
            battle_state=battle, jutsu_key=jutsu_key
        )
    except Exception as e:
        logger.error(f"Error during battle_animation_flow for battle {battle_id}: {e}", exc_info=True)
        await context.bot.send_message(battle.chat_id, "An error occurred during the turn execution.")
        await _end_battle(context, battle, "Error during turn execution.", winner_id=None)
        return

    battle.log.append(f"Turn {battle.turn_count}: {player.username} used {jutsu_data['name']}. {turn_log_msg}")

    # Check for Winner
    if winner_id:
        logger.info(f"Battle {battle_id} concluded. Winner: {winner_id}")
        await battle_message.edit_text(battle.get_battle_state_text(), parse_mode=ParseMode.MARKDOWN)

        # --- FIX: Added await ---
        winner_player = await get_player(winner_id)
        winner_name = winner_player.username if winner_player else f"Player {winner_id}"

        await context.bot.send_message(
            battle.chat_id,
            f"🎉 **BATTLE OVER!** 🎉\n\n**{winner_name} is victorious!**\n\n{turn_log_msg}",
            reply_markup=ReplyKeyboardRemove(),
            parse_mode=ParseMode.MARKDOWN
        )
        await _end_battle(context, battle, f"{winner_name} won.", winner_id=winner_id)
        return

    # Switch Turns
    battle.switch_turn()
    next_turn_player_id = battle.turn

    await cache_manager.set_data("battle_state", battle_id, battle, ttl=config.BATTLE_CACHE_TTL)

    # Get next player object for keyboard
    # --- FIX: Added await ---
    next_player = await get_player(next_turn_player_id)
    if not next_player:
         logger.error(f"Could not load next player {next_turn_player_id} in battle {battle_id}.")
         await _end_battle(context, battle, "Internal error loading next player.", winner_id=None)
         return

    keyboard = build_jutsu_keyboard(next_player)
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)

    await battle_message.edit_text(battle.get_battle_state_text(), parse_mode=ParseMode.MARKDOWN)

    await context.bot.send_message(
        battle.chat_id,
        f"It's {next_player.username}'s turn!",
        reply_markup=reply_markup
    )


async def flee_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Allows a player to flee a battle."""
    user_id = update.effective_user.id
    if not user_id: return

    battle_id = await cache_manager.get_data("user_battle_id", str(user_id))
    if not battle_id:
        await update.message.reply_text("You are not in a battle.", reply_markup=ReplyKeyboardRemove())
        return

    battle = await cache_manager.get_data("battle_state", battle_id)
    if not battle or not isinstance(battle, Battle):
        await _cleanup_battle_cache(battle_id, user_id, None)
        await update.message.reply_text("Your battle data was not found.", reply_markup=ReplyKeyboardRemove())
        return

    winner_id = battle.player2_id if battle.player1_id == user_id else battle.player1_id
    fleeing_player_name = update.effective_user.first_name

    # --- FIX: Added await ---
    winner_player = await get_player(winner_id)
    winner_name = winner_player.username if winner_player else f"Player {winner_id}"

    logger.info(f"Battle {battle.battle_id}: Player {user_id} ({fleeing_player_name}) fled. Winner: {winner_id} ({winner_name}).")

    await context.bot.send_message(
        battle.chat_id,
        f"🏃 **{fleeing_player_name} has fled the battle!**\n\n"
        f"The winner is {winner_name}!",
        reply_markup=ReplyKeyboardRemove(),
        parse_mode=ParseMode.MARKDOWN
    )

    battle.log.append(f"{fleeing_player_name} fled.")
    await _end_battle(context, battle, f"{winner_name} won by default.", winner_id=winner_id)

# --- Battle Cleanup and Logging (Minimal changes needed) ---

async def _cleanup_battle_cache(battle_id: str, player1_id: Optional[int], player2_id: Optional[int]):
     """Removes battle state and user mappings from cache."""
     if not battle_id: return
     logger.debug(f"Cleaning up cache entries for battle {battle_id}")
     tasks = [cache_manager.delete_data("battle_state", battle_id)]
     if player1_id:
          tasks.append(cache_manager.delete_data("user_battle_id", str(player1_id)))
          tasks.append(cache_manager.delete_data("battle_lock", str(player1_id)))
     if player2_id:
          tasks.append(cache_manager.delete_data("user_battle_id", str(player2_id)))
          tasks.append(cache_manager.delete_data("battle_lock", str(player2_id)))
     await asyncio.gather(*tasks)
     logger.debug(f"Cache cleanup complete for battle {battle_id}")


async def _end_battle(context: ContextTypes.DEFAULT_TYPE, battle: Battle, end_reason: str, winner_id: Optional[int]):
    """Cleans up cache, updates player stats, sends messages, and logs history."""

    if not isinstance(battle, Battle) or not battle.battle_id:
         logger.error(f"_end_battle called with invalid Battle object: {battle}")
         return

    p1_id = battle.player1_id
    p2_id = battle.player2_id
    loser_id = None

    logger.info(f"Ending battle {battle.battle_id}. Reason: '{end_reason}'. Winner: {winner_id}")

    if winner_id == p1_id: loser_id = p2_id
    elif winner_id == p2_id: loser_id = p1_id

    # Clean up cache FIRST
    await _cleanup_battle_cache(battle.battle_id, p1_id, p2_id)

    # Update Player Stats & Send DMs
    if winner_id and loser_id:
        try:
            # --- FIX: Added await ---
            winner = await get_player(winner_id)
            # --- FIX: Added await ---
            loser = await get_player(loser_id)

            if winner and loser:
                level_diff = max(0, loser.level - winner.level)
                exp_gain = max(10, (loser.level * 10) + 25 + (level_diff * 5))
                ryo_gain = max(20, (loser.level * 5) + 50 + (level_diff * 10))

                logger.debug(f"Battle {battle.battle_id}: Winner {winner_id} gains {exp_gain} EXP, {ryo_gain} Ryo.")

                # Update winner
                level_up_msg, exp_msg = winner.add_exp(exp_gain)
                winner.ryo += ryo_gain
                winner.wins += 1
                winner.mark_modified()
                winner.set_cooldown('battle', 60)
                winner.save()

                # Update loser
                loser.losses += 1
                loser.mark_modified()
                loser.set_cooldown('battle', 30)
                loser.save()

                # Send result messages via DM
                try:
                    await context.bot.send_message(
                        winner_id,
                        f"**VICTORY!**\n"
                        f"You defeated {loser.username}!\n"
                        f"You earned {ryo_gain} Ryo 💰.\n{exp_msg}"
                        f"{('\n\n'+level_up_msg) if level_up_msg else ''}",
                        parse_mode=ParseMode.MARKDOWN
                    )
                except Exception as dm_err:
                     logger.warning(f"Could not send victory DM to winner {winner_id}: {dm_err}")

                try:
                    await context.bot.send_message(
                        loser_id,
                        f"**DEFEAT...**\n"
                        f"You were defeated by {winner.username}.",
                        parse_mode=ParseMode.MARKDOWN
                    )
                except Exception as dm_err:
                     logger.warning(f"Could not send defeat DM to loser {loser_id}: {dm_err}")

                _log_battle_history(p1_id, p2_id, battle.log, winner_id=winner_id)

            else:
                 logger.error(f"Could not load winner ({winner_id}) or loser ({loser_id}) object for battle {battle.battle_id}.")

        except Exception as e:
            logger.error(f"Error updating player stats after battle {battle.battle_id}: {e}", exc_info=True)
            try:
                 await context.bot.send_message(p1_id, "An error occurred updating stats after the battle.", disable_notification=True)
                 await context.bot.send_message(p2_id, "An error occurred updating stats after the battle.", disable_notification=True)
            except: pass

    elif winner_id is None:
         logger.info(f"Battle {battle.battle_id} ended without a clear winner. Reason: {end_reason}.")
         try:
              await context.bot.send_message(battle.chat_id, f"The battle ended inconclusively ({end_reason}).", reply_markup=ReplyKeyboardRemove())
         except Exception as msg_err:
              logger.warning(f"Could not send inconclusive battle message for {battle.battle_id}: {msg_err}")

         _log_battle_history(p1_id, p2_id, battle.log, winner_id=None)


def _log_battle_history(player1_id: int, player2_id: int, log: list[str], winner_id: Optional[int]):
    """Saves the battle log to the database (synchronous)."""
    try:
        log_json = json.dumps(log)
    except TypeError:
        logger.error("Failed to serialize battle log to JSON. Log content might be invalid.")
        log_json = json.dumps(["Error serializing log."])

    sql = """
    INSERT INTO battle_history (player1_id, player2_id, winner_id, battle_log, fought_at)
    VALUES (?, ?, ?, ?, ?)
    """
    now_iso = datetime.now(timezone.utc).isoformat()

    try:
        with get_db_connection() as conn:
            conn.execute(sql, (player1_id, player2_id, winner_id, log_json, now_iso))
            conn.commit()
        logger.info(f"Battle history logged: P1={player1_id}, P2={player2_id}, Winner={winner_id}")
    except sqlite3.Error as e:
        logger.error(f"Failed to log battle history to DB: {e}", exc_info=True)
    except Exception as e:
         logger.error(f"Unexpected error logging battle history: {e}", exc_info=True)


def build_jutsu_keyboard(player: Player) -> list[list[str]]:
    """Creates a ReplyKeyboardMarkup list of lists for usable jutsus."""
    keyboard_buttons = []
    row = []

    valid_jutsu_keys = [
        key for key in player.known_jutsus
        if key in JUTSU_LIBRARY and isinstance(JUTSU_LIBRARY[key], dict)
    ]

    for jutsu_key in valid_jutsu_keys:
        jutsu = JUTSU_LIBRARY[jutsu_key]
        if jutsu.get('power', 0) > 0 or 'effect' in jutsu:
            jutsu_name = jutsu.get('name', jutsu_key)
            row.append(f"/use {jutsu_name}")
            if len(row) == 2:
                keyboard_buttons.append(row)
                row = []

    if row:
        keyboard_buttons.append(row)

    keyboard_buttons.append(["/flee"])

    if not valid_jutsu_keys or not any(JUTSU_LIBRARY[key].get('power', 0) > 0 or 'effect' in JUTSU_LIBRARY[key] for key in valid_jutsu_keys):
        keyboard_buttons.insert(0, ["No usable battle jutsus known!"])

    return keyboard_buttons


def register_battle_handlers(application: Application):
    logger.debug("Registering battle handlers...")
    application.add_handler(CommandHandler('battle', battle_command))
    application.add_handler(CommandHandler('use', use_jutsu_handler))
    application.add_handler(CommandHandler('flee', flee_command))
    logger.debug("Battle handlers registered.")
