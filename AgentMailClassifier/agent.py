import asyncio
import logging
from aioimaplib import aioimaplib
from helper import ImapConnectionPool
from model import IMAP_HOST, IMAP_PORT, IMAP_USER, PASSWORD
from nodes import PROCESSING_UIDS, db_writer_worker, process_email_task
from worker.agent import create_worker_graph

# --- Configuration Logging ---
logger = logging.getLogger("Orchestrator.Agent")


async def bounded_process_task(
    semaphore: asyncio.Semaphore,
    mail_uid: str,
    raw_bytes: bytes,
    compiled_graph,
    db_queue: asyncio.Queue,
):
    async with semaphore:
        await process_email_task(
            mail_uid, raw_bytes, compiled_graph, db_queue
        )


async def run_orchestrator():
    # 1. Initialiser le pool et le sous-graphe
    imap_pool = ImapConnectionPool(size=3)
    await imap_pool.initialize()

    agent_semaphore = asyncio.Semaphore(3)
    compiled_graph = create_worker_graph(imap_pool)
    db_queue = asyncio.Queue()

    # Démarrage du worker DB en arrière-plan
    asyncio.create_task(db_writer_worker(db_queue))

    listener = None

    try:
        while True:
            try:
                # Connexion ou reconnexion si la socket est fermée
                if not listener or listener.protocol is None:
                    logger.info("Connexion du socket d'écoute IMAP...")
                    listener = aioimaplib.IMAP4_SSL(
                        host=IMAP_HOST, port=IMAP_PORT
                    )
                    await listener.wait_hello_from_server()
                    await listener.login(IMAP_USER, PASSWORD)
                    await listener.select("INBOX")
                    logger.info("Écoute active sur la boîte INBOX.")

                # 1. Rafraîchir l'état de la boîte via NOOP
                await listener.noop()

                # 2. Chercher les emails non lus
                _, search_res = await listener.search("UNSEEN")
                msg_ids = (
                    search_res[0].split()
                    if search_res and search_res[0]
                    else []
                )

                for msg_id in msg_ids:
                    msg_num = msg_id.decode()

                    # Fetch du message et de l'UID sans modifier l'état de lecture
                    _, fetch_res = await listener.fetch(
                        msg_num, "(UID BODY.PEEK[])"
                    )

                    if not fetch_res or len(fetch_res) < 2:
                        continue

                    header_info = (
                        fetch_res[0].decode()
                        if isinstance(fetch_res[0], bytes)
                        else str(fetch_res[0])
                    )
                    mail_uid = (
                        header_info.split("UID ")[1].split()[0].rstrip(")")
                    )
                    raw_bytes = fetch_res[1]

                    # Déduplication : ignorer si déjà en cours de traitement
                    if mail_uid in PROCESSING_UIDS:
                        continue

                    PROCESSING_UIDS.add(mail_uid)

                    # Lancement asynchrone limité par le sémaphore
                    asyncio.create_task(
                        bounded_process_task(
                            agent_semaphore,
                            mail_uid,
                            raw_bytes,
                            compiled_graph,
                            db_queue,
                        )
                    )

                # 3. Pause non bloquante avant la prochaine vérification
                await asyncio.sleep(5)

            except Exception as e:
                logger.error(
                    f"Erreur réseau / IMAP dans l'orchestrateur: {e}. Reconnexion dans 5s..."
                )
                if listener:
                    try:
                        await listener.logout()
                    except Exception:
                        pass
                    listener = None
                await asyncio.sleep(5)

    finally:
        if listener:
            await listener.logout()
        await imap_pool.close_all()