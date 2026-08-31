import asyncio
import logging
from agent import run_orchestrator
from helper import setup_logging

# --- Configuration Logging ---
setup_logging()
logger = logging.getLogger("Orchestrator")

if __name__ == "__main__":
    try:
        asyncio.run(run_orchestrator())
    except KeyboardInterrupt:
        logger.info("Arrêt de l'orchestrateur demandé par l'utilisateur.")

