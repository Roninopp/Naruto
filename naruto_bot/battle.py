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

# --- Damage Calculation ---

def calculate_damage(attacker: Player, defender: Player, jutsu_key: str) -> tuple[int, bool, bool, str]:
    """
    Calculates the damage dealt by a jutsu.
    Returns: (final_damage, is_critical, is_elemental_bonus, effect_str)
    """
    jutsu = JUTSU_LIBRARY.get(jutsu_key)
    if not jutsu:
        logger.error(f"Invalid jutsu_key '{jutsu_key}' passed to calculate_damage")
        return 0, False, False, ""

    # 1. Base Damage
    base_damage = jutsu['power'] + (attacker.level * 2) + (attacker.intelligence * 1.5)
    
    # 2. Village Bonus
    attacker_village_bonus, bonus_percent = attacker.get_village_bonus()
    if attacker_village_bonus == jutsu['element']:
        base_damage *= (1 + bonus_percent)
        
    # 3. Elemental Bonus
    defender_element = VILLAGES.get(defender.village, {}).get('element_bonus', 'none')
    element_bonus = ELEMENT_MATRIX[jutsu['element']][defender_element]
    
    # 4. Critical Chance
    critical_chance = (attacker.speed / 500) + 0.05
    is_critical = random.random() < critical_chance
    critical_multiplier = 1.8 if is_critical else 1.0
    
    # 5. Defense Reduction
    defense_reduction = 1 - (defender.stamina / (defender.stamina + 100))
    
    # 6. Final Damage
    final_damage = int(
        (base_damage * element_bonus * critical_multiplier * defense_reduction)
    )
    
    # 7. Handle effects
    effect_str = jutsu.get('effect')
    if effect_str:
        if effect_str == 'heal':
            final_damage = -abs(jutsu['power'])
        elif effect_str in ['evasion_up', 'defense_up', 'stun', 'accuracy_down']:
            final_damage = 0
        
    return final_damage, is_critical, element_bonus > 1.2, effect_str

# --- Battle State Manager ---

class Battle:
    """Manages the state of a single battle instance."""
    
    def __init__(self, player1: Player, player2: Player, battle_id: str):
        self.battle_id = battle_id
        self.player1_id = player1.user_id
        self.player2_id = player2.user_id
        self.turn = self.player1_id if player1.speed >= player2.speed else self.player2_id
        self.log = [f"Battle started between {player1.username} and {player2.username}!"]
        self.turn_count = 1
        
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
            'battle_effects': {}
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
    
    # FIX: Added missing method
    def update_player_resource(self, user_id: int, resource: str, value: int):
        """Updates a player's resource (HP, chakra) in battle state."""
        if user_id in self.players and resource in self.players[user_id]:
            self.players[user_id][resource] = value
        else:
            logger.warning(f"Attempted to update invalid resource '{resource}' for user {user_id} in battle {self.battle_id}")
        
    def get_battle_state_text(self) -> str:
        """Generates the main battle screen text."""
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

# --- Battle Animation Flow ---

async def battle_animation_flow(message_editor, attacker: Player, defender: Player, battle_state: Battle, jutsu_key: str):
    """
    Manages the full animation sequence for a battle turn.
    Returns: (winner_id, turn_log_message)
    """
    jutsu = JUTSU_LIBRARY.get(jutsu_key)
    
    attacker_data = battle_state.get_player_data(attacker.user_id)
    defender_data = battle_state.get_opponent_data(attacker.user_id)
    
    # --- Step 2: Hand signs animation ---
    await animate_hand_signs(message_editor, jutsu_key)
    
    # --- Step 3: Jutsu charging animation ---
    await animate_chakra_charge(message_editor)
    
    # --- Step 4: Jutsu execution animation ---
    await animate_jutsu_effect(message_editor, jutsu_key)
    
    # --- Step 5: Damage Calculation ---
    # Create temporary Player objects for calculation
    class TempPlayer:
        def __init__(self, data):
            self.user_id = attacker.user_id if data == attacker_data else defender.user_id
            self.level = data['level']
            self.intelligence = data['intelligence']
            self.speed = data['speed']
            self.stamina = data['stamina']
            self.village = data['village']
        
        def get_village_bonus(self):
            village_data = VILLAGES.get(self.village, {})
            return village_data.get('element_bonus', 'none'), village_data.get('bonus_percent', 0)
    
    temp_attacker = TempPlayer(attacker_data)
    temp_defender = TempPlayer(defender_data)
    
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
            attacker_data['battle_effects']['defense_up'] = 3
            final_message = f"🛡️ {attacker_data['username']}'s defense increased!"
        else:
            final_message = f"🌀 {attacker_data['username']} used {jutsu['name']}!"
    else:
        # Handle damage
        if is_crit:
            await animate_critical_hit(message_editor)
defender_data['current_hp'] = max(0, defender_data['current_hp'] - damage)
        
        if is_elem_bonus:
            final_message += "🔥 **It's super effective!**\n"
        
        # --- Step 7: Damage result animation ---
        await animate_damage_result(
            message_editor,
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
    elif attacker_data['current_hp'] <= 0:
        winner_id = defender.user_id
        
    return winner_id, final_message    
