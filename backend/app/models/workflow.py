from typing import List, Optional
from pydantic import BaseModel, Field


class WorkflowStep(BaseModel):
    """
    One step in a business workflow.
    """

    id: str

    name: str

    description: str

    actor: Optional[str] = None

    action: Optional[str] = None

    condition: Optional[str] = None

    next_step: Optional[str] = None


class Workflow(BaseModel):
    """
    Represents a business workflow extracted
    from the source code.
    """

    id: str

    name: str

    description: str

    domain: str

    trigger: Optional[str] = None

    steps: List[WorkflowStep] = Field(
        default_factory=list
    )

    business_rules: List[str] = Field(
        default_factory=list
    )

    source_files: List[str] = Field(
        default_factory=list
    )