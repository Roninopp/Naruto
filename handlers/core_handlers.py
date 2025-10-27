# naruto_bot/handlers/core_handlers.py
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Application, 
    CommandHandler, 
    ContextTypes, 
    CallbackQueryHandler,
    ConversationHandler
)
from telegram.constants import ParseMode
from ..models import get_player, create_player, Player
from ..game_data import VILLAGES, JUTSU_LIBRARY, RANKS
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
    player = get_player(user.id)
    
    if player:
        # Player exists, show main menu
        await context.bot.send_message(
            chat_id=user.id,
            text=(
                f"Welcome back, {player.username} of {VILLAGES[player.village]['name']}!\n\n"
                "You are a shinobi on your path to greatness. What will you do?\n\n"
                "Use /profile to see your stats.\n"
                "Use /missions to earn Ryo and EXP.\n"
                "Use /battle to challenge another ninja."
            ),
            reply_markup=ReplyKeyboardRemove()
        )
        return ConversationHandler.END
    else:
        # New player, start registration
        logger.info(f"New player registration started for user_id: {user.id}")
        keyboard = [
            [InlineKeyboardButton(VILLAGES['konoha']['name'], callback_data='village_konoha')],
            [InlineKeyboardButton(VILLAGES['suna']['name'], callback_data='village_suna')],
            [InlineKeyboardButton(VILLAGES['kiri']['name'], callback_data='village_kiri')],
            [InlineKeyboardButton(VILLAGES['kumo']['name'], callback_data='village_kumo')],
            [InlineKeyboardButton(VILLAGES['iwa']['name'], callback_data='village_iwa')],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await context.bot.send_message(
            chat_id=user.id,
            text="Welcome, aspiring ninja! Your journey begins now.\n\n"
                 "First, you must choose your home village. This choice is permanent!"
        )
        await context.bot.send_message(
            chat_id=user.id,
            text="**Choose your village:**\n\n"
                 f"🔥 **{VILLAGES['konoha']['name']}**: +15% Fire Damage\n"
                 f"💨 **{VILLAGES['suna']['name']}**: +15% Wind Damage\n"
                 f"💧 **{VILLAGES['kiri']['name']}**: +15% Water Damage\n"
                 f"⚡ **{VILLAGES['kumo']['name']}**: +15% Lightning Damage\n"
                 f"⛰ **{VILLAGES['iwa']['name']}**: +15% Earth Damage",
            reply_markup=reply_markup,
            parse_mode=ParseMode.MARKDOWN
        )
        return CHOOSE_VILLAGE

async def village_selection_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handles the village selection from the InlineKeyboard."""
    query = update.callback_query
    await query.answer()
    
    user = update.effective_user
    village_key = query.data.split('_')[1] # e.g., 'village_konoha' -> 'konoha'
    
    if village_key not in VILLAGES:
        await query.edit_message_text("Invalid village. Please try /start again.")
        return ConversationHandler.END
        
    # Create the player
    username = user.username or f"Ninja-{user.id}"
    player = create_player(user.id, username, village_key)
    
    if not player:
        await query.edit_message_text("An error occurred during registration. Please contact an admin.")
        return ConversationHandler.END

    village_name = VILLAGES[village_key]['name']
    await query.edit_message_text(
        f"You have joined **{village_name}**!\n\n"
        f"Welcome, {player.username}. You are now an **{player.rank}**.\n\n"
        "Your journey has just begun. Use /profile to see your status or /help to see all commands.",
        parse_mode=ParseMode.MARKDOWN
    )
    return ConversationHandler.END

async def cancel_registration(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancels the registration conversation."""
    await update.message.reply_text("Registration cancelled. You can restart anytime with /start.")
    return ConversationHandler.END

async def profile_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the /profile command."""
    user = update.effective_user
    player = get_player(user.id)
    
    if not player:
        await update.message.reply_text("You haven't started your journey yet! Use /start to begin.")
        return

    # Get village bonus
    bonus_elem, bonus_perc = player.get_village_bonus()
    bonus_text = f"+{bonus_perc * 100}% {bonus_elem.capitalize()} Damage"

    profile_text = (
        f"👤 **Ninja Profile: {player.username}**\n\n"
        f"**Village:** {VILLAGES[player.village]['name']} ({bonus_text})\n"
        f"**Rank:** {player.rank}\n"
        f"**Level:** {player.level} ({player.exp} / {player.get_exp_for_level(player.level)} EXP)\n"
        f"**Ryo:** {player.ryo} 💰\n\n"
        f"❤️ **HP:** {health_bar(player.current_hp, player.max_hp)}\n"
        f"🔵 **Chakra:** {chakra_bar(player.current_chakra, player.max_chakra)}\n\n"
        f"**--- Stats ---**\n"
        f"💪 **Strength:** {player.strength}\n"
        f"⚡ **Speed:** {player.speed}\n"
        f"🧠 **Intelligence:** {player.intelligence}\n"
        f"맷 **Stamina:** {player.stamina}\n\n"
        f"**--- Battle ---**\n"
        f"**Wins:** {player.wins}\n"
        f"**Losses:** {player.losses}\n\n"
        f"**Jutsus Known:** {len(player.known_jutsus)} / 25\n"
        f"Use /jutsus to see your list."
    )
    
    await update.message.reply_text(profile_text, parse_mode=ParseMode.MARKDOWN)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Displays the help message with all commands (Prompt 17)."""
    help_text = (
        "**📜 Available Commands 📜**\n\n"
        "**Core Gameplay:**\n"
        "/start - Start your ninja journey\n"
        "/profile - Check your stats and progress\n"
        "/battle - Reply to a user's message to challenge them\n"
        "/train - Train to improve stats (e.g., /train taijutsu)\n"
        "/missions - View and start available missions\n\n"
        
        "**Jutsu System:**\n"
        "/jutsus - List your learned jutsus\n"
        "/combine `[signs]` - Try a hand sign combination (e.g., /combine tiger snake bird)\n"
        "/use `[jutsu]` - Use a specific jutsu (in battle)\n\n"
        
        "**Progression:**\n"
        "/rankup - (Not Implemented) Attempt rank promotion\n"
        "/leaderboard - (Not Implemented) View top players\n\n"
        
        "**Social:**\n"
        "/gift `@[user] [amount]` - (Not Implemented) Gift Ryo to another player"
    )
    await update.message.reply_text(help_text, parse_mode=ParseMode.MARKDOWN)

def register_core_handlers(application: Application):
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
