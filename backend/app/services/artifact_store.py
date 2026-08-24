from pathlib import Path
import boto3
from botocore.config import Config

S3_CONFIG = Config(
    connect_timeout=10,
    read_timeout=30,
    retries={"max_attempts": 3, "mode": "standard"},
)


class ArtifactStore:
    def __init__(self, region: str, bucket: str, prefix: str):
        self.bucket = bucket
        self.prefix = prefix.strip("/")
        self.client = boto3.client("s3", region_name=region, config=S3_CONFIG) if bucket else None

    def upload_directory(self, run_id: str, directory: Path) -> list[str]:
        if not self.client:
            return []

        locations = []
        base = f"{self.prefix}/{run_id}".strip("/")

        for path in directory.rglob("*"):
            if not path.is_file():
                continue
            key = f"{base}/{path.relative_to(directory).as_posix()}"
            self.client.upload_file(str(path), self.bucket, key)
            locations.append(f"s3://{self.bucket}/{key}")

        return locations

    def upload_source(self, run_id: str, source_root: Path) -> list[str]:
        if not self.client:
            return []

        locations = []
        base = f"{self.prefix}/{run_id}/source".strip("/")

        for path in source_root.rglob("*"):
            if not path.is_file():
                continue
            if ".git" in path.parts:
                continue
            key = f"{base}/{path.relative_to(source_root).as_posix()}"
            self.client.upload_file(str(path), self.bucket, key)
            locations.append(f"s3://{self.bucket}/{key}")

        return locations


    def upload_file(self, run_id: str, path: Path) -> str | None:
        if not self.client:
            return None
        key = f"{self.prefix}/{run_id}/{path.name}".strip("/")
        self.client.upload_file(str(path), self.bucket, key)
        return f"s3://{self.bucket}/{key}"
