from typing import Literal, Optional
from pydantic import BaseModel


class EmailExtractionResult(BaseModel):
    category: Literal["Trash", "Information", "Review"]
    summary: str
    action_required: bool

class WorkerState(BaseModel):
    # Raw input received from the orchestrator
    mail_uid: str
    raw_bytes: bytes

    # Intermediate fields populated after MIME/HTML parsing
    sender: Optional[str] = None
    subject: Optional[str] = None
    cleaned_body: Optional[str] = None

    # Output from the LLM analysis and IMAP move action
    result: Optional[EmailExtractionResult] = None
    moved_to_folder: Optional[str] = None