from typing import Literal, Optional
from pydantic import BaseModel, Field


class EmailExtractionResult(BaseModel):
    category: Literal["Trash", "Information", "Review"]
    summary: str
    action_required: bool

class WorkerState(BaseModel):
    # Entrées brutes reçues de l'orchestrateur
    mail_uid: str
    raw_bytes: bytes

    # Données intermédiaires après parsing
    sender: Optional[str] = None
    subject: Optional[str] = None
    cleaned_body: Optional[str] = None

    # Sortie finale de l'analyse LLM
    result: Optional[EmailExtractionResult] = None
    moved_to_folder: Optional[str] = None