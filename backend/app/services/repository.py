import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import urlparse


class RepositoryIngestor:
    """Read-only GitHub/local repository ingestion."""

    def __init__(self, token: str = "", workspace_root: Path | None = None):
        self.token = token
        self.workspace_root = workspace_root or Path(tempfile.gettempdir())

    def fetch(self, source: str, branch: str | None = None) -> tuple[Path, bool]:
        local = Path(source)
        if local.exists() and (local / ".git").exists():
            return local.resolve(), False
        if local.exists() and local.is_dir():
            return local.resolve(), False

        parsed = urlparse(source)
        if parsed.scheme not in {"http", "https", "ssh"}:
            raise ValueError("Repository must be a local directory or GitHub HTTPS/SSH URL")

        target = Path(tempfile.mkdtemp(prefix="repo-intel-", dir=str(self.workspace_root)))
        env = os.environ.copy()
        askpass = None

        # GitHub HTTPS authentication without putting the token in the URL.
        if self.token and parsed.scheme in {"http", "https"}:
            askpass = target / "git-askpass"
            askpass.write_text(
                "#!/bin/sh\n"
                "case \"$1\" in\n"
                "*Username*) printf '%s\\n' x-access-token ;;\n"
                "*) printf '%s\\n' \"$GITHUB_TOKEN\" ;;\n"
                "esac\n",
                encoding="utf-8",
            )
            try:
                askpass.chmod(0o700)
            except OSError:
                pass

            env["GIT_ASKPASS"] = str(askpass)
            env["GITHUB_TOKEN"] = self.token
            env["GIT_TERMINAL_PROMPT"] = "0"

        destination = target / "repo"
        cmd = ["git", "clone", "--depth", "1"]
        if branch:
            cmd.extend(["--branch", branch])
        cmd.extend([source, str(destination)])

        try:
            completed = subprocess.run(
                cmd,
                check=True,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=600,
            )
        except Exception as exc:
            shutil.rmtree(target, ignore_errors=True)
            detail = getattr(exc, "stderr", "") or str(exc)
            raise RuntimeError(
                "GitHub repository clone failed. Verify URL, branch and read-only token. "
                f"Git: {detail[-1200:]}"
            ) from exc

        return destination, True

    @staticmethod
    def cleanup(repo_path: Path, temporary: bool) -> None:
        if temporary:
            shutil.rmtree(repo_path.parent, ignore_errors=True)
