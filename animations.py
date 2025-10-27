# naruto_bot/animations.py
import asyncio
import logging
from telegram.ext import ContextTypes
from telegram.helpers import escape_markdown
from .config import config
from .game_data import ELEMENT_ANIMATIONS, JUTSU_LIBRARY, TRAINING_ANIMATIONS, MISSIONS
from .services import get_hand_signs_for_jutsu, health_bar

logger = logging.getLogger(__name__)
ANIMATION_DELAY = config.ANIMATION_DELAY

# --- Battle Animations (Prompts 5, 6, 12, 13) ---

async def animate_hand_signs(message, jutsu_key: str):
    """Animates the forming of hand signs (Prompt 6)."""
    signs = get_hand_signs_for_jutsu(jutsu_key)
    if not signs:
        return
        
    base_text = "🤲 Forming hand signs...\n"
    current_signs = ""
    for sign in signs:
        current_signs += f"→ {sign.capitalize()} "
        frame = base_text + current_signs
        await message.edit_text(frame)
        await asyncio.sleep(ANIMATION_DELAY)

async def animate_chakra_charge(message):
    """Animates the chakra charging progress bar (Prompt 6)."""
    charge_frames = [
        "Chakra Gathering: [▱▱▱▱▱▱▱▱▱▱] 0%",
        "Chakra Gathering: [▰▱▱▱▱▱▱▱▱▱] 20%",
        "Chakra Gathering: [▰▰▰▱▱▱▱▱▱▱] 40%",
        "Chakra Gathering: [▰▰▰▰▰▱▱▱▱▱] 60%",
        "Chakra Gathering: [▰▰▰▰▰▰▰▱▱▱] 80%",
        "Chakra Gathering: [▰▰▰▰▰▰▰▰▰▰] 100% READY! 💫"
    ]
    for frame in charge_frames:
        await message.edit_text(frame)
        await asyncio.sleep(ANIMATION_DELAY * 0.8) # Slightly faster

async def animate_fireball(message):
    """Specific jutsu animation for Fireball (Prompt 6)."""
    fire_frames = [
        "🔥 **Fireball Forming!**",
        "🔥🔥 Growing...",
        "🔥🔥🔥 Getting larger!",
        "🔥🔥🔥🔥 **FIREBALL JUTSU!**",
        "(🔥=====>) Launching!",
        "(🔥=======>) Flying!",
        "(🔥=========>) 💥 **DIRECT HIT!**"
    ]
    for frame in fire_frames:
        await message.edit_text(frame)
        await asyncio.sleep(ANIMATION_DELAY)

# Dictionary to map specific jutsu keys to their unique animation functions
SPECIFIC_JUTSU_ANIMATIONS = {
    'fireball': animate_fireball,
    'great_fireball': animate_fireball,
    # Can add more: 'water_dragon': animate_water_dragon, etc.
}

async def animate_jutsu_effect(message, jutsu_key: str):
    """
    Generic jutsu animation. Plays element animation (Prompt 12)
    and then a specific animation if one exists (Prompt 6).
    """
    jutsu = JUTSU_LIBRARY.get(jutsu_key)
    if not jutsu:
        return
        
    element = jutsu.get('element', 'none')
    
    # 1. Play Element Animation (Prompt 12)
    element_frames = ELEMENT_ANIMATIONS.get(element, ELEMENT_ANIMATIONS['none'])
    for frame in element_frames:
        await message.edit_text(frame)
        await asyncio.sleep(ANIMATION_DELAY)
        
    # 2. Play Specific Jutsu Animation (if it exists)
    specific_anim_func = SPECIFIC_JUTSU_ANIMATIONS.get(jutsu_key)
    if specific_anim_func:
        await specific_anim_func(message)

async def animate_critical_hit(message):
    """Animates a critical hit (Prompt 13)."""
    crit_frames = [
        "✨ ✨ ✨",
        "💥 **CRITICAL HIT!** 💥",
        "⭐ **DEVASTATING BLOW!** ⭐",
        "🎯 **WEAK POINT HIT!** 🎯",
        "✨ ✨ ✨"
    ]
    for frame in crit_frames:
        await message.edit_text(frame)
        await asyncio.sleep(ANIMATION_DELAY * 0.7) # Faster

async def animate_damage_result(message, attacker_name, defender_name, damage, defender_hp, defender_max_hp):
    """Animates the damage result and updates health bar (Prompt 5)."""
    damage_frames = [
        f"💥 {attacker_name} hits {defender_name} for **{damage}** damage!",
        f"💥 {attacker_name} hits {defender_name} for **{damage}** damage!\n{defender_name} HP: {health_bar(defender_hp, defender_max_hp)}",
        f"💥 {attacker_name} hits {defender_name} for **{damage}** damage!\n{defender_name} HP: {health_bar(defender_hp, defender_max_hp)}",
    ]
    for frame in damage_frames:
        await message.edit_text(frame)
        await asyncio.sleep(ANIMATION_DELAY)

# --- Other Game Animations ---

async def animate_jutsu_discovery(message, player_name, new_jutsu_dict):
    """Animates discovering a new jutsu (Prompt 10)."""
    jutsu_name = new_jutsu_dict.get('name', 'Unknown Jutsu').upper()
    
    discovery_frames = [
        f"{escape_markdown(player_name)} tries unusual hand signs...",
        f"Signs: {' → '.join(new_jutsu_dict['signs'])}",
        "💫 Chakra reacts strangely!",
        "✨ Something new is forming!",
        "🌟 **NEW JUTSU DISCOVERED!**",
        f"🎉 **{escape_markdown(jutsu_name)}!**",
        f"💥 Power: {new_jutsu_dict['power']} | Cost: {new_jutsu_dict['chakra_cost']}",
        "📚 This technique is now recorded in your scroll!"
    ]
    
    for frame in discovery_frames:
        await message.edit_text(frame)
        await asyncio.sleep(ANIMATION_DELAY * 1.5)

async def animate_activity(message, activity_type: str, activity_key: str):
    """
    Handles animations for long-running activities like Missions and Training.
    (From Prompts 14 & 15)
    """
    if activity_type == 'mission':
        activity_data = MISSIONS.get(activity_key)
    elif activity_type == 'training':
        activity_data = TRAINING_ANIMATIONS.get(activity_key)
    else:
        return
        
    if not activity_data:
        await message.edit_text("Unknown activity.")
        return
        
    frames = activity_data['frames']
    duration_per_frame = activity_data['duration_sec'] / len(frames)
    
    for frame in frames:
        await message.edit_text(frame)
        await asyncio.sleep(duration_per_frame)
