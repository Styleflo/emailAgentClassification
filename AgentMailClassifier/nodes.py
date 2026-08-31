import asyncio
import logging
from helper import DB_PATH, init_db, insert_classified_email
from worker.state import WorkerState

logger = logging.getLogger("Orchestrator.Nodes")

PROCESSING_UIDS = set()


async def process_email_task(
    mail_uid: str, raw_bytes: bytes, compiled_graph, db_queue: asyncio.Queue
):
    """Tâche de fond exécutée par un sous-agent avec déduplication."""
    logger.info(f"⚡ [UID {mail_uid}] Démarrage de l'analyse...")
    try:
        initial_state = WorkerState(mail_uid=mail_uid, raw_bytes=raw_bytes)
        final_state = await compiled_graph.ainvoke(initial_state)

        category = (
            final_state["result"].category
            if final_state.get("result")
            else "Inconnu"
        )
        target_folder = final_state.get("moved_to_folder", "Non déplacé")
        logger.info(
            f"✅ [UID {mail_uid}] Classé en '{category}' -> Déplacé vers '{target_folder}'"
        )

        await db_queue.put(final_state)
    except Exception as e:
        logger.error(f"❌ [UID {mail_uid}] Erreur lors du traitement: {e}")
    finally:
        # Toujours libérer l'UID une fois le traitement terminé
        PROCESSING_UIDS.discard(mail_uid)


async def db_writer_worker(db_queue: asyncio.Queue, db_path: str = DB_PATH):
    """Écoute la file des résultats et persiste les données de façon séquentielle."""
    logger.info("Démarrage du DB Writer Worker...")
    try:
        await asyncio.to_thread(init_db, db_path)
    except Exception as e:
        logger.error(f"Erreur lors de l'initialisation de la DB : {e}")

    while True:
        record = await db_queue.get()
        try:
            if isinstance(record, dict) and record.get("mail_uid"):
                await asyncio.to_thread(insert_classified_email, record, db_path)
                logger.info(f"💾 [UID {record.get('mail_uid')}] Données persistées en base.")
        except Exception as e:
            logger.error(f"Erreur d'écriture DB : {e}")
        finally:
            db_queue.task_done()
