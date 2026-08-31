import sys
import os
import asyncio
import unittest
from unittest.mock import MagicMock, AsyncMock, patch

# Ensure the AgentMailClassifier directory is in path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from model import IMAP_HOST
from state import OrchestratorState
from helper import ImapConnectionPool
from nodes import db_writer_worker, process_email_task
from worker.state import WorkerState, EmailExtractionResult

class TestOrchestrator(unittest.IsolatedAsyncioTestCase):

    def test_orchestrator_state(self):
        state = OrchestratorState(is_running=True, processed_count=5)
        self.assertTrue(state.is_running)
        self.assertEqual(state.processed_count, 5)

    @patch('helper.aioimaplib.IMAP4_SSL')
    async def test_imap_connection_pool(self, mock_imap_class):
        mock_client = AsyncMock()
        mock_client.protocol = MagicMock()
        mock_client.noop.return_value = ("OK", [b"NOOP Completed"])
        mock_imap_class.return_value = mock_client

        pool = ImapConnectionPool(size=2)
        await pool.initialize()

        self.assertEqual(mock_imap_class.call_count, 2)
        self.assertEqual(mock_client.wait_hello_from_server.call_count, 2)
        self.assertEqual(mock_client.login.call_count, 2)

        # Test context manager get_connection
        async with pool.get_connection() as conn:
            self.assertEqual(conn, mock_client)
            self.assertEqual(pool.pool.qsize(), 1)

        self.assertEqual(pool.pool.qsize(), 2)

        # Test close_all
        await pool.close_all()
        self.assertEqual(mock_client.logout.call_count, 2)

    async def test_db_writer_worker(self):
        db_queue = asyncio.Queue()
        # Put an item to DB writer queue
        await db_queue.put({"test": "data"})

        # Run db_writer_worker task
        task = asyncio.create_task(db_writer_worker(db_queue))

        # Yield control to let it process
        await asyncio.sleep(0.1)

        # Confirm queue is empty
        self.assertEqual(db_queue.qsize(), 0)
        task.cancel()

    async def test_process_email_task(self):
        mock_compiled_graph = AsyncMock()
        # Return state with category / result
        mock_extraction = EmailExtractionResult(
            category="Review",
            summary="This is a test email.",
            action_required=True
        )
        mock_compiled_graph.ainvoke.return_value = {
            "result": mock_extraction,
            "moved_to_folder": "work"
        }

        db_queue = asyncio.Queue()
        await process_email_task(
            mail_uid="123",
            raw_bytes=b"raw message data",
            compiled_graph=mock_compiled_graph,
            db_queue=db_queue
        )

        # Verify graph invocation
        mock_compiled_graph.ainvoke.assert_called_once()
        # Verify db queue got the final state
        self.assertEqual(db_queue.qsize(), 1)
        record = await db_queue.get()
        self.assertEqual(record["moved_to_folder"], "work")

if __name__ == '__main__':
    unittest.main()
