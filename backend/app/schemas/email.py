from pydantic import BaseModel, Field


class EmailIngestRequest(BaseModel):
    message_id: str = Field(..., min_length=1)
    subject: str = Field(..., min_length=1)
    raw_body: str = Field(..., min_length=1)
    thread_id: str | None = None
    cleaned_body: str | None = None
    from_address: str | None = None
    to_address: str | None = None
    source: str | None = "manual"
