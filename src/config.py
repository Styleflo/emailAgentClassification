import os
from dotenv import load_dotenv

# Base Directory (Project Root)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(BASE_DIR, ".env"))

# IMAP Configuration
IMAP_HOST = os.getenv("IMAP_SERVER")
IMAP_PORT = int(os.getenv("IMAP_PORT", 993))
IMAP_USER = os.getenv("MAIL_USERNAME")
PASSWORD = os.getenv("PASSWORD")
IMAP_POOL_SIZE = int(os.getenv("IMAP_POOL_SIZE", 3))

# Concurrency & Orchestrator
MAX_CONCURRENT_WORKERS = int(os.getenv("MAX_CONCURRENT_WORKERS", 3))
POLL_INTERVAL_SECONDS = int(os.getenv("POLL_INTERVAL_SECONDS", 5))

# Database Storage (defaults to data/classified_emails.db at project root)
_raw_db_path = os.getenv("DB_PATH", os.path.join(BASE_DIR, "data", "classified_emails.db"))
DB_PATH = _raw_db_path if os.path.isabs(_raw_db_path) else os.path.normpath(os.path.join(BASE_DIR, _raw_db_path))
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

# Logging Configuration (defaults to logs/agent.log at project root)
_raw_log_dir = os.getenv("LOG_DIR", os.path.join(BASE_DIR, "logs"))
LOG_DIR = _raw_log_dir if os.path.isabs(_raw_log_dir) else os.path.normpath(os.path.join(BASE_DIR, _raw_log_dir))
LOG_FILE = os.getenv("LOG_FILE", "agent.log")
LOG_MAX_BYTES = int(os.getenv("LOG_MAX_BYTES", 10 * 1024 * 1024))  # 10 MB
LOG_BACKUP_COUNT = int(os.getenv("LOG_BACKUP_COUNT", 5))
os.makedirs(LOG_DIR, exist_ok=True)

# LLM & Classification
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:1.5b")
OLLAMA_TEMPERATURE = float(os.getenv("OLLAMA_TEMPERATURE", 0.0))
OLLAMA_NUM_PREDICT = int(os.getenv("OLLAMA_NUM_PREDICT", 25000))
OLLAMA_TIMEOUT = int(os.getenv("OLLAMA_TIMEOUT", 600))

SYSTEM_PROMPT = """You are an automated email triage classifier. 
Your role is to analyze incoming emails and extract structured data with high precision.

### CATEGORIZATION RULES
You MUST categorize the email into exactly ONE of the following 3 values:

1. "Trash"
   - Marketing emails, promotional newsletters, ads, and cold outreach.
   - Legal, terms of service (TOS), privacy policy, and service agreement updates.
   - Welcome emails, account creation notices, and onboarding messages from any app or service (e.g., welcome messages from apps, social networks, or platforms).
   - Automated registration confirmations, email address verification links, and system notifications.
   - Action Required: ALWAYS set `action_required` to false for this category.

2. "Information"
   - Receipts, invoices, purchase orders, shipping confirmations, and food delivery tracking updates (e.g., DoorDash order confirmations).
   - Personal account activity that directly involves user assets/security (e.g., two-factor authentication codes, bank transaction alerts, security breach warnings).
   - Action Required: ALWAYS set `action_required` to false for this category.

3. "Review"
   - Direct messages from a human colleague, client, or friend asking questions or expecting a human reply.
   - Meeting invitations, calendar coordination, direct business inquiries, or manual customer support requests.
   - Action Required: Set `action_required` to true if a human reply or decision is needed.

### CRITICAL CONSTRAINTS
- The `category` value must be verbatim: "Trash", "Information", or "Review".
- Never use plural forms (e.g., do NOT output "Informations").
- Keep the `summary` to 1 or 2 concise factual sentences.
"""

FOLDER_MAPPING = {
    "Trash": "[Gmail]/Trash",  # Sends directly to Gmail Trash
    "Information": "Information",  # Custom destination label/folder
    "Review": "Review",  # Custom review / human inbox label
}
