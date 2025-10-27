# naruto_bot/handlers/activity_handlers.py
import logging
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler
from telegram.constants import ParseMode
from ..models import get_player
from ..game_data import MISSIONS, TRAINING_ANIMATIONS
from ..animations import animate_activity

logger = logging.getLogger(__name__)

# --- Mission Handlers (Prompt 14) ---

async def missions_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Displays available missions."""
    player = get_player(update.effective_user.id)
    if not player:
        await update.message.reply_text("You must /start your journey first.")
        return

    if player.current_mission:
        await update.message.reply_text(f"You are already on a mission: {player.current_mission}")
        return

    keyboard = []
    for rank, details in MISSIONS.items():
        if player.level >= details['level_req']:
            keyboard.append([
                InlineKeyboardButton(
                    f"{rank}: {details['name']} ({details['exp']} EXP, {details['ryo']} Ryo)",
                    callback_data=f"mission_start_{rank}"
                )
            ])
        else:
            keyboard.append([
                InlineKeyboardButton(
                    f"🔒 {rank}: {details['name']} (Lvl {details['level_req']} Req)",
                    callback_data="mission_locked"
                )
            ])
            
    await update.message.reply_text(
        "**Mission Board**\n\n"
        "Select a mission to begin. You cannot battle or train while on a mission.",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.MARKDOWN
    )

async def mission_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles starting a mission from the callback."""
    query = update.callback_query
    await query.answer()

    if query.data == "mission_locked":
        await query.message.reply_text("You do not meet the level requirement for this mission.")
        return

    mission_rank = query.data.split('_')[-1]
    if mission_rank not in MISSIONS:
        await query.edit_message_text("Invalid mission.")
        return

    player = get_player(update.effective_user.id)
    if not player:
        await query.edit_message_text("Player not found. Please /start.")
        return

    if player.current_mission:
        await query.edit_message_text(f"You are already on a mission: {player.current_mission}")
        return
        
    mission = MISSIONS[mission_rank]
    run_at = datetime.now() + timedelta(seconds=mission['duration_sec'])
    
    # Send initial animation frame
    start_frame = mission['animation_frames'][0]
    message = await query.edit_message_text(start_frame)

    # Schedule the completion job
    context.job_queue.run_once(
        _mission_completion_job,
        run_at,
        data={
            'user_id': player.user_id,
            'chat_id': query.message.chat_id,
            'message_id': message.message_id,
            'mission_rank': mission_rank
        },
        name=f"mission_{player.user_id}"
    )
    
    # Set player status
    player.current_mission = mission['name']
    player.save()

async def _mission_completion_job(context: ContextTypes.DEFAULT_TYPE):
    """The job that runs when a mission is complete."""
    job_data = context.job.data
    user_id = job_data['user_id']
    mission_rank = job_data['mission_rank']
    
    player = get_player(user_id)
    mission = MISSIONS[mission_rank]
    
    if not player:
        logger.warning(f"Player {user_id} not found for mission completion job.")
        return

    # Create a dummy message object for animation
    class DummyMessage:
        chat_id = job_data['chat_id']
        message_id = job_data['message_id']
        async def edit_text(self, text, parse_mode=None, reply_markup=None):
            await context.bot.edit_message_text(
                chat_id=self.chat_id,
                message_id=self.message_id,
                text=text,
                parse_mode=parse_mode,
                reply_markup=reply_markup
            )
            
    message = DummyMessage()
    
    # Play the rest of the animation
    try:
        frames = mission['animation_frames'][1:] # All except the first frame
        duration_per_frame = (mission['duration_sec'] - 10) / len(frames) # -10s for safety
        
        for frame in frames:
            await message.edit_text(frame)
            await asyncio.sleep(duration_per_frame)
            
    except Exception as e:
        logger.error(f"Mission animation failed for user {user_id}: {e}")
        # Fallback message
        await message.edit_text(mission['animation_frames'][-1])

    # Grant rewards
    exp_gain, exp_msg = player.add_exp(mission['exp'])
    player.ryo += mission['ryo']
    player.current_mission = None
    player.save()
    
    await context.bot.send_message(job_data['chat_id'], f"**Mission Rewards:**\n{exp_msg}\nYou gained {mission['ryo']} Ryo.", parse_mode=ParseMode.MARKDOWN)


# --- Training Handlers (Prompt 15) ---

async def train_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the /train command."""
    player = get_player(update.effective_user.id)
    if not player:
        await update.message.reply_text("You must /start your journey first.")
        return

    if player.current_mission:
        await update.message.reply_text("You cannot train while on a mission.")
        return
        
    args = context.args
    if not args:
        await update.message.reply_text(
            "Which stat do you want to train?\n"
            "Usage: `/train [type]`\n\n"
            "Types:\n"
            " - `taijutsu` (Strength)\n"
            " - `chakra_control` (Max Chakra)\n"
            " - `stamina` (Stamina)",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    train_type = args[0].lower()
    if train_type not in TRAINING_ANIMATIONS:
        await update.message.reply_text("Invalid training type. Valid types: `taijutsu`, `chakra_control`, `stamina`.")
        return

    training = TRAINING_ANIMATIONS[train_type]
    run_at = datetime.now() + timedelta(seconds=training['duration_sec'])
    
    start_frame = training['frames'][0]
    message = await update.message.reply_text(start_frame)

    # Schedule the completion job
    context.job_queue.run_once(
        _training_completion_job,
        run_at,
        data={
            'user_id': player.user_id,
            'chat_id': message.chat_id,
            'message_id': message.message_id,
            'train_type': train_type
        },
        name=f"train_{player.user_id}"
    )
    
    # Set player status
    player.current_mission = f"Training {train_type.capitalize()}" # Use mission slot
    player.save()

async def _training_completion_job(context: ContextTypes.DEFAULT_TYPE):
    """The job that runs when training is complete."""
    job_data = context.job.data
    user_id = job_data['user_id']
    train_type = job_data['train_type']
    
    player = get_player(user_id)
    training = TRAINING_ANIMATIONS[train_type]
    
    if not player:
        logger.warning(f"Player {user_id} not found for training job.")
        return

    # Create a dummy message object for animation
    class DummyMessage:
        chat_id = job_data['chat_id']
        message_id = job_data['message_id']
        async def edit_text(self, text, parse_mode=None, reply_markup=None):
            await context.bot.edit_message_text(
                chat_id=self.chat_id,
                message_id=self.message_id,
                text=text,
                parse_mode=parse_mode,
                reply_markup=reply_markup
            )
            
    message = DummyMessage()

    # Play animation
    try:
        frames = training['frames'] # Play all frames
        duration_per_frame = (training['duration_sec'] - 5) / len(frames)
        for frame in frames:
            await message.edit_text(frame)
            await asyncio.sleep(duration_per_frame)
    except Exception as e:
        logger.error(f"Training animation failed for user {user_id}: {e}")
        await message.edit_text(training['frames'][-1]) # Fallback to last frame

    # Grant rewards
    stat_to_gain = training['stat']
    gain_amount = training['gain']
    
    setattr(player, stat_to_gain, getattr(player, stat_to_gain) + gain_amount)
    player.current_mission = None
    player.save()

def register_activity_handlers(application: Application):
    application.add_handler(CommandHandler('missions', missions_command))
    application.add_handler(CallbackQueryHandler(mission_callback, pattern='^mission_start_'))
    application.add_handler(CallbackQueryHandler(mission_callback, pattern='^mission_locked$'))
    application.add_handler(CommandHandler('train', train_command))
