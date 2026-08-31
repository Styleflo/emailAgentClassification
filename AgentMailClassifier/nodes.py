import asyncio
import logging
import os
import sqlite3
from typing import Optional
from worker.state import WorkerState

logger = logging.getLogger("Orchestrator.Nodes")

PROCESSING_UIDS = set()
DB_PATH = os.getenv("DB_PATH", "classified_emails.db")


def init_db(db_path: str = DB_PATH):
    """Initialise la base de données SQLite et crée la table si nécessaire."""
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS classified_emails (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                mail_uid TEXT NOT NULL UNIQUE,
                sender TEXT,
                subject TEXT,
                cleaned_body_preview TEXT,
                category TEXT CHECK(category IN ('Trash', 'Information', 'Review')),
                summary TEXT,
                action_required BOOLEAN,
                moved_to_folder TEXT,
                processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.commit()


def insert_classified_email(record: dict, db_path: str = DB_PATH):
    """Insère un enregistrement classifié dans la base SQLite."""
    mail_uid = record.get("mail_uid")
    sender = record.get("sender")
    subject = record.get("subject")
    cleaned_body = record.get("cleaned_body")
    cleaned_body_preview = cleaned_body[:500] if cleaned_body else None

    result = record.get("result")
    category = None
    summary = None
    action_required = None

    if result:
        category = getattr(result, "category", None) or (result.get("category") if isinstance(result, dict) else None)
        summary = getattr(result, "summary", None) or (result.get("summary") if isinstance(result, dict) else None)
        action_required = getattr(result, "action_required", None) if hasattr(result, "action_required") else (result.get("action_required") if isinstance(result, dict) else None)

    moved_to_folder = record.get("moved_to_folder")

    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT OR REPLACE INTO classified_emails (
                mail_uid, sender, subject, cleaned_body_preview, category, summary, action_required, moved_to_folder
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                mail_uid,
                sender,
                subject,
                cleaned_body_preview,
                category,
                summary,
                action_required,
                moved_to_folder,
            ),
        )
        conn.commit()


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
