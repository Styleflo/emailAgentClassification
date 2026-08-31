# AgentMailClassifier

An asynchronous, agentic email triage and classification system built with **LangGraph**, **LangChain Ollama**, and **aioimaplib**.

The system polls an IMAP mailbox, processes incoming emails concurrently using a LangGraph worker pipeline, classifies messages using a local LLM (`qwen2.5:1.5b`), moves emails to appropriate destination folders via an IMAP connection pool, and forwards metadata to a background queue for persistence.

---

## 🏗 Architecture & Overview

The project is structured into two main layers:
1. **Orchestrator Layer** (`AgentMailClassifier/`): Manages IMAP listener polling, concurrency bounds, connection pooling, and background DB ingestion queues.
2. **Worker Graph Layer** (`AgentMailClassifier/worker/`): A compiled LangGraph workflow that cleans, classifies, and moves individual emails.

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
```

---

## 📂 Project Structure

```
AgentMailClassifier/
├── config.py              # Centralized environment variables, LLM, IMAP, & DB settings
├── agentOrchestrateur.py   # Main entry point to launch the orchestrator loop
├── agent.py               # Core orchestrator loop, IMAP listener, task distribution
├── helper.py              # Asynchronous IMAP connection pool, logging & DB helpers
├── model.py               # IMAP configuration re-exports
├── nodes.py               # Orchestrator-level worker tasks & DB write queue consumer
├── state.py               # Orchestrator Pydantic state model
├── test_orchestrator.py   # Unit test suite for orchestrator components
└── worker/
    ├── __init__.py
    ├── agent.py           # LangGraph StateGraph definition (clean -> classify -> move)
    ├── helper.py          # Email MIME decoders, HTML sanitization, text cleaners
    ├── model.py           # ChatOllama model client definition
    ├── nodes.py           # Worker LangGraph nodes (clean_node, classify_node, move_email_node)
    └── state.py           # WorkerState & EmailExtractionResult Pydantic models
```

---

## 🏷 Classification Categories & Routing

Incoming emails are extracted and classified into exactly one of three categories:

| Category | Description | `action_required` | Default IMAP Folder |
| :--- | :--- | :--- | :--- |
| **`Trash`** | Marketing emails, newsletters, TOS/privacy policy updates, automated welcome/signup notices | `False` | `[Gmail]/Trash` |
| **`Information`** | Receipts, invoices, shipping/delivery confirmations, 2FA codes, security/bank alerts | `False` | `Information` |
| **`Review`** | Direct messages from humans (colleagues, clients), meeting invitations, manual support requests | `True` / `False` | `Review` |

---

## ⚙️ Prerequisites & Environment Setup

### 1. Requirements
- Python 3.10+
- [Ollama](https://ollama.com/) running locally with the `qwen2.5:1.5b` model pulled:
  ```bash
  ollama pull qwen2.5:1.5b
  ```

### 2. Environment Variables
Create a `.env` file in the project root with your IMAP credentials:

```env
IMAP_SERVER=imap.example.com
IMAP_PORT=993
MAIL_USERNAME=your-email@example.com
PASSWORD=your-app-password
```

---

## 🚀 Running the Application

### Start the Orchestrator
To start listening and classifying incoming emails:

```bash
python agentOrchestrateur.py
```

### Running Tests
Execute the test suite using `unittest`:

```bash
python -m unittest discover -s . -p "test_*.py"
```
