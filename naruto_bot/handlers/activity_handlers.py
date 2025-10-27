import logging
import asyncio
from datetime import datetime, timedelta, timezone # Import timezone
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler
from telegram.constants import ParseMode
# Correctly import the async get_player
from ..models import get_player
from ..game_data import MISSIONS, TRAINING_ANIMATIONS
from ..config import config # Import config for animation delay

logger = logging.getLogger(__name__)

# --- Mission Handlers ---

async def missions_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Displays available missions."""
    user_id = update.effective_user.id
    if not user_id: return
    logger.debug(f"Received /missions command from {user_id}")
    # --- FIX: Added await ---
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
        # Validate mission details structure
        if not isinstance(details, dict) or not all(k in details for k in ['name', 'exp', 'ryo', 'level_req', 'duration_sec', 'animation_frames']):
             logger.warning(f"Mission definition for rank '{rank}' is incomplete or invalid. Skipping.")
             continue

        if player.level >= details['level_req']:
            keyboard.append([
                InlineKeyboardButton(
                    f"{rank}: {details['name']} ({details['exp']} EXP, {details['ryo']} Ryo, {details['duration_sec']}s)",
                    callback_data=f"mission_start_{rank}"
                )
            ])
            found_available = True
        else:
            keyboard.append([
                InlineKeyboardButton(
                    f"🔒 {rank}: {details['name']} (Lvl {details['level_req']} Req)",
                    callback_data="mission_locked" # Simple callback for locked
                )
            ])

    if not found_available and not keyboard: # If MISSIONS was empty or all were invalid
         await update.message.reply_text("There are currently no missions defined.")
         return
    elif not found_available: # If missions exist but player level too low for all
         await update.message.reply_text("You don't meet the level requirements for any available missions yet.")
         # Still show the locked missions
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
    if not query or not user_id: return
    logger.debug(f"Received mission callback from {user_id}: {query.data}")
    await query.answer()

    if query.data == "mission_locked":
        # Send ephemeral message or just ignore? Let's send message.
        await context.bot.send_message(user_id, "You do not meet the level requirement for this mission.")
        return

    try:
        mission_rank = query.data.split('_')[-1]
    except IndexError:
        logger.warning(f"Could not parse mission rank from callback data: {query.data}")
        await query.edit_message_text("Error processing mission selection.")
        return

    mission = MISSIONS.get(mission_rank)
    if not mission or not isinstance(mission, dict): # Check if mission exists and is a dict
        logger.warning(f"Invalid or non-existent mission rank '{mission_rank}' received from {user_id}.")
        await query.edit_message_text("Invalid mission selected.")
        return

    # --- FIX: Added await ---
    player = await get_player(user_id)
    if not player:
        await query.edit_message_text("Player data not found. Please /start again.")
        return

    # Double check level req just in case
    if player.level < mission.get('level_req', 999):
         await context.bot.send_message(user_id, "You no longer meet the level requirement for this mission.")
         # Optionally re-edit the original message back to the board? Complex.
         return

    if player.current_mission:
        await query.edit_message_text(f"You are already busy: {player.current_mission}")
        return

    # Validate essential mission data before scheduling
    if not all(k in mission for k in ['duration_sec', 'animation_frames', 'name', 'exp', 'ryo']) or not mission['animation_frames']:
         logger.error(f"Mission '{mission_rank}' definition is incomplete. Cannot start.")
         await query.edit_message_text("This mission is currently unavailable due to a configuration error.")
         return

    # Use timezone aware datetime
    run_at = datetime.now(timezone.utc) + timedelta(seconds=mission['duration_sec'])

    # Send initial animation frame
    start_frame = mission['animation_frames'][0]
    try:
        # Edit the original message (mission board)
        message = await query.edit_message_text(start_frame, parse_mode=ParseMode.MARKDOWN)

        # Ensure job_queue is available
        if not context.job_queue:
            logger.error("JobQueue is not available in context. Cannot schedule mission completion.")
            await message.edit_text("Error: Cannot schedule mission completion. Please contact admin.")
            return

        # Schedule the completion job ONLY if message edit succeeded
        job_name = f"mission_{user_id}_{mission_rank}_{int(datetime.now().timestamp())}" # More unique job name
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

        # Set player status AFTER scheduling
        player.current_mission = mission['name']
        player.mark_modified()
        player.save() # Save the change immediately

    except Exception as e:
        logger.error(f"Failed to start mission '{mission_rank}' for player {user_id}: {e}", exc_info=True)
        try:
             # Try to revert message or inform user
             await query.message.reply_text("Failed to start the mission due to an error.")
             # Optionally try editing original message back? Difficult state management.
        except Exception as report_err:
             logger.error(f"Failed also to send error report to user {user_id}: {report_err}")


async def _mission_completion_job(context: ContextTypes.DEFAULT_TYPE):
    """The job that runs when a mission is complete."""
    job_data = context.job.data
    user_id = job_data.get('user_id')
    mission_rank = job_data.get('mission_rank')
    chat_id = job_data.get('chat_id')
    message_id = job_data.get('message_id')

    # Validate job data
    if not all([user_id, mission_rank, chat_id, message_id]):
         logger.error(f"Mission completion job missing essential data: {job_data}")
         return

    logger.info(f"Running mission completion job for user {user_id}, mission {mission_rank}.")

    # --- FIX: Added await ---
    player = await get_player(user_id)
    mission = MISSIONS.get(mission_rank)

    # Check player exists
    if not player:
        logger.warning(f"Player {user_id} not found for mission completion job.")
        return
    # Check mission exists and is valid
    if not mission or not isinstance(mission, dict) or 'name' not in mission:
         logger.error(f"Mission rank '{mission_rank}' not found or invalid in MISSIONS for completion job.")
         # Attempt to clear player status if it seems related
         if player.current_mission and mission_rank in player.current_mission:
              logger.warning(f"Clearing potentially related mission status '{player.current_mission}' for player {user_id}")
              player.current_mission = None
              player.mark_modified()
              player.save()
         return

    # Check if player is still on THIS mission (prevent race conditions)
    if player.current_mission != mission['name']:
         logger.warning(f"Player {user_id} is no longer on mission '{mission['name']}' (current: {player.current_mission}). Job aborted.")
         return

    bot = context.bot # Get bot instance from context

    # --- Animate Completion ---
    try:
        frames = mission.get('animation_frames', [])
        # Use frames starting from the second one for animation
        animation_frames = frames[1:] if len(frames) > 1 else frames # Use all if only 1 frame total

        if not animation_frames:
             logger.warning(f"No animation frames (or only 1) defined for mission '{mission_rank}'. Skipping animation.")
        else:
            # Calculate duration per frame dynamically
            total_anim_duration = max(5.0, mission.get('duration_sec', 30) * 0.2) # Default 30s if duration missing
            duration_per_frame = max(config.ANIMATION_DELAY, total_anim_duration / len(animation_frames))

            logger.debug(f"Animating mission completion for {user_id}. Frames: {len(animation_frames)}, Delay: {duration_per_frame:.2f}s")

            # Edit message through frames
            for frame in animation_frames:
                try:
                    await bot.edit_message_text(
                        chat_id=chat_id, message_id=message_id,
                        text=frame, parse_mode=ParseMode.MARKDOWN
                    )
                    await asyncio.sleep(duration_per_frame)
                except Exception as edit_err:
                    logger.warning(f"Failed to edit mission message {message_id} (frame): {edit_err}. Stopping animation.")
                    break # Stop trying to animate if one edit fails

            # Ensure the final frame is shown if animation was interrupted or short
            final_frame = frames[-1] if frames else "Mission animation error."
            try:
                 await bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=final_frame, parse_mode=ParseMode.MARKDOWN)
            except Exception as final_edit_err:
                 logger.warning(f"Failed to set final animation frame for mission {message_id}: {final_edit_err}")

    except Exception as anim_e:
        logger.error(f"Mission animation failed unexpectedly for user {user_id}: {anim_e}", exc_info=True)
        # Attempt to set final frame as fallback even if main animation logic failed
        try:
             final_frame = mission.get('animation_frames', ["Mission error."])[-1]
             await bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=final_frame, parse_mode=ParseMode.MARKDOWN)
        except Exception as fallback_e:
             logger.error(f"Failed to set fallback final frame for mission {message_id} after error: {fallback_e}")

    # --- Grant Rewards ---
    try:
        exp_reward = mission.get('exp', 0)
        ryo_reward = mission.get('ryo', 0)

        # Use player object's method to add exp and handle level ups
        level_up_msg, exp_msg = player.add_exp(exp_reward) # add_exp handles mark_modified

        player.ryo += ryo_reward
        player.current_mission = None # Clear mission status
        player.mark_modified() # Ensure marked if ryo changed or mission cleared
        player.save() # Save all changes

        logger.info(f"Mission '{mission_rank}' completed by player {user_id}. Rewarded {exp_reward} EXP, {ryo_reward} Ryo.")

        reward_message = f"**Mission Complete: {mission['name']}**\n{exp_msg}\nYou gained {ryo_reward} Ryo 💰."
        if level_up_msg:
             reward_message += f"\n\n{level_up_msg}" # Append level up details if any

        # Send rewards in a new message
        await bot.send_message(chat_id, reward_message, parse_mode=ParseMode.MARKDOWN)

    except Exception as reward_e:
         logger.error(f"Failed to grant rewards for mission '{mission_rank}', user {user_id}: {reward_e}", exc_info=True)
         # Try to inform the user
         await bot.send_message(chat_id, f"An error occurred while granting rewards for mission {mission.get('name', mission_rank)}. Please contact support.")
         # Still attempt to clear mission status
         if player and player.current_mission == mission.get('name'):
              player.current_mission = None
              player.mark_modified()
              player.save()


# --- Training Handlers ---

async def train_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the /train command."""
    user_id = update.effective_user.id
    if not user_id: return
    logger.debug(f"Received /train command from {user_id} with args: {context.args}")
    # --- FIX: Added await ---
    player = await get_player(user_id)
    if not player:
        await update.message.reply_text("You must /start your journey first.")
        return

    if player.current_mission:
        await update.message.reply_text(f"You cannot train while busy: {player.current_mission}.")
        return

    args = context.args
    if not args:
        # Build available training types dynamically
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
    training = TRAINING_ANIMATIONS.get(train_type) # Use .get for safer access

    if not training or not isinstance(training, dict):
        valid_types = ", ".join([f"`{k}`" for k in TRAINING_ANIMATIONS.keys()])
        await update.message.reply_text(f"Invalid training type '{train_type}'. Valid types: {valid_types}.", parse_mode=ParseMode.MARKDOWN)
        return

    # Validate training data structure
    required_keys = ['duration_sec', 'frames', 'stat', 'gain', 'display_name', 'description']
    if not all(k in training for k in required_keys) or not training['frames']:
         logger.error(f"Training definition for '{train_type}' is incomplete or invalid.")
         await update.message.reply_text("This training is currently unavailable due to configuration error.")
         return

    run_at = datetime.now(timezone.utc) + timedelta(seconds=training['duration_sec'])

    start_frame = training['frames'][0]
    try:
        message = await update.message.reply_text(start_frame, parse_mode=ParseMode.MARKDOWN)

        # Ensure job_queue is available
        if not context.job_queue:
            logger.error("JobQueue is not available in context. Cannot schedule training completion.")
            await message.edit_text("Error: Cannot schedule training completion. Please contact admin.")
            return

        # Schedule the completion job
        job_name = f"train_{user_id}_{train_type}_{int(datetime.now().timestamp())}" # Unique job name
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

        # Set player status AFTER scheduling
        player.current_mission = f"Training {training.get('display_name', train_type.capitalize())}" # Use mission slot
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

    # Validate data
    if not all([user_id, train_type, chat_id, message_id]):
         logger.error(f"Training completion job missing essential data: {job_data}")
         return

    logger.info(f"Running training completion job for user {user_id}, type {train_type}.")

    # --- FIX: Added await ---
    player = await get_player(user_id)
    training = TRAINING_ANIMATIONS.get(train_type)

    # Check player and training config
    if not player:
        logger.warning(f"Player {user_id} not found for training job.")
        return
    if not training or not isinstance(training, dict):
        logger.error(f"Training type '{train_type}' not found or invalid in TRAINING_ANIMATIONS.")
        # Clear status if it seems related
        if player.current_mission and train_type in player.current_mission:
             player.current_mission = None; player.mark_modified(); player.save()
        return

    # Check required keys for rewards
    if not all(k in training for k in ['stat', 'gain', 'display_name']):
         logger.error(f"Training definition for '{train_type}' missing reward keys (stat/gain/display_name).")
         if player.current_mission and train_type in player.current_mission:
              player.current_mission = None; player.mark_modified(); player.save()
         return

    # Check if player is still training this
    expected_status = f"Training {training.get('display_name', train_type.capitalize())}"
    if player.current_mission != expected_status:
         logger.warning(f"Player {user_id} is no longer training '{train_type}' (current: {player.current_mission}). Job aborted.")
         return

    bot = context.bot

    # --- Play Animation ---
    try:
        frames = training.get('frames', [])
        if not frames:
             logger.warning(f"No animation frames defined for training '{train_type}'.")
        else:
            total_anim_duration = max(3.0, training.get('duration_sec', 15) * 0.2) # Default 15s
            duration_per_frame = max(config.ANIMATION_DELAY, total_anim_duration / len(frames))

            logger.debug(f"Animating training completion for {user_id}. Frames: {len(frames)}, Delay: {duration_per_frame:.2f}s")

            for frame in frames:
                try:
                    await bot.edit_message_text(
                        chat_id=chat_id, message_id=message_id,
                        text=frame, parse_mode=ParseMode.MARKDOWN
                    )
                    await asyncio.sleep(duration_per_frame)
                except Exception as edit_err:
                    logger.warning(f"Failed to edit training message {message_id} (frame): {edit_err}. Stopping animation.")
                    # Ensure last frame is shown if possible
                    try:
                         await bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=frames[-1], parse_mode=ParseMode.MARKDOWN)
                    except: pass
                    break

    except Exception as anim_e:
        logger.error(f"Training animation failed unexpectedly for user {user_id}: {anim_e}", exc_info=True)
        # Attempt to set final frame as fallback
        try:
             final_frame = training.get('frames', ["Training animation error."])[-1]
             await bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=final_frame, parse_mode=ParseMode.MARKDOWN)
        except Exception as fallback_e:
             logger.error(f"Failed to set fallback final frame for training {message_id}: {fallback_e}")


    # --- Grant Rewards ---
    try:
        stat_to_gain = training['stat']
        gain_amount = training['gain']

        if hasattr(player, stat_to_gain):
            current_value = getattr(player, stat_to_gain)
            # Ensure gain is positive integer/float
            if isinstance(gain_amount, (int, float)) and gain_amount > 0:
                 setattr(player, stat_to_gain, current_value + gain_amount)
                 player.mark_modified()
                 logger.info(f"Player {user_id} trained {train_type}, {stat_to_gain} increased by {gain_amount}.")

                 # Recalculate dependent stats (HP/Chakra)
                 hp_updated = False
                 chakra_updated = False
                 if stat_to_gain == 'stamina':
                     player.max_hp = 100 + (player.stamina * 10)
                     logger.debug(f"Player {user_id} max HP updated to {player.max_hp}")
                     player.mark_modified()
                     hp_updated = True
                 elif stat_to_gain == 'intelligence':
                     player.max_chakra = 100 + (player.intelligence * 5)
                     logger.debug(f"Player {user_id} max Chakra updated to {player.max_chakra}")
                     player.mark_modified()
                     chakra_updated = True

                 # Optionally slightly restore HP/Chakra after training
                 if hp_updated: player.current_hp = min(player.max_hp, player.current_hp + 5) # Example: +5 HP
                 if chakra_updated: player.current_chakra = min(player.max_chakra, player.current_chakra + 5) # Example: +5 Chakra

            else:
                 logger.error(f"Invalid gain amount '{gain_amount}' for training '{train_type}'.")
        else:
             logger.error(f"Stat '{stat_to_gain}' in training '{train_type}' does not exist on Player.")

        # Clear status and save ALL changes made
        player.current_mission = None
        player.mark_modified() # Mark modified if status cleared
        player.save() # Save status clear and potential stat gains

        # Send completion message (optional, animation might be enough)
        # Example: await bot.send_message(chat_id, f"Training complete! Your {stat_to_gain} increased.")

    except Exception as reward_e:
         logger.error(f"Failed to grant rewards for training '{train_type}', user {user_id}: {reward_e}", exc_info=True)
         await bot.send_message(chat_id, f"An error occurred completing your training ({training.get('display_name', train_type)}).")
         # Attempt to clear status even if rewards failed
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
