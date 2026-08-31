import sys
import os
import asyncio
import logging
import unittest
from unittest.mock import MagicMock, AsyncMock, patch

# Ensure the src directory is in path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from model import IMAP_HOST
from state import OrchestratorState
from helper import ImapConnectionPool, setup_logging
from nodes import db_writer_worker, process_email_task
from worker.state import WorkerState, EmailExtractionResult

class TestOrchestrator(unittest.IsolatedAsyncioTestCase):

    def test_setup_logging(self):
        import tempfile
        import shutil
        temp_dir = tempfile.mkdtemp()
        try:
            log_path = setup_logging(log_dir=temp_dir, log_filename="test_agent.log")
            self.assertTrue(os.path.exists(log_path))
            
            test_logger = logging.getLogger("TestLogger")
            test_logger.info("Test message to log file")
            
            # Flush handlers to ensure content is written
            for handler in logging.getLogger().handlers:
                handler.flush()
                
            with open(log_path, "r", encoding="utf-8") as f:
                content = f.read()
            self.assertIn("Test message to log file", content)
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

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
        import tempfile
        import sqlite3
        with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
            test_db_path = tmp.name

        db_queue = asyncio.Queue()
        test_record = {
            "mail_uid": "999",
            "sender": "sender@test.com",
            "subject": "Test Subject",
            "cleaned_body": "Test body content",
            "result": EmailExtractionResult(
                category="Information",
                summary="A receipt summary",
                action_required=False
            ),
            "moved_to_folder": "Information"
        }
        await db_queue.put(test_record)

        # Run db_writer_worker task with test_db_path
        task = asyncio.create_task(db_writer_worker(db_queue, db_path=test_db_path))

        # Yield control to let it process
        await asyncio.sleep(0.1)

        # Confirm queue is empty
        self.assertEqual(db_queue.qsize(), 0)
        task.cancel()

        # Check DB contents
        with sqlite3.connect(test_db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT mail_uid, sender, subject, category, summary, action_required, moved_to_folder FROM classified_emails WHERE mail_uid = ?", ("999",))
            row = cursor.fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(row[0], "999")
            self.assertEqual(row[1], "sender@test.com")
            self.assertEqual(row[2], "Test Subject")
            self.assertEqual(row[3], "Information")
            self.assertEqual(row[4], "A receipt summary")
            self.assertEqual(row[5], 0)
            self.assertEqual(row[6], "Information")

        if os.path.exists(test_db_path):
            os.remove(test_db_path)

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
