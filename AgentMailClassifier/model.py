import os
from dotenv import load_dotenv

load_dotenv()

# --- Identifiants IMAP ---
IMAP_HOST = os.getenv("IMAP_SERVER")
IMAP_PORT = os.getenv("IMAP_PORT")
IMAP_USER = os.getenv("MAIL_USERNAME")
PASSWORD = os.getenv("PASSWORD")
