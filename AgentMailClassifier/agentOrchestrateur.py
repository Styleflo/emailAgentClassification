import asyncio
import logging
from agent import run_orchestrator

# --- Configuration Logging ---
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("Orchestrator")

if __name__ == "__main__":
    try:
        asyncio.run(run_orchestrator())
    except KeyboardInterrupt:
        logger.info("Arrêt de l'orchestrateur demandé par l'utilisateur.")
