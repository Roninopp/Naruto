# naruto_bot/scheduler.py
import logging
import sqlite3
import json
from datetime import datetime, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from .config import config
from .database import get_db_connection
from .cache import cache_manager

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler(timezone="UTC")

async def regenerate_resources():
    """Periodically regenerates HP and Chakra for all players."""
    logger.info("[Scheduler] Running 'regenerate_resources' job...")
    
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("SELECT user_id, current_hp, max_hp, current_chakra, max_chakra FROM players")
            players = cursor.fetchall()
            
            update_data = []
            for player in players:
                user_id = player['user_id']
                
                # FIX: Added await
                if await cache_manager.is_in_battle(user_id):
                    continue
                    
                hp_regen = int(player['max_hp'] * 0.05)
                chakra_regen = int(player['max_chakra'] * 0.10)
                
                new_hp = min(player['max_hp'], player['current_hp'] + hp_regen)
                new_chakra = min(player['max_chakra'], player['current_chakra'] + chakra_regen)
                
                if new_hp != player['current_hp'] or new_chakra != player['current_chakra']:
                    update_data.append((new_hp, new_chakra, user_id))
            
            if update_data:
                cursor.executemany(
                    "UPDATE players SET current_hp = ?, current_chakra = ? WHERE user_id = ?",
                    update_data
                )
                conn.commit()
                logger.info(f"[Scheduler] Regenerated resources for {len(update_data)} players.")
            
            # FIX: Added await
            for _, _, user_id in update_data:
                await cache_manager.delete_data("players", str(user_id))

    except sqlite3.Error as e:
        logger.error(f"[Scheduler] Error during resource regeneration: {e}")


async def cleanup_stale_battles():
    """Finds and cleans up battle locks and states that have timed out."""
    logger.info("[Scheduler] Running 'cleanup_stale_battles' job...")
    
    try:
        # FIX: Added await and proper client access
        client = await cache_manager._get_client()
        
        # Get all battle lock keys
        lock_pattern = cache_manager._get_key("battle_lock", "*")
        lock_keys = await client.keys(lock_pattern)
        
        for key in lock_keys:
            ttl = await client.ttl(key)
            if ttl == -1:  # No TTL set
                logger.warning(f"[Scheduler] Found stale battle lock {key} with no TTL. Deleting.")
                await client.delete(key)
                
    except Exception as e:
        logger.error(f"[Scheduler] Error during stale battle cleanup: {e}")


def setup_scheduler():
    """Adds and starts all background jobs."""
    try:
        scheduler.add_job(
            regenerate_resources,
            trigger=IntervalTrigger(minutes=10),
            id="regenerate_resources",
            replace_existing=True,
            misfire_grace_time=60
        )
        
        scheduler.add_job(
            cleanup_stale_battles,
            trigger=IntervalTrigger(minutes=config.CLEANUP_INTERVAL / 60),
            id="cleanup_stale_battles",
            replace_existing=True,
            misfire_grace_time=60
        )
        
        scheduler.start()
        logger.info("Scheduler started successfully with jobs.")
    except Exception as e:
        logger.critical(f"Failed to start scheduler: {e}")
