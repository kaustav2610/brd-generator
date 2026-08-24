import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Settings:
    aws_region: str = os.getenv("AWS_REGION", os.getenv("AWS_DEFAULT_REGION", "ap-south-1"))
    bedrock_model_id: str = os.getenv("BEDROCK_MODEL_ID", "amazon.nova-pro-v1:0")
    s3_bucket_name: str = os.getenv("S3_BUCKET_NAME", "")
    s3_prefix: str = os.getenv("S3_PREFIX", "repository-intelligence")
    github_token: str = os.getenv("GITHUB_TOKEN", "")

    max_files: int = int(os.getenv("MAX_FILES", "800"))
    max_file_bytes: int = int(os.getenv("MAX_FILE_BYTES", "250000"))
    max_code_chunks: int = int(os.getenv("MAX_CODE_CHUNKS", "50"))
    max_bedrock_chunks: int = int(os.getenv("MAX_BEDROCK_CHUNKS", "25"))

    upload_source_to_s3: bool = os.getenv(
        "UPLOAD_SOURCE_TO_S3", "false"
    ).lower() == "true"

    output_dir: Path = BASE_DIR / "output"
    workspace_dir: Path = BASE_DIR / "workspaces"


settings = Settings()
