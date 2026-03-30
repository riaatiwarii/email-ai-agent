from typing import Any, Literal

from pydantic import BaseModel, Field


TaskStatus = Literal[
    "PENDING_APPROVAL",
    "APPROVED",
    "REJECTED",
    "EXECUTING",
    "EXECUTED",
    "EXECUTION_FAILED",
]
TaskActionType = Literal[
    "REPLY",
    "SCHEDULE_MEETING",
    "SEND_REMINDER",
    "FOLLOW_UP",
    "CREATE_NOTE",
    "UNKNOWN",
]
ProcessingMode = Literal["rules", "llm", "hybrid", "fallback"]


class ExtractedTask(BaseModel):
    action_type: TaskActionType
    status: TaskStatus = "PENDING_APPROVAL"
    confidence: float = Field(..., ge=0.0, le=1.0)
    rationale: str = Field(..., min_length=1)
    title: str = Field(..., min_length=1)
    payload: dict[str, Any] = Field(default_factory=dict)


class EmailExtractionResult(BaseModel):
    mode: ProcessingMode
    tasks: list[ExtractedTask] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
