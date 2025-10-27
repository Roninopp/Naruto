# naruto_bot/handlers/battle_handlers.py
import logging
import uuid
import asyncio
from datetime import datetime, timedelta
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
from ..services import get_jutsu_by_name, safe_animation
from ..database import get_db_connection

logger = logging.getLogger(__name__)

async def battle_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Initiates a battle by replying to a user's message.
    """
    challenger = get_player(update.effective_user.id)
    if not challenger:
        await update.message.reply_text("You must /start your journey first.")
        return

    # --- Check Challenger Status ---
    if challenger.current_mission:
        await update.message.reply_text("You cannot battle while on a mission or training.")
        return
    if cache_manager.is_in_battle(challenger.user_id):
        await update.message.reply_text("You are already in a battle!")
        return
    
    cooldown, remaining = challenger.is_on_cooldown('battle')
    if cooldown:
        await update.message.reply_text(f"You are tired from your last battle. You can fight again in {remaining}.")
        return
        
    if challenger.current_hp <= 0:
        await update.message.reply_text("You have 0 HP! Rest and regenerate before fighting.")
        return

    # --- Find Opponent ---
    if not update.message.reply_to_message:
        await update.message.reply_text("To challenge someone, you must **reply** to one of their messages with `/battle`.")
        return
        
    opponent_user = update.message.reply_to_message.from_user
    if opponent_user.id == challenger.user_id:
        await update.message.reply_text("You cannot challenge yourself.")
        return
    if opponent_user.is_bot:
        await update.message.reply_text("You cannot challenge a bot.")
        return
        
    opponent = get_player(opponent_user.id)
    if not opponent:
        await update.message.reply_text(f"{opponent_user.first_name} has not started their ninja journey yet.")
        return

    # --- Check Opponent Status ---
    if opponent.current_mission:
        await update.message.reply_text(f"{opponent.username} is busy with a mission and cannot battle.")
        return
    if cache_manager.is_in_battle(opponent.user_id):
        await update.message.reply_text(f"{opponent.username} is already in another battle.")
        return
    if opponent.current_hp <= 0:
        await update.message.reply_text(f"{opponent.username} has 0 HP and cannot fight.")
        return

    # --- Start Battle ---
    logger.info(f"Battle initiated: {challenger.username} vs {opponent.username}")
    
    # Create and cache battle state
    battle_id = f"battle_{uuid.uuid4()}"
    battle = Battle(challenger, opponent, battle_id)
    battle.chat_id = update.message.chat_id
    
    # Set battle locks for both players
    # This key tracks *who* they are fighting
    cache_manager.set_battle_lock(challenger.user_id, opponent.user_id)
    cache_manager.set_battle_lock(opponent.user_id, challenger.user_id)
    
    # This key tracks the battle *state*
    cache_manager.set_data("battle_state", battle_id, battle, ttl=config.BATTLE_CACHE_TTL)
    
    # Set helper keys to find the battle_id from a user_id
    cache_manager.set_data("user_battle_id", challenger.user_id, battle_id, ttl=config.BATTLE_CACHE_TTL)
    cache_manager.set_data("user_battle_id", opponent.user_id, battle_id, ttl=config.BATTLE_CACHE_TTL)

    # --- Send Initial Battle Message ---
    # Create dynamic keyboard for the first turn
    turn_player_id = battle.turn
    turn_player = challenger if turn_player_id == challenger.user_id else opponent
    
    keyboard = build_jutsu_keyboard(turn_player)
    
    battle_text = battle.get_battle_state_text()
    message = await update.message.reply_text(
        battle_text,
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True),
        parse_mode=ParseMode.MARKDOWN
    )
    
    # Save the message ID to the battle state
    battle.battle_message_id = message.message_id
    cache_manager.set_data("battle_state", battle_id, battle, ttl=config.BATTLE_CACHE_TTL)
    
    await update.message.reply_text(f"It's {turn_player.username}'s turn!")

async def use_jutsu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handles the /use command during a battle.
    """
    user = update.effective_user
    player = get_player(user.id)
    
    # 1. Check if player is in battle
    battle_id = cache_manager.get_data("user_battle_id", user.id)
    if not battle_id:
        await update.message.reply_text("This command can only be used in a battle.", reply_markup=ReplyKeyboardRemove())
        return

    battle: Battle = cache_manager.get_data("battle_state", battle_id)
    if not battle:
        logger.warning(f"Player {user.id} has battle_id {battle_id} but battle state is not in cache.")
        await _end_battle(context, battle_id, user.id, None, "Battle state expired.")
        return
        
    # 2. Check if it's the player's turn
    if battle.turn != user.id:
        await update.message.reply_text("It's not your turn!")
        return
        
    # 3. Parse and validate the jutsu
    if not context.args:
        await update.message.reply_text("Usage: `/use [jutsu_name]`")
        return
        
    jutsu_name = ' '.join(context.args)
    jutsu_key = next((key for key, val in JUTSU_LIBRARY.items() if val['name'].lower() == jutsu_name.lower()), None)
    
    if not jutsu_key:
        jutsu_key = jutsu_name.lower()
        if jutsu_key not in JUTSU_LIBRARY:
            await update.message.reply_text("Unknown jutsu.")
            return

    if jutsu_key not in player.known_jutsus:
        await update.message.reply_text("You don't know that jutsu!")
        return
        
    jutsu = JUTSU_LIBRARY[jutsu_key]
    
    # 4. Check Chakra
    if player.current_chakra < jutsu['chakra_cost']:
        await update.message.reply_text(f"Not enough chakra! {jutsu['name']} costs {jutsu['chakra_cost']}, you have {player.current_chakra}.")
        return

    # --- All checks passed, execute turn ---
    
    # Get opponent
    opponent_id = cache_manager.get_battle_opponent(user.id)
    opponent = get_player(opponent_id)
    
    # Deduct chakra (from the *real* player object)
    player.current_chakra -= jutsu['chakra_cost']
    player.save()
    
    # Update chakra in the battle state
    battle.get_player_data(user.id)['current_chakra'] = player.current_chakra
    
    # Get the battle message
    try:
        # Create a dummy message object to edit
        class BattleMessage:
            chat_id = battle.chat_id
            message_id = battle.battle_message_id
            async def edit_text(self, text, parse_mode=None, reply_markup=None):
                await context.bot.edit_message_text(
                    chat_id=self.chat_id,
                    message_id=self.message_id,
                    text=text,
                    parse_mode=parse_mode,
                    reply_markup=reply_markup
                )
        battle_message = BattleMessage()
    except Exception as e:
        logger.error(f"Failed to find battle message {battle.battle_message_id}: {e}")
        await _end_battle(context, battle_id, user.id, opponent_id, "Battle message was deleted or not found.")
        return

    # 5. Run the animation flow
    winner_id, turn_log = await battle_animation_flow(
        battle_message, player, opponent, battle, jutsu_key
    )
    
    battle.log.append(f"Turn {battle.turn_count}: {player.username} used {jutsu['name']}. {turn_log}")
    
    # 6. Check for winner
    if winner_id:
        await battle_message.edit_text(battle.get_battle_state_text(), parse_mode=ParseMode.MARKDOWN)
        winner = player if winner_id == player.user_id else opponent
        await context.bot.send_message(
            battle.chat_id,
            f"🎉 **BATTLE OVER!** 🎉\n\n**{winner.username} is victorious!**\n\n{turn_log}",
            reply_markup=ReplyKeyboardRemove(),
            parse_mode=ParseMode.MARKDOWN
        )
        await _end_battle(context, battle_id, winner_id, (opponent_id if winner_id == user.id else user.id), battle.log)
        return
        
    # 7. If no winner, switch turns
    battle.switch_turn()
    
    # Update battle state in cache
    cache_manager.set_data("battle_state", battle_id, battle, ttl=config.BATTLE_CACHE_TTL)
    
    # Update message and keyboard for next turn
    next_player = opponent
    keyboard = build_jutsu_keyboard(next_player)
    
    await battle_message.edit_text(battle.get_battle_state_text(), parse_mode=ParseMode.MARKDOWN)
    await context.bot.send_message(
        battle.chat_id,
        f"It's {next_player.username}'s turn!",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )

async def flee_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Allows a player to flee a battle."""
    user_id = update.effective_user.id
    battle_id = cache_manager.get_data("user_battle_id", user_id)
    
    if not battle_id:
        await update.message.reply_text("You are not in a battle.")
        return
        
    battle: Battle = cache_manager.get_data("battle_state", battle_id)
    if not battle:
        await _end_battle(context, battle_id, user_id, None, "Battle state expired.")
        return
        
    opponent_id = cache_manager.get_battle_opponent(user_id)
    
    await context.bot.send_message(
        battle.chat_id,
        f"🏃 **{update.effective_user.first_name} has fled the battle!**\n\n"
        f"The winner is {context.bot.get_chat(opponent_id).first_name}!",
        reply_markup=ReplyKeyboardRemove(),
        parse_mode=ParseMode.MARKDOWN
    )
    
    await _end_battle(context, battle_id, opponent_id, user_id, battle.log + [f"{update.effective_user.first_name} fled."])

# --- Battle Helper Functions ---

async def _end_battle(context: ContextTypes.DEFAULT_TYPE, battle_id: str, winner_id: int, loser_id: int | None, log: list[str]):
    """Cleans up after a battle is over."""
    logger.info(f"Ending battle {battle_id}. Winner: {winner_id}, Loser: {loser_id}")
    
    # Clear cache
    cache_manager.delete_data("battle_state", battle_id)
    
    if winner_id:
        cache_manager.delete_data("user_battle_id", winner_id)
        cache_manager.delete_data("battle_lock", winner_id)
        
    if loser_id:
        cache_manager.delete_data("user_battle_id", loser_id)
        cache_manager.delete_data("battle_lock", loser_id)
        
    # --- Update Player Stats ---
    try:
        if winner_id and loser_id:
            winner = get_player(winner_id)
            loser = get_player(loser_id)
            
            # Grant rewards
            exp_gain = (loser.level * 15) + 50
            ryo_gain = (loser.level * 10) + 100
            
            lvl_up, exp_msg = winner.add_exp(exp_gain)
            winner.ryo += ryo_gain
            winner.wins += 1
            winner.set_cooldown('battle', 60) # 1 min cooldown
            winner.save()
            
            loser.losses += 1
            loser.set_cooldown('battle', 60)
            loser.save()
            
            await context.bot.send_message(
                winner_id,
                "**VICTORY!**\n"
                f"You defeated {loser.username}!\n"
                f"You earned {ryo_gain} Ryo.\n{exp_msg}"
            )
            await context.bot.send_message(
                loser_id,
                "**DEFEAT...**\n"
                f"You were defeated by {winner.username}."
            )
            
            # Log to battle_history (Prompt 16)
            _log_battle_history(winner_id, loser_id, log)
            
    except Exception as e:
        logger.error(f"Error updating player stats after battle {battle_id}: {e}")

def _log_battle_history(winner_id: int, loser_id: int, log: list[str]):
    """Saves the battle log to the database."""
    sql = """
    INSERT INTO battle_history (player1_id, player2_id, winner_id, battle_log)
    VALUES (?, ?, ?, ?)
    """
    try:
        with get_db_connection() as conn:
            conn.execute(sql, (winner_id, loser_id, winner_id, json.dumps(log)))
            conn.commit()
    except Exception as e:
        logger.error(f"Failed to log battle history: {e}")

def build_jutsu_keyboard(player: Player) -> list[list[str]]:
    """Creates a ReplyKeyboardMarkup of the player's jutsus."""
    keyboard = []
    row = []
    for jutsu_key in player.known_jutsus:
        jutsu = JUTSU_LIBRARY.get(jutsu_key)
        if jutsu and (jutsu['power'] > 0 or jutsu.get('effect')):
            # Add '/use' prefix
            row.append(f"/use {jutsu['name']}")
            if len(row) == 2:
                keyboard.append(row)
                row = []
    if row:
        keyboard.append(row)
    
    keyboard.append(["/flee"]) # Add flee button
    return keyboard

def register_battle_handlers(application: Application):
    application.add_handler(CommandHandler('battle', battle_command))
    application.add_handler(CommandHandler('use', use_jutsu_handler))
    application.add_handler(CommandHandler('flee', flee_command))
