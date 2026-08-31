import asyncio
import logging
from helper import DB_PATH, init_db, insert_classified_email
from worker.state import WorkerState

# Logging Configuration
logger = logging.getLogger("Orchestrator.Nodes")

PROCESSING_UIDS = set()


async def process_email_task(
    mail_uid: str, raw_bytes: bytes, compiled_graph, db_queue: asyncio.Queue
):
    """Background task executed by a worker agent with deduplication."""
    logger.info(f"[UID {mail_uid}] Starting analysis...")
    try:
        initial_state = WorkerState(mail_uid=mail_uid, raw_bytes=raw_bytes)
        final_state = await compiled_graph.ainvoke(initial_state)

        category = (
            final_state["result"].category
            if final_state.get("result")
            else "Unknown"
        )
        target_folder = final_state.get("moved_to_folder", "Not moved")
        logger.info(
            f"[UID {mail_uid}] Classified as '{category}' -> Moved to '{target_folder}'"
        )

        await db_queue.put(final_state)
    except Exception as e:
        logger.error(f"[UID {mail_uid}] Error during processing: {e}")
    finally:
        # Always release the UID once processing is complete
        PROCESSING_UIDS.discard(mail_uid)


async def db_writer_worker(db_queue: asyncio.Queue, db_path: str = DB_PATH):
    """Listens to the results queue and sequentially persists data to the database."""
    logger.info("Starting DB Writer Worker...")
    try:
        await asyncio.to_thread(init_db, db_path)
    except Exception as e:
        logger.error(f"Error during DB initialization: {e}")

    while True:
        record = await db_queue.get()
        try:
            if isinstance(record, dict) and record.get("mail_uid"):
                await asyncio.to_thread(insert_classified_email, record, db_path)
                logger.info(f"[UID {record.get('mail_uid')}] Record persisted to database.")
        except Exception as e:
            logger.error(f"DB write error: {e}")
        finally:
            db_queue.task_done()
