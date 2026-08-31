# AgentMailClassifier

An asynchronous, agentic email triage and classification system built with **LangGraph**, **LangChain Ollama**, **aioimaplib**, and **SQLite**.

The system continuously polls an IMAP mailbox, processes incoming emails concurrently through a LangGraph worker pipeline, classifies messages using a local LLM (`qwen2.5:1.5b`), moves emails to appropriate destination folders via a managed IMAP connection pool, logs operational events to rotating files and console, and persists structured classification records to a SQLite database.

---

## Architecture & Overview

The project is designed with a clear separation of concerns across two primary layers:

1. **Orchestrator Layer** (`src/`):
   - Maintains an IMAP listener socket to detect `UNSEEN` emails without marking them read (`BODY.PEEK[]`).
   - Limits concurrency with `asyncio.Semaphore` and manages an `ImapConnectionPool`.
   - Handles email deduplication via tracked in-flight UIDs (`PROCESSING_UIDS`).
   - Runs a background worker (`db_writer_worker`) consuming classification results from an `asyncio.Queue`.

2. **Worker Graph Layer** (`src/worker/`):
   - A compiled LangGraph workflow: `clean` ➔ `classify` ➔ `move_email`.
   - Extracts and sanitizes plain text / HTML (ignoring attachments).
   - Generates structured classification results via local Ollama LLM.
   - Moves messages to the mapped IMAP folder and expunges them from `INBOX`.

### Workflow Diagram

```text
[IMAP Inbox (UNSEEN)]
        │ (Poll / NOOP / PEEK fetch)
        ▼
[Orchestrator (agent.py)] ── (Deduplication + Semaphore)
        │
        ▼
┌────────────────── LangGraph Worker Graph ───────────────────┐
│                                                             │
│  [clean_node] ──► [classify_node] ──► [move_email_node]     │
│  (MIME parse,      (Local LLM:         (Move email & expunge│
│   HTML strip,       qwen2.5:1.5b        via ImapPool)       │
│   clean body)       structured output)                      │
│                                                             │
└──────────────────────────────┬──────────────────────────────┘
                               │ (WorkerState)
                               ▼
                   [db_writer_worker (Queue)]
                               │
                               ▼
                [SQLite DB (classified_emails)]
```

---

## Project Structure

```
emailAgentClassification/
├── .env                    # Environment variables (credentials, paths, model settings)
├── .gitignore              # Ignored files (venv, data/, logs/, __pycache__)
├── README.md               # Project documentation & usage instructions
├── data/                   # Runtime SQLite database storage (classified_emails.db)
├── logs/                   # Application rotating log files (agent.log)
├── tests/                  # Automated test suite
│   ├── __init__.py
│   └── test_orchestrator.py
└── src/                    # Application source code
    ├── __init__.py
    ├── config.py           # Centralized configuration & root-anchored path resolution
    ├── agentOrchestrateur.py # Main entry point to launch the orchestrator loop
    ├── agent.py            # Core orchestrator loop, IMAP listener, task distribution
    ├── helper.py           # IMAP connection pool, SQLite DB helpers, logging setup
    ├── model.py            # IMAP configuration re-exports
    ├── nodes.py            # Orchestrator-level worker tasks & DB write queue consumer
    ├── state.py            # Orchestrator Pydantic state model
    └── worker/             # LangGraph Worker Subpackage
        ├── __init__.py
        ├── agent.py        # LangGraph StateGraph definition (clean -> classify -> move)
        ├── helper.py       # MIME header decoders, HTML stripper, text sanitizer
        ├── model.py        # ChatOllama model client with structured output
        ├── nodes.py        # Worker LangGraph nodes (clean_node, classify_node, move_email_node)
        └── state.py        # WorkerState & EmailExtractionResult Pydantic models
```

---

## Classification Categories & Routing

Incoming emails are extracted and classified into exactly one of three categories:

| Category | Description | `action_required` | Default IMAP Folder |
| :--- | :--- | :--- | :--- |
| **`Trash`** | Marketing emails, newsletters, TOS/privacy policy updates, automated welcome/signup notices | `False` | `[Gmail]/Trash` |
| **`Information`** | Receipts, invoices, shipping/delivery confirmations, 2FA codes, security/bank alerts | `False` | `Information` |
| **`Review`** | Direct messages from humans (colleagues, clients), meeting invitations, manual support requests | `True` / `False` | `Review` |

---

## Database Persistence & Dynamic Migration (SQLite)

Classified email metadata is sequentially stored in SQLite (`data/classified_emails.db` by default) via the background `db_writer_worker`.

The database automatically manages schema creation and dynamically applies table migrations when new categories are configured in `FOLDER_MAPPING`.

### Table Schema: `classified_emails`
```sql
CREATE TABLE IF NOT EXISTS classified_emails (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mail_uid TEXT NOT NULL UNIQUE,
    sender TEXT,
    subject TEXT,
    cleaned_body_preview TEXT,
    category TEXT CHECK(category IN ('Trash', 'Information', 'Review')),
    summary TEXT,
    action_required INTEGER CHECK(action_required IN (0, 1)),
    moved_to_folder TEXT,
    processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

---

## 📝 Logging System

The application features a dual logging system configured in `helper.py`:
- **Console Output**: Real-time human-readable stdout logs with `[UID <id>]` traceability.
- **Rotating File Logs**: Stored in `logs/agent.log` (rotates up to 10 MB per file, keeping 5 backup archives).

---

## Configuration & Environment Variables

All settings can be customized in a root `.env` file or through environment variables (loaded via `src/config.py`):

```env
# IMAP Settings
IMAP_SERVER=imap.example.com
IMAP_PORT=993
MAIL_USERNAME=your-email@example.com
PASSWORD=your-app-password
IMAP_POOL_SIZE=3

# Concurrency & Polling
MAX_CONCURRENT_WORKERS=3
POLL_INTERVAL_SECONDS=5

# Database
DB_PATH=data/classified_emails.db

# Logging
LOG_DIR=logs
LOG_FILE=agent.log
LOG_MAX_BYTES=10485760
LOG_BACKUP_COUNT=5

# Ollama / LLM
OLLAMA_MODEL=qwen2.5:1.5b
OLLAMA_TEMPERATURE=0.0
OLLAMA_NUM_PREDICT=25000
OLLAMA_TIMEOUT=600
```

---

## 🚀 Running the Application

### 1. Prerequisites
- Python 3.10+
- [Ollama](https://ollama.com/) running locally with the target model:
  ```bash
  ollama pull qwen2.5:1.5b
  ```
- To enables parallelization:
  ```bash
  OLLAMA_NUM_PARALLEL=3 ollama serve
  ```

### 2. Start the Orchestrator
```bash
python src/agentOrchestrateur.py
```

### 3. Running Unit Tests
```bash
python -m unittest discover -s tests -p "test_*.py"
```
