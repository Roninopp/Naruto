# naruto_bot/handlers/__init__.py
# This file makes 'handlers' a Python package.

# Import all handlers to make them accessible
from .core_handlers import register_core_handlers
from .activity_handlers import register_activity_handlers
from .jutsus_handlers import register_jutsu_handlers # RENAME FIX HERE!
from .battle_handlers import register_battle_handlers

def register_all_handlers(application):
    """A helper function to register all handlers with the bot application."""
    register_core_handlers(application)
    register_activity_handlers(application)
    register_jutsu_handlers(application)
    register_battle_handlers(application)
