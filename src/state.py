from pydantic import BaseModel, Field

class OrchestratorState(BaseModel):
    """Represents the configuration or current active state of the orchestrator."""
    is_running: bool = Field(default=False, description="Whether the orchestrator loop is running.")
    processed_count: int = Field(default=0, description="Number of emails processed in the current session.")
