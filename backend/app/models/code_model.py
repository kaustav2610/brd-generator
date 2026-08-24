from typing import List, Optional
from pydantic import BaseModel, Field


class FunctionInfo(BaseModel):
    """
    Represents a function/method discovered in source code.
    """

    name: str

    parameters: List[str] = Field(
        default_factory=list
    )

    return_type: Optional[str] = None

    file_path: str

    line_start: Optional[int] = None

    line_end: Optional[int] = None


class DatabaseTable(BaseModel):
    """
    Represents a database table discovered
    from SQL or application code.
    """

    name: str

    columns: List[str] = Field(
        default_factory=list
    )

    primary_key: Optional[str] = None

    foreign_keys: List[str] = Field(
        default_factory=list
    )

    source_file: Optional[str] = None


class ApiEndpoint(BaseModel):
    """
    Represents an API endpoint discovered
    from the application.
    """

    path: str

    method: Optional[str] = None

    handler: Optional[str] = None

    file_path: str


class DependencyInfo(BaseModel):
    """
    Represents a relationship between two
    source-code components.
    """

    source: str

    target: str

    dependency_type: str

    file_path: Optional[str] = None


class CodeFile(BaseModel):
    """
    Represents one analyzed source file.
    """

    path: str

    language: str

    lines_of_code: int = 0

    functions: List[FunctionInfo] = Field(
        default_factory=list
    )

    database_tables: List[DatabaseTable] = Field(
        default_factory=list
    )

    api_endpoints: List[ApiEndpoint] = Field(
        default_factory=list
    )

    dependencies: List[DependencyInfo] = Field(
        default_factory=list
    )