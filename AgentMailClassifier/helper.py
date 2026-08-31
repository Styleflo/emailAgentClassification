import asyncio
from contextlib import asynccontextmanager
import logging
from logging.handlers import RotatingFileHandler
import os
import sqlite3
from typing import Optional
from aioimaplib import aioimaplib
from model import IMAP_HOST, IMAP_PORT, IMAP_USER, PASSWORD

# Logging Configuration
logger = logging.getLogger("Pool.Helper")

DB_PATH = os.getenv("DB_PATH", "classified_emails.db")
LOG_DIR = os.getenv("LOG_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs"))
LOG_FILE = os.getenv("LOG_FILE", "agent.log")


def setup_logging(
    log_dir: str = LOG_DIR,
    log_filename: str = LOG_FILE,
    level: int = logging.INFO,
    max_bytes: int = 10 * 1024 * 1024,
    backup_count: int = 5,
):
    """Configures global logging with both console and rotating file outputs."""
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, log_filename)

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] [%(name)s] %(message)s"
    )

    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Avoid duplicate handlers if setup_logging is invoked multiple times
    if not any(isinstance(h, RotatingFileHandler) and getattr(h, "baseFilename", None) == os.path.abspath(log_path) for h in root_logger.handlers):
        file_handler = RotatingFileHandler(
            log_path, maxBytes=max_bytes, backupCount=backup_count, encoding="utf-8"
        )
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)

    if not any(isinstance(h, logging.StreamHandler) and not isinstance(h, RotatingFileHandler) for h in root_logger.handlers):
        stream_handler = logging.StreamHandler()
        stream_handler.setLevel(level)
        stream_handler.setFormatter(formatter)
        root_logger.addHandler(stream_handler)

    return log_path



def init_db(db_path: str = DB_PATH):
    """Initializes SQLite database and creates table if needed."""
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
    """Inserts a classified email record into SQLite."""
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
        category = getattr(result, "category", None) or (
            result.get("category") if isinstance(result, dict) else None
        )
        summary = getattr(result, "summary", None) or (
            result.get("summary") if isinstance(result, dict) else None
        )
        action_required = getattr(
            result, "action_required", None
        ) if hasattr(result, "action_required") else (
            result.get("action_required") if isinstance(result, dict) else None
        )

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



class ImapConnectionPool:

    def __init__(self, size: int = 3):
        self.size = size
        self.pool = asyncio.Queue(maxsize=size)

    async def _create_single_client(self) -> aioimaplib.IMAP4_SSL:
        """Creates, negotiates SSL, and authenticates a new IMAP socket."""
        client = aioimaplib.IMAP4_SSL(host=IMAP_HOST, port=IMAP_PORT)
        await client.wait_hello_from_server()
        await client.login(IMAP_USER, PASSWORD)
        return client

    async def initialize(self):
        """Fills the connection pool at startup."""
        logger.info(
            f"Initializing IMAP connection pool ({self.size} connections)..."
        )
        for _ in range(self.size):
            client = await self._create_single_client()
            await self.pool.put(client)
        logger.info("IMAP connection pool ready.")

    @asynccontextmanager
    async def get_connection(self):
        """Borrows a valid connection and automatically replaces it if inactive/disconnected."""
        client = await self.pool.get()

        try:
            # Health Check (Keep-Alive / Reconnect)
            is_alive = False
            try:
                if client.protocol is not None:
                    # Send NOOP with short timeout (3s) to check socket liveness
                    res, _ = await asyncio.wait_for(client.noop(), timeout=3.0)
                    if res == "OK":
                        is_alive = True
            except Exception:
                is_alive = False

            # If the socket dropped (inactivity > 25 min or network reset), recreate it
            if not is_alive:
                logger.warning(
                    "Inactive or closed pool socket detected. Reconnecting..."
                )
                try:
                    await client.logout()
                except Exception:
                    pass
                client = await self._create_single_client()

            # Yield client to worker agent
            yield client

        finally:
            # Return connection back to the pool
            await self.pool.put(client)

    async def close_all(self):
        """Gracefully closes all pool connections during shutdown."""
        logger.info("Closing IMAP pool connections...")
        while not self.pool.empty():
            client = await self.pool.get()
            try:
                await client.logout()
            except Exception:
                pass