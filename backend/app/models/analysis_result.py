from typing import Any
from pydantic import BaseModel, Field


class AnalyzeRequest(BaseModel):
    repo_url: str
    branch: str | None = None
    module_hints: list[str] = Field(default_factory=list)
    upload_source: bool | None = None


class AnalyzeResponse(BaseModel):
    run_id: str
    status: str
    summary: dict[str, Any]
    artifacts: list[str] = Field(default_factory=list)


class ReviewUpdate(BaseModel):
    item_type: str
    item_id: str
    status: str
    corrected_text: str | None = None
    comment: str | None = None
    reviewer: str = "SME"
