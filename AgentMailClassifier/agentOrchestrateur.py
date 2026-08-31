import asyncio
import logging
from agent import run_orchestrator
from helper import setup_logging

# --- Logging Configuration ---
setup_logging()
logger = logging.getLogger("Orchestrator")

if __name__ == "__main__":
    try:
        asyncio.run(run_orchestrator())
    except KeyboardInterrupt:
        logger.info("Orchestrator shutdown requested by user.")


