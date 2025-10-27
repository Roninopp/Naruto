# naruto_bot/battle.py
import random
import logging
import asyncio
import json
from datetime import datetime
from .models import Player
from .config import config
from .game_data import ELEMENT_MATRIX, JUTSU_LIBRARY, VILLAGES
from .services import get_jutsu_by_name, health_bar, chakra_bar, safe_animation
from .animations import (
    animate_hand_signs, 
    animate_chakra_charge, 
    animate_jutsu_effect,
    animate_critical_hit, 
    animate_damage_result
)

logger = logging.getLogger(__name__)

# --- Damage Calculation (Prompt 8) ---

def calculate_damage(attacker: Player, defender: Player, jutsu_key: str) -> tuple[int, bool, bool, str]:
    """
    Calculates the damage dealt by a jutsu.
    Returns: (final_damage, is_critical, is_elemental_bonus, effect_str)
    """
    jutsu = JUTSU_LIBRARY.get(jutsu_key)
    if not jutsu:
        logger.error(f"Invalid jutsu_key '{jutsu_key}' passed to calculate_damage")
        return 0, False, False, ""

    # 1. Base Damage (using Intelligence for Ninjutsu)
    base_damage = jutsu['power'] + (attacker.level * 2) + (attacker.intelligence * 1.5)
    
    # 2. Village Bonus (Prompt 3)
    attacker_village_bonus, bonus_percent = attacker.get_village_bonus()
    if attacker_village_bonus == jutsu['element']:
        base_damage *= (1 + bonus_percent)
        
    # 3. Elemental Bonus (Prompt 7)
    # Get defender's primary element from their village
    defender_element = VILLAGES.get(defender.village, {}).get('element_bonus', 'none')
    element_bonus = ELEMENT_MATRIX[jutsu['element']][defender_element]
    
    # 4. Critical Chance (Prompt 8, modified to use speed)
    critical_chance = (attacker.speed / 500) + 0.05  # 5% base + speed bonus
    is_critical = random.random() < critical_chance
    critical_multiplier = 1.8 if is_critical else 1.0
    
    # 5. Defense Reduction (using defender's Stamina)
    defense_reduction = 1 - (defender.stamina / (defender.stamina + 100))
    
    # 6. Final Damage
    final_damage = int(
        (base_damage * element_bonus * critical_multiplier * defense_reduction)
    )
    
    # 7. Handle non-damage "effects"
    effect_str = jutsu.get('effect')
    if effect_str:
        if effect_str == 'heal':
            final_damage = -abs(jutsu['power']) # Negative damage signifies healing
        elif effect_str in ['evasion_up', 'defense_up', 'stun', 'accuracy_down']:
            # These are handled by applying a battle effect, damage is 0
            final_damage = 0
        
    return final_damage, is_critical, element_bonus > 1.2, effect_str

# --- Battle State Manager ---

class Battle:
    """
    Manages the state of a single battle instance.
    This object is cached in Redis.
    """
    def __init__(self, player1: Player, player2: Player, battle_id: str):
        self.battle_id = battle_id
        self.player1_id = player1.user_id
        self.player2_id = player2.user_id
        self.turn = self.player1_id if player1.speed >= player2.speed else self.player2_id
        self.log = [f"Battle started between {player1.username} and {player2.username}!"]
        self.turn_count = 1
        
        # Store player data needed for the battle to reduce DB calls
        self.players = {
            player1.user_id: self._serialize_player(player1),
            player2.user_id: self._serialize_player(player2)
        }
        self.battle_message_id = None
        self.chat_id = None
        self.last_action_time = datetime.now()

    def _serialize_player(self, player: Player) -> dict:
        """Stores a snapshot of player data for battle."""
        return {
            'username': player.username,
            'level': player.level,
            'current_hp': player.current_hp,
            'max_hp': player.max_hp,
            'current_chakra': player.current_chakra,
            'max_chakra': player.max_chakra,
            'strength': player.strength,
            'speed': player.speed,
            'intelligence': player.intelligence,
            'stamina': player.stamina,
            'village': player.village,
            'known_jutsus': player.known_jutsus,
            'battle_effects': {} # e.g., {'defense_up': 2}
        }

    def get_player_data(self, user_id: int) -> dict:
        return self.players[user_id]

    def get_opponent_data(self, user_id: int) -> dict:
        opponent_id = self.player2_id if user_id == self.player1_id else self.player1_id
        return self.players[opponent_id]

    def switch_turn(self):
        self.turn = self.player2_id if self.turn == self.player1_id else self.player1_id
        self.turn_count += 1
        self.last_action_time = datetime.now()
        
    def get_battle_state_text(self) -> str:
        """Generates the main battle screen text (part of Prompt 5)."""
        p1 = self.get_player_data(self.player1_id)
        p2 = self.get_player_data(self.player2_id)
        
        p1_turn = "▶️" if self.turn == self.player1_id else "  "
        p2_turn = "▶️" if self.turn == self.player2_id else "  "
        
        return (
            f"⚔️ **BATTLE! (Turn {self.turn_count})** ⚔️\n\n"
            f"{p1_turn} {p1['username']} [Lvl {p1['level']}]\n"
            f"❤️ {health_bar(p1['current_hp'], p1['max_hp'])}\n"
            f"🔵 {chakra_bar(p1['current_chakra'], p1['max_chakra'])}\n\n"
            f"{p2_turn} {p2['username']} [Lvl {p2['level']}]\n"
            f"❤️ {health_bar(p2['current_hp'], p2['max_hp'])}\n"
            f"🔵 {chakra_bar(p2['current_chakra'], p2['max_chakra'])}"
        )

# --- Battle Animation Flow (Prompt 5) ---

async def battle_animation_flow(message, attacker: Player, defender: Player, battle: Battle, jutsu_key: str):
    """
    Manages the full animation sequence for a battle turn.
    """
    jutsu = JUTSU_LIBRARY.get(jutsu_key)
    
    # Get player/opponent data *from the battle object*
    attacker_data = battle.get_player_data(attacker.user_id)
    defender_data = battle.get_opponent_data(attacker.user_id)
    
    # --- Step 1: Initial battle screen (Handled by the command) ---
    # message.edit_text(...) is called before this function
    
    # --- Step 2: Hand signs animation (Prompt 6) ---
    await animate_hand_signs(message, jutsu_key)
    
    # --- Step 3: Jutsu charging animation (Prompt 6) ---
    await animate_chakra_charge(message)
    
    # --- Step 4: Jutsu execution animation (Prompt 12) ---
    await animate_jutsu_effect(message, jutsu_key)
    
    # --- Step 5: Damage Calculation (Prompt 8) ---
    # Create temporary Player objects for calculation
    # This is a bit of a hack, but safer than passing full objects
    temp_attacker = Player(attacker_data) # Re-hydrating from dict
    temp_defender = Player(defender_data) # Re-hydrating from dict
    
    damage, is_crit, is_elem_bonus, effect = calculate_damage(temp_attacker, temp_defender, jutsu_key)

    # --- Step 6: Apply Damage/Effects to Battle State ---
    final_message = ""
    if effect:
        # Handle special effects
        if effect == 'heal':
            heal_amount = abs(damage)
            attacker_data['current_hp'] = min(attacker_data['max_hp'], attacker_data['current_hp'] + heal_amount)
            final_message = f"✨ {attacker_data['username']} heals for {heal_amount} HP!"
        elif effect == 'defense_up':
            attacker_data['battle_effects']['defense_up'] = 3 # Lasts 3 turns
            final_message = f"🛡️ {attacker_data['username']}'s defense increased!"
        # ... other effects
        else:
            final_message = f"🌀 {attacker_data['username']} used {jutsu['name']}!"
    else:
        # Handle damage
        if is_crit:
            await animate_critical_hit(message)
        
        defender_data['current_hp'] = max(0, defender_data['current_hp'] - damage)
        
        if is_elem_bonus:
            final_message += "🔥 **It's super effective!**\n"
        
        # --- Step 7: Damage result animation (Prompt 5) ---
        await animate_damage_result(
            message,
            attacker_data['username'],
            defender_data['username'],
            damage,
            defender_data['current_hp'],
            defender_data['max_hp']
        )
        final_message += f"💥 {attacker_data['username']}'s {jutsu['name']} hits {defender_data['username']} for **{damage}** damage!"

    # --- Step 8: Check for Winner ---
    winner_id = None
    if defender_data['current_hp'] <= 0:
        winner_id = attacker.user_id
    elif attacker_data['current_hp'] <= 0: # e.g., from a reflect damage
        winner_id = defender.user_id
        
    return winner_id, final_message
