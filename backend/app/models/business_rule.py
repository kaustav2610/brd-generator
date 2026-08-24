from typing import List, Optional
from pydantic import BaseModel, Field


class BusinessRule(BaseModel):
    """
    Represents a business rule inferred from
    application code.
    """

    id: str

    name: str

    description: str

    source_file: str

    source_function: Optional[str] = None

    conditions: List[str] = Field(
        default_factory=list
    )

    actions: List[str] = Field(
        default_factory=list
    )

    entities: List[str] = Field(
        default_factory=list
    )

    confidence: float = 0.0