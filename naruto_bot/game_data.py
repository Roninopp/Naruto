# naruto_bot/game_data.py

# Prompt 3: Villages
VILLAGES = {
    'konoha': {
        'name': 'Konoha (Leaf)', 
        'element_bonus': 'fire', 
        'bonus_percent': 0.15,
        'icon': '🍃',
        'bonus_text': 'Fire jutsu deal +15% damage'
    },
    'suna': {
        'name': 'Suna (Sand)', 
        'element_bonus': 'wind', 
        'bonus_percent': 0.15,
        'icon': '⏳',
        'bonus_text': 'Wind jutsu deal +15% damage'
    },
    'kiri': {
        'name': 'Kiri (Mist)', 
        'element_bonus': 'water', 
        'bonus_percent': 0.15,
        'icon': '🌊',
        'bonus_text': 'Water jutsu deal +15% damage'
    },
    'kumo': {
        'name': 'Kumo (Cloud)', 
        'element_bonus': 'lightning', 
        'bonus_percent': 0.15,
        'icon': '⚡',
        'bonus_text': 'Lightning jutsu deal +15% damage'
    },
    'iwa': {
        'name': 'Iwa (Stone)', 
        'element_bonus': 'earth', 
        'bonus_percent': 0.15,
        'icon': '🪨',
        'bonus_text': 'Earth jutsu deal +15% damage'
    },
}

# Prompt 4: Ranks & Levels
RANKS = [
    'Academy Student', 
    'Genin', 
    'Chunin', 
    'Jonin', 
    'Kage'
]

RANK_UP_LEVELS = {
    'Academy Student': 10,
    'Genin': 25,
    'Chunin': 40,
    'Jonin': 60,
    'Kage': float('inf')
}

def get_exp_for_level(level: int) -> int:
    """Calculates EXP needed for the next level."""
    return level * 150

STAT_GROWTH_PER_LEVEL = 6

# Prompt 7: Element Matrix
ELEMENT_MATRIX = {
    'fire': {'wind': 1.5, 'earth': 0.75, 'water': 0.5, 'lightning': 1.0, 'fire': 1.0, 'none': 1.0},
    'water': {'fire': 1.5, 'earth': 1.0, 'lightning': 0.5, 'wind': 0.75, 'water': 1.0, 'none': 1.0},
    'wind': {'lightning': 1.5, 'earth': 0.5, 'fire': 0.75, 'water': 1.0, 'wind': 1.0, 'none': 1.0},
    'earth': {'lightning': 1.5, 'water': 0.75, 'fire': 1.0, 'wind': 1.5, 'earth': 1.0, 'none': 1.0},
    'lightning': {'water': 1.5, 'earth': 0.5, 'wind': 0.75, 'fire': 1.0, 'lightning': 1.0, 'none': 1.0},
    'none': {'fire': 1.0, 'water': 1.0, 'wind': 1.0, 'earth': 1.0, 'lightning': 1.0, 'none': 1.0}
}

# Prompt 9: Jutsu System
HAND_SIGNS = ['tiger', 'snake', 'dog', 'bird', 'ram', 'boar', 'hare', 'rat', 'monkey', 'dragon']

# Jutsu Library (keeping your existing jutsus - no changes needed)
JUTSU_LIBRARY = {
    # --- FIRE JUTSUS ---
    'fireball': {
        'name': 'Fireball Jutsu',
        'signs': ['tiger', 'snake', 'bird'],
        'power': 45, 'chakra_cost': 25, 'element': 'fire', 'level_required': 5, 'discovered': True
    },
    'great_fireball': {
        'name': 'Great Fireball Jutsu',
        'signs': ['tiger', 'snake', 'ram', 'bird'],
        'power': 70, 'chakra_cost': 40, 'element': 'fire', 'level_required': 12, 'discovered': True
    },
    'fire_phoenix': {
        'name': 'Phoenix Flower Jutsu',
        'signs': ['tiger', 'snake', 'boar', 'bird', 'dragon'],
        'power': 95, 'chakra_cost': 60, 'element': 'fire', 'level_required': 25, 'discovered': False
    },
    'dragon_flame': {
        'name': 'Dragon Flame Jutsu',
        'signs': ['snake', 'dragon', 'ram', 'tiger'],
        'power': 80, 'chakra_cost': 50, 'element': 'fire', 'level_required': 20, 'discovered': False
    },
    'ash_pile_burning': {
        'name': 'Ash Pile Burning',
        'signs': ['snake', 'rat', 'snake', 'tiger'],
        'power': 110, 'chakra_cost': 70, 'element': 'fire', 'level_required': 30, 'discovered': False
    },
    'flame_bullet': {
        'name': 'Flame Bullet',
        'signs': ['tiger', 'ram'],
        'power': 30, 'chakra_cost': 15, 'element': 'fire', 'level_required': 1, 'discovered': True
    },

    # --- WATER JUTSUS ---
    'water_dragon': {
        'name': 'Water Dragon Jutsu',
        'signs': ['tiger', 'dog', 'snake', 'bird'],
        'power': 65, 'chakra_cost': 35, 'element': 'water', 'level_required': 15, 'discovered': True
    },
    'water_shark_bomb': {
        'name': 'Water Shark Bomb',
        'signs': ['tiger', 'boar', 'dog', 'dragon', 'bird'],
        'power': 100, 'chakra_cost': 65, 'element': 'water', 'level_required': 28, 'discovered': False
    },
    'hidden_mist': {
        'name': 'Hidden Mist Jutsu',
        'signs': ['ram', 'snake', 'tiger'],
        'power': 0, 'chakra_cost': 40, 'element': 'water', 'level_required': 18, 'discovered': False, 'effect': 'evasion_up'
    },
    'water_vortex': {
        'name': 'Water Vortex Jutsu',
        'signs': ['tiger', 'snake', 'rat', 'bird'],
        'power': 75, 'chakra_cost': 45, 'element': 'water', 'level_required': 22, 'discovered': False
    },
    'water_prison': {
        'name': 'Water Prison Jutsu',
        'signs': ['snake', 'ram', 'boar', 'dragon'],
        'power': 0, 'chakra_cost': 55, 'element': 'water', 'level_required': 24, 'discovered': False, 'effect': 'stun'
    },
    'water_bullet': {
        'name': 'Water Bullet',
        'signs': ['ram', 'dog'],
        'power': 30, 'chakra_cost': 15, 'element': 'water', 'level_required': 1, 'discovered': True
    },

    # --- WIND JUTSUS ---
    'wind_scythe': {
        'name': 'Wind Scythe Jutsu',
        'signs': ['snake', 'bird', 'dragon'],
        'power': 50, 'chakra_cost': 30, 'element': 'wind', 'level_required': 8, 'discovered': True
    },
    'great_breakthrough': {
        'name': 'Great Breakthrough',
        'signs': ['tiger', 'hare', 'dog', 'ram'],
        'power': 70, 'chakra_cost': 40, 'element': 'wind', 'level_required': 14, 'discovered': True
    },
    'vacuum_blade': {
        'name': 'Vacuum Blade',
        'signs': ['dog', 'bird', 'snake', 'dragon'],
        'power': 105, 'chakra_cost': 65, 'element': 'wind', 'level_required': 27, 'discovered': False
    },
    'wind_gale': {
        'name': 'Gale Palm',
        'signs': ['snake', 'ram', 'monkey'],
        'power': 60, 'chakra_cost': 35, 'element': 'wind', 'level_required': 16, 'discovered': False
    },
    'air_bullet': {
        'name': 'Air Bullet',
        'signs': ['bird', 'hare'],
        'power': 30, 'chakra_cost': 15, 'element': 'wind', 'level_required': 1, 'discovered': True
    },
    'dust_cloud': {
        'name': 'Dust Cloud Jutsu',
        'signs': ['tiger', 'ram', 'dog'],
        'power': 0, 'chakra_cost': 30, 'element': 'wind', 'level_required': 10, 'discovered': False, 'effect': 'accuracy_down'
    },

    # --- LIGHTNING JUTSUS ---
    'lightning_bolt': {
        'name': 'Lightning Bolt',
        'signs': ['boar', 'snake', 'tiger'],
        'power': 55, 'chakra_cost': 30, 'element': 'lightning', 'level_required': 9, 'discovered': True
    },
    'lightning_panther': {
        'name': 'Lightning Panther',
        'signs': ['boar', 'dog', 'snake', 'bird', 'tiger'],
        'power': 115, 'chakra_cost': 70, 'element': 'lightning', 'level_required': 30, 'discovered': False
    },
    'chidori_stream': {
        'name': 'Chidori Stream',
        'signs': ['monkey', 'dragon', 'rat', 'bird'],
        'power': 85, 'chakra_cost': 55, 'element': 'lightning', 'level_required': 24, 'discovered': False
    },
    'lightning_snake': {
        'name': 'Lightning Snake',
        'signs': ['snake', 'dragon', 'snake'],
        'power': 70, 'chakra_cost': 40, 'element': 'lightning', 'level_required': 17, 'discovered': False
    },
    'lightning_strike': {
        'name': 'Lightning Strike',
        'signs': ['rat', 'boar'],
        'power': 30, 'chakra_cost': 15, 'element': 'lightning', 'level_required': 1, 'discovered': True
    },
    'lightning_armor': {
        'name': 'Lightning Armor',
        'signs': ['tiger', 'boar', 'ram'],
        'power': 0, 'chakra_cost': 50, 'element': 'lightning', 'level_required': 20, 'discovered': False, 'effect': 'defense_up'
    },

    # --- EARTH JUTSUS ---
    'earth_wall': {
        'name': 'Earth Style Wall',
        'signs': ['tiger', 'hare', 'boar', 'dog'],
        'power': 0, 'chakra_cost': 35, 'element': 'earth', 'level_required': 10, 'discovered': True, 'effect': 'defense_up'
    },
    'mud_river': {
        'name': 'Mud River',
        'signs': ['ram', 'boar', 'snake'],
        'power': 60, 'chakra_cost': 35, 'element': 'earth', 'level_required': 13, 'discovered': True
    },
    'rock_golem': {
        'name': 'Rock Golem Jutsu',
        'signs': ['snake', 'boar', 'ram', 'dog', 'tiger'],
        'power': 120, 'chakra_cost': 80, 'element': 'earth', 'level_required': 32, 'discovered': False
    },
    'earth_dragon_bomb': {
        'name': 'Earth Dragon Bomb',
        'signs': ['ram', 'boar', 'dragon', 'bird'],
        'power': 90, 'chakra_cost': 55, 'element': 'earth', 'level_required': 26, 'discovered': False
    },
    'rock_slide': {
        'name': 'Rock Slide',
        'signs': ['boar', 'dog', 'ram'],
        'power': 75, 'chakra_cost': 45, 'element': 'earth', 'level_required': 19, 'discovered': False
    },
    'stone_bullet': {
        'name': 'Stone Bullet',
        'signs': ['dog', 'boar'],
        'power': 30, 'chakra_cost': 15, 'element': 'earth', 'level_required': 1, 'discovered': True
    },

    # --- NON-ELEMENTAL ---
    'substitution': {
        'name': 'Substitution Jutsu',
        'signs': ['ram', 'boar', 'tiger'],
        'power': 0, 'chakra_cost': 20, 'element': 'none', 'level_required': 3, 'discovered': True, 'effect': 'dodge'
    },
    'clone_jutsu': {
        'name': 'Clone Jutsu',
        'signs': ['ram', 'snake', 'tiger'],
        'power': 0, 'chakra_cost': 15, 'element': 'none', 'level_required': 1, 'discovered': True, 'effect': 'distract'
    },
    'chakra_heal': {
        'name': 'Chakra Heal',
        'signs': ['rat', 'ram', 'snake'],
        'power': 50, 'chakra_cost': 30, 'element': 'none', 'level_required': 8, 'discovered': True, 'effect': 'heal'
    }
}

# Prompt 12: Element Animations
ELEMENT_ANIMATIONS = {
    'fire': [
        "🔥 **FIRE STYLE!** 🔥",
        "🔥🔥 Igniting! 🔥🔥", 
        "🔥🔥🔥 **INFERNO!** 🔥🔥🔥",
        "💥 **BURNING DAMAGE!** ❤️‍🔥"
    ],
    'water': [
        "💧 **WATER STYLE!** 💧",
        "🌊 Waves forming! 🌊",
        "🌊💦 **TSUNAMI!** 💦🌊",
        "💦 **SOAKING HIT!** 🌊"
    ],
    'lightning': [
        "⚡ **LIGHTNING STYLE!** ⚡",
        "⚡⚡ Charging! ⚡⚡",
        "⚡⚡⚡ **THUNDER STRIKE!** ⚡⚡⚡", 
        "💢 **SHOCK DAMAGE!** 🌀"
    ],
    'wind': [
        "💨 **WIND STYLE!** 💨",
        "💨💨 Gusts building! 💨💨",
        "💨💨💨 **TYPHOON!** 💨💨💨",
        "🌪 **SLASHING WIND!** 🎯"
    ],
    'earth': [
        "⛰ **EARTH STYLE!** ⛰",
        "⛰⛰ Ground shaking! ⛰⛰",
        "⛰⛰⛰ **QUAKE!** ⛰⛰⛰",
        "💢 **CRUSHING DAMAGE!** 🪨"
    ],
    'none': [
        "🌀 **CHAKRA MANIPULATION!** 🌀",
        "💫 Focusing energy...",
        "✨ **JUTSU ACTIVATED!** ✨"
    ]
}

# Prompt 14: Missions
MISSIONS = {
    'D-Rank': {
        'name': 'Weed a Garden',
        'exp': 50, 'ryo': 100, 'level_req': 1,
        'duration_sec': 60 * 5,
        'animation_frames': [
            "🪴 You begin weeding the client's garden...",
            "🌿 This is tedious work...",
            "🌱 Almost done...",
            "✅ **D-Rank Mission Completed!**\nYou earned 50 EXP and 100 Ryo."
        ]
    },
    'C-Rank': {
        'name': 'Escort a Client',
        'exp': 150, 'ryo': 300, 'level_req': 10,
        'duration_sec': 60 * 15,
        'animation_frames': [
            "🛡️ You begin escorting the client...",
            "🌲 Traveling through the woods...",
            "⚔️ Ambush! You fight off a group of bandits!",
            "✅ **C-Rank Mission Completed!**\nThe client is safe. You earned 150 EXP and 300 Ryo."
        ]
    },
    'B-Rank': {
        'name': 'Investigate Ruins',
        'exp': 400, 'ryo': 800, 'level_req': 20,
        'duration_sec': 60 * 30,
        'animation_frames': [
            "🔍 You arrive at the ancient ruins to investigate...",
            "📖 You find a strange scroll...",
            "💥 Enemy ninja appear! You defend yourself and escape!",
            "✅ **B-RANK MISSION COMPLETED!**\nYou report your findings. You earned 400 EXP and 800 Ryo."
        ]
    }
}

# Prompt 15: Training (FIX: Added missing fields)
TRAINING_ANIMATIONS = {
    'chakra_control': {
        'duration_sec': 60 * 3,
        'stat': 'intelligence',  # FIX: Changed from 'max_chakra' to actual stat
        'gain': 2,
        'display_name': 'Chakra Control',
        'description': 'Increase Intelligence (+Max Chakra)',
        'frames': [
            "🧘 Meditating...",
            "💫 Chakra flowing...", 
            "✨ Control improving!",
            "🎯 **Training complete! Intelligence +2!**"
        ]
    },
    'taijutsu': {
        'duration_sec': 60 * 3,
        'stat': 'strength',
        'gain': 3,
        'display_name': 'Taijutsu',
        'description': 'Increase Strength',
        'frames': [
            "🥋 Practicing forms...",
            "💥 Sparring session!",
            "⚡ Power increasing!",
            "🎯 **Training complete! Strength +3!**"
        ]
    },
    'stamina': {
        'duration_sec': 60 * 3,
        'stat': 'stamina',
        'gain': 3,
        'display_name': 'Stamina',
        'description': 'Increase Stamina (+Max HP)',
        'frames': [
            "🏃 Running laps around the village...",
            "🥵 Pushing your limits...",
            "💪 Feeling stronger!",
            "🎯 **Training complete! Stamina +3!**"
        ]
    },
    'speed': {
        'duration_sec': 60 * 3,
        'stat': 'speed',
        'gain': 3,
        'display_name': 'Speed',
        'description': 'Increase Speed (Critical Hit chance)',
        'frames': [
            "🏃‍♂️ Sprint training begins...",
            "💨 Moving faster and faster!",
            "⚡ Lightning speed!",
            "🎯 **Training complete! Speed +3!**"
        ]
    }
}
