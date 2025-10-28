# naruto_bot/handlers/activity_handlers.py
import logging
import asyncio
from datetime import datetime, timedelta, timezone
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler
from telegram.constants import ParseMode
from ..models import get_player
from ..game_data import MISSIONS, TRAINING_ANIMATIONS
from ..config import config

logger = logging.getLogger(__name__)

# --- Mission Handlers ---

async def missions_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Displays available missions."""
    user_id = update.effective_user.id
    if not user_id: 
        return
    logger.debug(f"Received /missions command from {user_id}")
    
    player = await get_player(user_id)
    if not player:
        await update.message.reply_text("You must /start your journey first.")
        return

    if player.current_mission:
        await update.message.reply_text(f"You are already busy: {player.current_mission}")
        return

    keyboard = []
    logger.debug("Building mission keyboard...")
    found_available = False
    for rank, details in MISSIONS.items():
        if not isinstance(details, dict) or not all(k in details for k in ['name', 'exp', 'ryo', 'level_req', 'duration_sec', 'animation_frames']):
             logger.warning(f"Mission definition for rank '{rank}' is incomplete or invalid. Skipping.")
             continue

        if player.level >= details['level_req']:
            keyboard.append([
                InlineKeyboardButton(
                    f"{rank}: {details['name']} ({details['exp']} EXP, {details['ryo']} Ryo)",
                    callback_data=f"mission_start_{rank}"
                )
            ])
            found_available = True
        else:
            keyboard.append([
                InlineKeyboardButton(
                    f"🔒 {rank}: {details['name']} (Lvl {details['level_req']} Req)",
                    callback_data="mission_locked"
                )
            ])

    if not found_available and not keyboard:
         await update.message.reply_text("There are currently no missions defined.")
         return
    elif not found_available:
         reply_markup = InlineKeyboardMarkup(keyboard)
         await update.message.reply_text(
             "**Mission Board**\n\nKeep training to unlock these missions!",
             reply_markup=reply_markup,
             parse_mode=ParseMode.MARKDOWN
         )
         return

    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "**Mission Board**\n\n"
        "Select a mission to begin. You cannot battle or train while on a mission.",
        reply_markup=reply_markup,
        parse_mode=ParseMode.MARKDOWN
    )
    logger.debug(f"Mission board sent to {user_id}")


async def mission_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles starting a mission from the callback."""
    query = update.callback_query
    user_id = update.effective_user.id
    if not query or not user_id: 
        return
    logger.debug(f"Received mission callback from {user_id}: {query.data}")
    await query.answer()

    if query.data == "mission_locked":
        await context.bot.send_message(user_id, "You do not meet the level requirement for this mission.")
        return

    try:
        mission_rank = query.data.split('_')[-1]
    except IndexError:
        logger.warning(f"Could not parse mission rank from callback data: {query.data}")
        await query.edit_message_text("Error processing mission selection.")
        return

    mission = MISSIONS.get(mission_rank)
    if not mission or not isinstance(mission, dict):
        logger.warning(f"Invalid or non-existent mission rank '{mission_rank}' received from {user_id}.")
        await query.edit_message_text("Invalid mission selected.")
        return

    player = await get_player(user_id)
    if not player:
        await query.edit_message_text("Player data not found. Please /start again.")
        return

    if player.level < mission.get('level_req', 999):
         await context.bot.send_message(user_id, "You no longer meet the level requirement for this mission.")
         return

    if player.current_mission:
        await query.edit_message_text(f"You are already busy: {player.current_mission}")
        return

    if not all(k in mission for k in ['duration_sec', 'animation_frames', 'name', 'exp', 'ryo']) or not mission['animation_frames']:
         logger.error(f"Mission '{mission_rank}' definition is incomplete. Cannot start.")
         await query.edit_message_text("This mission is currently unavailable due to a configuration error.")
         return

    run_at = datetime.now(timezone.utc) + timedelta(seconds=mission['duration_sec'])
    start_frame = mission['animation_frames'][0]
    
    try:
        message = await query.edit_message_text(start_frame, parse_mode=ParseMode.MARKDOWN)

        if not context.job_queue:
            logger.error("JobQueue is not available in context. Cannot schedule mission completion.")
            await message.edit_text("Error: Cannot schedule mission completion. Please contact admin.")
            return

        job_name = f"mission_{user_id}_{mission_rank}_{int(datetime.now().timestamp())}"
        context.job_queue.run_once(
            _mission_completion_job,
            run_at,
            data={
                'user_id': player.user_id,
                'chat_id': query.message.chat_id,
                'message_id': message.message_id,
                'mission_rank': mission_rank
            },
            name=job_name
        )
        logger.info(f"Scheduled mission '{mission_rank}' ({job_name}) for player {user_id} to complete at {run_at}.")

        player.current_mission = mission['name']
        player.mark_modified()
        player.save()

    except Exception as e:
        logger.error(f"Failed to start mission '{mission_rank}' for player {user_id}: {e}", exc_info=True)
        try:
             await query.message.reply_text("Failed to start the mission due to an error.")
        except Exception as report_err:
             logger.error(f"Failed also to send error report to user {user_id}: {report_err}")


async def _mission_completion_job(context: ContextTypes.DEFAULT_TYPE):
    """The job that runs when a mission is complete."""
    job_data = context.job.data
    user_id = job_data.get('user_id')
    mission_rank = job_data.get('mission_rank')
    chat_id = job_data.get('chat_id')
    message_id = job_data.get('message_id')

    if not all([user_id, mission_rank, chat_id, message_id]):
         logger.error(f"Mission completion job missing essential data: {job_data}")
         return

    logger.info(f"Running mission completion job for user {user_id}, mission {mission_rank}.")

    player = await get_player(user_id)
    mission = MISSIONS.get(mission_rank)

    if not player:
        logger.warning(f"Player {user_id} not found for mission completion job.")
        return
    
    if not mission or not isinstance(mission, dict) or 'name' not in mission:
         logger.error(f"Mission rank '{mission_rank}' not found or invalid in MISSIONS for completion job.")
         if player.current_mission and mission_rank in player.current_mission:
              logger.warning(f"Clearing potentially related mission status '{player.current_mission}' for player {user_id}")
              player.current_mission = None
              player.mark_modified()
              player.save() # <-- THIS LINE WAS FIXED
         return

    if player.current_mission != mission['name']:
         logger.warning(f"Player {user_id} is no longer on mission '{mission['name']}' (current: {player.current_mission}). Job aborted.")
         return

    bot = context.bot

    # --- Animate Completion ---
    try:
        frames = mission.get('animation_frames', [])
        animation_frames = frames[1:] if len(frames) > 1 else frames
        
        if not animation_frames:
             logger.warning(f"No animation frames (or only 1) defined for mission '{mission_rank}'. Skipping animation.")
        else:
            total_anim_duration = max(5.0, mission.get('duration_sec', 30) * 0.2)
            duration_per_frame = max(config.ANIMATION_DELAY, total_anim_duration / len(animation_frames))

            for frame in animation_frames:
                try:
                    await bot.edit_message_text(
                        chat_id=chat_id, message_id=message_id,
                        text=frame, parse_mode=ParseMode.MARKDOWN
                    )
                    await asyncio.sleep(duration_per_frame)
                except Exception as edit_err:
                    logger.warning(f"Failed to edit mission message {message_id} (frame): {edit_err}. Stopping animation.")
                    try:
                         await bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=frames[-1], parse_mode=ParseMode.MARKDOWN)
                    except: 
                        pass
                    break

            final_frame = frames[-1] if frames else "Mission animation error."
            try:
                 await bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=final_frame, parse_mode=ParseMode.MARKDOWN)
            except Exception as final_edit_err:
                 logger.warning(f"Failed to set final animation frame for mission {message_id}: {final_edit_err}")

    except Exception as anim_e:
        logger.error(f"Mission animation failed unexpectedly for user {user_id}: {anim_e}", exc_info=True)
        try:
             final_frame = mission.get('animation_frames', ["Mission error."])[-1]
             await bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=final_frame, parse_mode=ParseMode.MARKDOWN)
        except Exception as fallback_e:
             logger.error(f"Failed to set fallback final frame for mission {message_id} after error: {fallback_e}")

    # --- Grant Rewards ---
    try:
        exp_reward = mission.get('exp', 0)
        ryo_reward = mission.get('ryo', 0)

        level_up_msg, exp_msg = player.add_exp(exp_reward)

        player.ryo += ryo_reward
        player.current_mission = None
        player.mark_modified()
        player.save()

        logger.info(f"Mission '{mission_rank}' completed by player {user_id}. Rewarded {exp_reward} EXP, {ryo_reward} Ryo.")

        reward_message = f"**Mission Complete: {mission['name']}**\n{exp_msg}\nYou gained {ryo_reward} Ryo 💰."
        if level_up_msg:
             reward_message += f"\n\n{level_up_msg}"

        await bot.send_message(chat_id, reward_message, parse_mode=ParseMode.MARKDOWN)

    except Exception as reward_e:
         logger.error(f"Failed to grant rewards for mission '{mission_rank}', user {user_id}: {reward_e}", exc_info=True)
         await bot.send_message(chat_id, f"An error occurred while granting rewards for mission {mission.get('name', mission_rank)}. Please contact support.")
         if player and player.current_mission == mission.get('name'):
              player.current_mission = None
              player.mark_modified()
              player.save()


# --- Training Handlers ---

async def train_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the /train command."""
    user_id = update.effective_user.id
    if not user_id: 
        return
    logger.debug(f"Received /train command from {user_id} with args: {context.args}")
    
    player = await get_player(user_id)
    if not player:
        await update.message.reply_text("You must /start your journey first.")
        return

    if player.current_mission:
        await update.message.reply_text(f"You cannot train while busy: {player.current_mission}.")
        return

    args = context.args
    if not args:
        available_training = "\n".join([f" - `{key}` ({details.get('description', 'Stat Increase')})"
                                        for key, details in TRAINING_ANIMATIONS.items()])
        await update.message.reply_text(
            "Which skill do you want to train?\n"
            "Usage: `/train [type]`\n\n"
            f"Available Training:\n{available_training}",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    train_type = args[0].lower()
    training = TRAINING_ANIMATIONS.get(train_type)

    if not training or not isinstance(training, dict):
        valid_types = ", ".join([f"`{k}`" for k in TRAINING_ANIMATIONS.keys()])
        await update.message.reply_text(f"Invalid training type '{train_type}'. Valid types: {valid_types}.", parse_mode=ParseMode.MARKDOWN)
        return

    required_keys = ['duration_sec', 'frames', 'stat', 'gain', 'display_name', 'description']
    if not all(k in training for k in required_keys) or not training['frames']:
         logger.error(f"Training definition for '{train_type}' is incomplete or invalid.")
         await update.message.reply_text("This training is currently unavailable due to configuration error.")
         return

    run_at = datetime.now(timezone.utc) + timedelta(seconds=training['duration_sec'])
    start_frame = training['frames'][0]
    
    try:
        message = await update.message.reply_text(start_frame, parse_mode=ParseMode.MARKDOWN)

        if not context.job_queue:
            logger.error("JobQueue is not available in context. Cannot schedule training completion.")
            await message.edit_text("Error: Cannot schedule training completion. Please contact admin.")
            return

        job_name = f"train_{user_id}_{train_type}_{int(datetime.now().timestamp())}"
        context.job_queue.run_once(
            _training_completion_job,
            run_at,
            data={
                'user_id': player.user_id,
                'chat_id': message.chat_id,
                'message_id': message.message_id,
                'train_type': train_type
            },
            name=job_name
        )
        logger.info(f"Scheduled training '{train_type}' ({job_name}) for player {user_id} to complete at {run_at}.")

        player.current_mission = f"Training {training.get('display_name', train_type.capitalize())}"
        player.mark_modified()
        player.save()

    except Exception as e:
        logger.error(f"Failed to start training '{train_type}' for player {user_id}: {e}", exc_info=True)
        await update.message.reply_text("Failed to start training due to an error.")


async def _training_completion_job(context: ContextTypes.DEFAULT_TYPE):
    """The job that runs when training is complete."""
    job_data = context.job.data
    user_id = job_data.get('user_id')
    train_type = job_data.get('train_type')
    chat_id = job_data.get('chat_id')
    message_id = job_data.get('message_id')

    if not all([user_id, train_type, chat_id, message_id]):
         logger.error(f"Training completion job missing essential data: {job_data}")
         return

    logger.info(f"Running training completion job for user {user_id}, type {train_type}.")

    player = await get_player(user_id)
    training = TRAINING_ANIMATIONS.get(train_type)

    if not player:
        logger.warning(f"Player {user_id} not found for training job.")
        return
    
    if not training or not isinstance(training, dict):
        logger.error(f"Training type '{train_type}' not found or invalid in TRAINING_ANIMATIONS.")
        if player.current_mission and train_type in player.current_mission:
             player.current_mission = None
             player.mark_modified()
             player.save()
        return

    if not all(k in training for k in ['stat', 'gain', 'display_name']):
         logger.error(f"Training definition for '{train_type}' missing reward keys (stat/gain/display_name).")
         if player.current_mission and train_type in player.current_mission:
              player.current_mission = None
              player.mark_modified()
              player.save()
         return

    expected_status = f"Training {training.get('display_name', train_type.capitalize())}"
    if player.current_mission != expected_status:
         logger.warning(f"Player {user_id} is no longer training '{train_type}' (current: {player.current_mission}). Job aborted.")
         return

    bot = context.bot

    # --- Play Animation ---
    try:
        frames = training.get('frames', [])
        if frames:
            total_anim_duration = max(3.0, training.get('duration_sec', 30) * 0.15)
            duration_per_frame = max(config.ANIMATION_DELAY, total_anim_duration / len(frames))

            for frame in frames:
                try:
                    await bot.edit_message_text(
                        chat_id=chat_id, message_id=message_id,
                        text=frame, parse_mode=ParseMode.MARKDOWN
                    )
                    await asyncio.sleep(duration_per_frame)
                except Exception as edit_err:
                    logger.warning(f"Failed to edit training message {message_id}: {edit_err}")
                    break
    except Exception as anim_e:
        logger.error(f"Training animation failed for user {user_id}: {anim_e}", exc_info=True)

    # --- Grant Rewards ---
    try:
        stat_to_gain = training['stat']
        gain_amount = training['gain']

        if hasattr(player, stat_to_gain):
            current_value = getattr(player, stat_to_gain)
            if isinstance(gain_amount, (int, float)) and gain_amount > 0:
                 setattr(player, stat_to_gain, current_value + gain_amount)
                 player.mark_modified()

                 hp_updated = False
                 chakra_updated = False
                 if stat_to_gain == 'stamina':
                     player.max_hp = 100 + (player.stamina * 10)
                     player.current_hp = min(player.max_hp, player.current_hp + 10)
                     player.mark_modified()
                     hp_updated = True
                 elif stat_to_gain == 'intelligence':
                     player.max_chakra = 100 + (player.intelligence * 5)
                     player.current_chakra = min(player.max_chakra, player.current_chakra + 10)
                     player.mark_modified()
                     chakra_updated = True

            else:
                 logger.error(f"Invalid gain amount '{gain_amount}' for training '{train_type}'.")
        else:
             logger.error(f"Stat '{stat_to_gain}' in training '{train_type}' does not exist on Player.")

        player.current_mission = None
        player.mark_modified()
        player.save()

        logger.info(f"Training '{train_type}' completed by player {user_id}. Gained {gain_amount} {stat_to_gain}.")

    except Exception as reward_e:
         logger.error(f"Failed to grant rewards for training '{train_type}', user {user_id}: {reward_e}", exc_info=True)
         await bot.send_message(chat_id, f"An error occurred completing your training ({training.get('display_name', train_type)}).")
         if player and player.current_mission == expected_status:
              player.current_mission = None
              player.mark_modified()
              player.save()


def register_activity_handlers(application: Application):
    logger.debug("Registering activity handlers...")
    application.add_handler(CommandHandler('missions', missions_command))
    application.add_handler(CallbackQueryHandler(mission_callback, pattern='^mission_'))
    application.add_handler(CommandHandler('train', train_command))
    logger.debug("Activity handlers registered.")
