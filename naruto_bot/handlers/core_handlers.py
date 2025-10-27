import logging
import sqlite3
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Application, 
    CommandHandler, 
    ContextTypes, 
    CallbackQueryHandler,
    ConversationHandler
)
from telegram.constants import ParseMode
from ..models import get_player, create_player, Player # get_player is async
from ..game_data import VILLAGES # JUTSU_LIBRARY, RANKS removed unused imports
from ..services import health_bar, chakra_bar

logger = logging.getLogger(__name__)

# --- Conversation States ---
CHOOSE_VILLAGE = range(1)

# --- Command Handlers ---

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Handles the /start command.
    Checks if the player exists. If not, starts the registration process.
    """
    user = update.effective_user
    if not user: 
        logger.warning("start_command received update without effective_user.")
        return ConversationHandler.END

    logger.info(f"Received /start command from user_id: {user.id}")

    try:
        logger.debug(f"Attempting to get player data for {user.id}...")
        # --- FIX: Added await ---
        player = await get_player(user.id)
        logger.debug(f"Player data for {user.id}: {'Found' if player else 'Not Found'}")

        if player:
            logger.debug(f"Existing player found ({player.username}). Sending welcome back message.")
            # Ensure village key exists before accessing
            village_name = VILLAGES.get(player.village, {}).get('name', 'an unknown village')
            await context.bot.send_message(
                chat_id=user.id,
                text=(
                    f"Welcome back, {player.username} of {village_name}!\n\n"
                    "You are a shinobi on your path to greatness. What will you do?\n\n"
                    "Use /profile to see your stats.\n"
                    "Use /missions to earn Ryo and EXP.\n"
                    "Use /battle @username to challenge another ninja."
                ),
                reply_markup=ReplyKeyboardRemove()
            )
            logger.debug(f"Welcome back message sent to {user.id}.")
            return ConversationHandler.END
        else:
            # New player, start registration
            logger.info(f"New player registration started for user_id: {user.id}")
            keyboard = []
            for key, data in VILLAGES.items():
                if isinstance(data, dict) and 'name' in data:
                     keyboard.append([InlineKeyboardButton(data['name'], callback_data=f'village_{key}')])
                else:
                     logger.warning(f"Village data for key '{key}' is invalid or missing 'name'. Skipping button.")

            if not keyboard:
                logger.error("VILLAGES data is empty or invalid. Cannot create registration keyboard.")
                await context.bot.send_message(user.id, "Sorry, registration is currently unavailable due to a configuration error.")
                return ConversationHandler.END

            reply_markup = InlineKeyboardMarkup(keyboard)

            village_descriptions = []
            for key, data in VILLAGES.items():
                if isinstance(data, dict) and all(k in data for k in ['name', 'icon', 'bonus_text']):
                     village_descriptions.append(f"{data['icon']} **{data['name']}**: {data['bonus_text']}")
                else:
                     logger.warning(f"Village data for key '{key}' is missing required fields for description.")

            choose_text = "**Choose your village:**\n\n" + "\n".join(village_descriptions)

            await context.bot.send_message(
                chat_id=user.id,
                text="Welcome, aspiring ninja! Your journey begins now.\n\n"
                     "First, you must choose your home village. This choice is permanent!"
            )
            await context.bot.send_message(
                chat_id=user.id,
                text=choose_text,
                reply_markup=reply_markup,
                parse_mode=ParseMode.MARKDOWN
            )
            logger.debug(f"Registration messages sent to {user.id}. Returning CHOOSE_VILLAGE state.")
            return CHOOSE_VILLAGE

    except Exception as e:
        logger.error(f"Error occurred in start_command for user {user.id}: {e}", exc_info=True)
        try:
            await context.bot.send_message(
                chat_id=user.id,
                text="An error occurred while processing the /start command. Please try again later or contact support."
            )
        except Exception as send_error:
            logger.error(f"Failed to send error message to user {user.id}: {send_error}")
        return ConversationHandler.END


async def village_selection_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handles the village selection from the InlineKeyboard."""
    query = update.callback_query
    user = update.effective_user
    if not query or not user: return

    logger.debug(f"Received village selection callback from {user.id}: {query.data}")
    await query.answer()

    try:
        village_key = query.data.split('_')[1]
    except IndexError:
        logger.warning(f"Could not parse village key from callback data: {query.data}")
        await query.edit_message_text("Error processing selection.")
        return ConversationHandler.END

    if village_key not in VILLAGES:
        logger.warning(f"Invalid village key '{village_key}' received from {user.id}.")
        await query.edit_message_text("Invalid village selected. Please try /start again.")
        return ConversationHandler.END

    # Check if player already exists BEFORE attempting creation
    # --- FIX: Added await ---
    existing_player = await get_player(user.id)
    if existing_player:
         logger.warning(f"User {user.id} tried to select village '{village_key}' but already exists as {existing_player.username}.")
         try:
            await query.edit_message_text("You are already registered! Use /profile.")
         except Exception as edit_err:
             logger.warning(f"Could not edit message for existing user {user.id}: {edit_err}")
             await context.bot.send_message(user.id, "You are already registered! Use /profile.")
         return ConversationHandler.END

    # Create the player (create_player is synchronous)
    username = user.username or f"Ninja-{user.id}"
    logger.info(f"Attempting to create player {user.id} ({username}) in village {village_key}.")
    try:
        player = create_player(user.id, username, village_key)

        if not player:
            logger.error(f"create_player failed for user {user.id}.")
            await query.edit_message_text("An internal error occurred during registration. Please contact an admin or try again later.")
            return ConversationHandler.END

        village_name = VILLAGES.get(village_key, {}).get('name', village_key)
        logger.info(f"Player {user.id} successfully created in {village_name}.")
        await query.edit_message_text(
            f"You have joined **{village_name}**!\n\n"
            f"Welcome, {player.username}. You are now an **{player.rank}**.\n\n"
            "Your journey has just begun. Use /profile to see your status or /help to see all commands.",
            parse_mode=ParseMode.MARKDOWN
        )

    except Exception as e:
        logger.error(f"Unexpected error during village selection/player creation for {user.id}: {e}", exc_info=True)
        try:
            await query.edit_message_text("An unexpected error occurred during registration. Please try again.")
        except Exception as final_err:
             logger.error(f"Failed even to send final error message to user {user.id}: {final_err}")

    return ConversationHandler.END

async def cancel_registration(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancels the registration conversation."""
    user = update.effective_user
    if user:
        logger.info(f"Registration cancelled by user {user.id}.")
        await update.message.reply_text("Registration cancelled. You can restart anytime with /start.")
    return ConversationHandler.END

async def profile_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the /profile command."""
    user = update.effective_user
    if not user: return

    logger.debug(f"Received /profile command from {user.id}")
    # --- FIX: Added await ---
    player = await get_player(user.id)

    if not player:
        logger.debug(f"User {user.id} tried /profile but is not registered.")
        await update.message.reply_text("You haven't started your journey yet! Use /start to begin.")
        return

    try:
        # Check instance type (safety check)
        if not isinstance(player, Player):
             logger.error(f"get_player returned non-Player object for {user.id}: {type(player)}")
             await update.message.reply_text("Error retrieving your profile data.")
             return

        # Get village bonus safely
        bonus_elem, bonus_perc = player.get_village_bonus()
        bonus_text = f"+{int(bonus_perc * 100)}% {bonus_elem.capitalize()} Damage" if bonus_elem != 'none' else "No Bonus"
        exp_needed = player.get_exp_for_level(player.level)
        village_name = VILLAGES.get(player.village, {}).get('name', player.village)

        profile_text = (
            f"👤 **Ninja Profile: {player.username}**\n\n"
            f"**Village:** {village_name} ({bonus_text})\n"
            f"**Rank:** {player.rank}\n"
            f"**Level:** {player.level} ({player.exp} / {exp_needed} EXP)\n"
            f"**Ryo:** {player.ryo} 💰\n\n"
            f"❤️ **HP:** {health_bar(player.current_hp, player.max_hp)}\n"
            f"🔵 **Chakra:** {chakra_bar(player.current_chakra, player.max_chakra)}\n\n"
            f"**--- Stats ---**\n"
            f"💪 **Strength:** {player.strength}\n"
            f"⚡ **Speed:** {player.speed}\n"
            f"🧠 **Intelligence:** {player.intelligence}\n"
            f"🛡️ **Stamina:** {player.stamina}\n\n"
            f"**--- Battle ---**\n"
            f"**Wins:** {player.wins}\n"
            f"**Losses:** {player.losses}\n\n"
            f"**Jutsus Known:** {len(player.known_jutsus)} / 25\n"
            f"Use /jutsus to see your list."
        )

        await update.message.reply_text(profile_text, parse_mode=ParseMode.MARKDOWN)
        logger.debug(f"Profile sent to {user.id}")
    except Exception as e:
        logger.error(f"Error generating or sending profile for {user.id}: {e}", exc_info=True)
        await update.message.reply_text("Could not display your profile due to an error.")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Displays the help message with available commands."""
    user = update.effective_user
    if not user: return
    logger.debug(f"Received /help command from {user.id}")

    help_text = (
         "**📜 Available Commands 📜**\n\n"
        "**Core Gameplay:**\n"
        "`/start` - Start your ninja journey\n"
        "`/profile` - Check your stats and progress\n"
        "`/battle @username` - Challenge another player (reply to their msg)\n"
        "`/train [type]` - Train stats (`taijutsu`, `chakra_control`, `stamina`)\n"
        "`/missions` - View and start available missions\n\n"

        "**Jutsu System:**\n"
        "`/jutsus` - List your learned jutsus\n"
        "`/combine [signs]` - Try hand signs (e.g., `/combine tiger snake bird`)\n"
        "`/use [jutsu]` - Use a jutsu in battle (use keyboard)\n\n"

        "`/help` - Show this message"
    )
    try:
        await update.message.reply_text(help_text, parse_mode=ParseMode.MARKDOWN)
        logger.debug(f"Help message sent to {user.id}")
    except Exception as e:
        logger.error(f"Failed to send help message to {user.id}: {e}", exc_info=True)

def register_core_handlers(application: Application):
    logger.debug("Registering core handlers...")
    # Conversation handler for /start registration
    start_conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start_command)],
        states={
            CHOOSE_VILLAGE: [CallbackQueryHandler(village_selection_callback, pattern='^village_')]
        },
        fallbacks=[CommandHandler('cancel', cancel_registration)],
        per_user=True,
        per_chat=True
    )

    application.add_handler(start_conv_handler)
    application.add_handler(CommandHandler('profile', profile_command))
    application.add_handler(CommandHandler('help', help_command))
    logger.debug("Core handlers registered.")
