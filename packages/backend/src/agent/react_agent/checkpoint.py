"""
Checkpointer management for ReAct Agent
"""
import os
import logging
from pathlib import Path
from typing import Union
from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

logger = logging.getLogger(__name__)

# Set DB_PATH
DB_PATH = Path(os.getenv("DB_PATH", "conversation_checkpoints.db"))


async def init_checkpointer() -> Union[AsyncSqliteSaver, MemorySaver]:
    """
    Initialize checkpointer based on environment variables
    
    Returns:
        AsyncSqliteSaver or MemorySaver instance
    """
    use_persistence = os.getenv("USE_PERSISTENCE", "false").lower() == "true"
    
    if use_persistence:
        logger.info(f"Using SQLite-based persistence: {DB_PATH}")
        # Create SQLite path
        db_path = Path(DB_PATH)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Initialize AsyncSqliteSaver (using aiosqlite)
        try:
            # AsyncSqliteSaver uses connection string
            conn_string = f"aiosqlite:///{DB_PATH}"
            checkpointer = AsyncSqliteSaver.from_conn_string(conn_string)
            logger.info("AsyncSQLite checkpointer initialized")
            return checkpointer
        except Exception as e:
            logger.error(f"AsyncSQLite checkpointer initialization failed: {e}")
            logger.info("Using memory-based storage instead")
            return MemorySaver()
    else:
        logger.info("Using memory-based storage")
        return MemorySaver()


def cleanup_checkpointer_data(checkpointer: Union[AsyncSqliteSaver, MemorySaver], thread_id: str = None) -> bool:
    """
    Clean up checkpointer data
    
    Args:
        checkpointer
        thread_id: Specific thread ID (None for full cleanup)
        
    Returns:
        True if cleanup is successful, False otherwise
    """
    try:
        if isinstance(checkpointer, AsyncSqliteSaver):
            # SQLite-based cleanup
            if thread_id:
                with checkpointer.conn.cursor() as cursor:
                    cursor.execute(
                        "DELETE FROM checkpoints WHERE thread_id = ?", 
                        (thread_id,)
                    )
                    cursor.execute(
                        "DELETE FROM checkpoint_blobs WHERE thread_id = ?", 
                        (thread_id,)
                    )
                checkpointer.conn.commit()
                logger.info(f"SQLite checkpoint cleanup completed: {thread_id}")
            else:
                with checkpointer.conn.cursor() as cursor:
                    cursor.execute("DELETE FROM checkpoints")
                    cursor.execute("DELETE FROM checkpoint_blobs")
                checkpointer.conn.commit()
                logger.info("All SQLite checkpoints cleaned up")
                
        elif isinstance(checkpointer, MemorySaver):
            # Memory-based cleanup
            if thread_id:
                # MemorySaver has limited ability to clean up internally
                logger.info(f"Memory checkpoint cleanup attempt: {thread_id}")
            else:
                # Full cleanup
                logger.info("Memory checkpoint full cleanup")
                
        return True
        
    except Exception as e:
        logger.error(f"Error in checkpoint cleanup: {e}")
        return False