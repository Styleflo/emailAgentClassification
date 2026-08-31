from langchain_ollama import ChatOllama
from config import (
    FOLDER_MAPPING,
    OLLAMA_MODEL,
    OLLAMA_NUM_PREDICT,
    OLLAMA_TEMPERATURE,
    OLLAMA_TIMEOUT,
    SYSTEM_PROMPT,
)
from .state import EmailExtractionResult

# Create LLM chat client
model = ChatOllama(
    model=OLLAMA_MODEL,
    temperature=OLLAMA_TEMPERATURE,
    num_predict=OLLAMA_NUM_PREDICT,
    timeout=OLLAMA_TIMEOUT,
)

agent = model.with_structured_output(EmailExtractionResult)

__all__ = ["agent", "SYSTEM_PROMPT", "FOLDER_MAPPING", "model"]