import asyncio
import logging
from aioimaplib import aioimaplib
from helper import ImapConnectionPool
from model import IMAP_HOST, IMAP_PORT, IMAP_USER, PASSWORD
from nodes import PROCESSING_UIDS, db_writer_worker, process_email_task
from worker.agent import create_worker_graph

# --- Logging Configuration ---
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
    # 1. Initialize connection pool and worker subgraph
    imap_pool = ImapConnectionPool(size=3)
    await imap_pool.initialize()

    agent_semaphore = asyncio.Semaphore(3)
    compiled_graph = create_worker_graph(imap_pool)
    db_queue = asyncio.Queue()

    # Start DB writer worker task in the background
    asyncio.create_task(db_writer_worker(db_queue))

    listener = None

    try:
        while True:
            try:
                # Connect or reconnect if socket is closed
                if not listener or listener.protocol is None:
                    logger.info("Connecting IMAP listener socket...")
                    listener = aioimaplib.IMAP4_SSL(
                        host=IMAP_HOST, port=IMAP_PORT
                    )
                    await listener.wait_hello_from_server()
                    await listener.login(IMAP_USER, PASSWORD)
                    await listener.select("INBOX")
                    logger.info("Active listening on INBOX.")

                # 1. Refresh mailbox state via NOOP
                await listener.noop()

                # 2. Search for unseen emails
                _, search_res = await listener.search("UNSEEN")
                msg_ids = (
                    search_res[0].split()
                    if search_res and search_res[0]
                    else []
                )

                if msg_ids:
                    logger.info(f"📬 Detected {len(msg_ids)} unseen email(s).")

                for msg_id in msg_ids:
                    msg_num = msg_id.decode()

                    # Fetch message and UID without altering read status
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

                    # Deduplication: ignore if already currently processing
                    if mail_uid in PROCESSING_UIDS:
                        logger.debug(f"[UID {mail_uid}] Already in progress, skipping.")
                        continue

                    PROCESSING_UIDS.add(mail_uid)
                    logger.info(f"🚀 [UID {mail_uid}] Submitting email processing task.")

                    # Asynchronous dispatch bounded by semaphore
                    asyncio.create_task(
                        bounded_process_task(
                            agent_semaphore,
                            mail_uid,
                            raw_bytes,
                            compiled_graph,
                            db_queue,
                        )
                    )

                # 3. Non-blocking pause before next polling cycle
                await asyncio.sleep(5)

            except Exception as e:
                logger.error(
                    f"IMAP / Network error in orchestrator: {e}. Reconnecting in 5s..."
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