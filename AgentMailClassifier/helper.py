import asyncio
from contextlib import asynccontextmanager
import logging
import os
import sqlite3
from aioimaplib import aioimaplib
from model import IMAP_HOST, IMAP_PORT, IMAP_USER, PASSWORD

logger = logging.getLogger("Pool.Helper")

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
        """Crée, négocie et authentifie un nouveau socket IMAP."""
        client = aioimaplib.IMAP4_SSL(host=IMAP_HOST, port=IMAP_PORT)
        await client.wait_hello_from_server()
        await client.login(IMAP_USER, PASSWORD)
        return client

    async def initialize(self):
        """Remplit le pool au démarrage."""
        logger.info(
            f"Initialisation du pool IMAP ({self.size} connexions)..."
        )
        for _ in range(self.size):
            client = await self._create_single_client()
            await self.pool.put(client)
        logger.info("Pool IMAP prêt.")

    @asynccontextmanager
    async def get_connection(self):
        """Prête une connexion valide et la remplace automatiquement si elle est inactive/déconnectée."""
        client = await self.pool.get()

        try:
            # --- 1. Health Check (Keep-Alive / Reconnexion) ---
            is_alive = False
            try:
                if client.protocol is not None:
                    # Envoi d'un NOOP avec timeout court (3s) pour vérifier la vivacité du socket
                    res, _ = await asyncio.wait_for(client.noop(), timeout=3.0)
                    if res == "OK":
                        is_alive = True
            except Exception:
                is_alive = False

            # Si le socket est coupé (inactivité > 25 min ou reset réseau), on le recrée
            if not is_alive:
                logger.warning(
                    "Socket du pool inactive ou fermée détectée. Reconnexion en cours..."
                )
                try:
                    await client.logout()
                except Exception:
                    pass
                client = await self._create_single_client()

            # --- 2. Mise à disposition du client pour le sous-agent ---
            yield client

        finally:
            # --- 3. Restitution systématique dans la file ---
            await self.pool.put(client)

    async def close_all(self):
        """Ferme proprement toutes les connexions du pool lors de l'arrêt."""
        logger.info("Fermeture du pool IMAP...")
        while not self.pool.empty():
            client = await self.pool.get()
            try:
                await client.logout()
            except Exception:
                pass