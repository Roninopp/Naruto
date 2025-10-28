# naruto_bot/handlers/__init__.py

from .core_handlers import register_core_handlers
from .activity_handlers import register_activity_handlers
from .jutsu_handlers import register_jutsu_handlers  # FIX: Changed from jutsus_handlers
from .battle_handlers import register_battle_handlers

def register_all_handlers(application):
    """A helper function to register all handlers with the bot application."""
    register_core_handlers(application)
    register_activity_handlers(application)
    register_jutsu_handlers(application)
    register_battle_handlers(application)
