import hashlib
import json
import re
from pathlib import Path
from typing import Iterable
import os


LANGUAGES = {
    ".py": "Python", ".js": "JavaScript", ".jsx": "JavaScript",
    ".ts": "TypeScript", ".tsx": "TypeScript", ".java": "Java",
    ".cs": "C#", ".php": "PHP", ".go": "Go", ".rb": "Ruby",
    ".sql": "SQL", ".xml": "XML", ".json": "JSON", ".yaml": "YAML",
    ".yml": "YAML", ".kt": "Kotlin", ".swift": "Swift",
}

IGNORE_DIRS = {
    ".git", ".github", ".venv", "venv", "node_modules", "__pycache__",
    "dist", "build", "bin", "obj", ".idea", ".vscode", "coverage",
    "vendor", "libs", "fonts",
}

SECRET_PATTERNS = [
    re.compile(r"(?i)(aws_secret_access_key|aws_access_key_id|github_pat|api_key|secret_key)\s*[:=]\s*['\"][^'\"]+"),
    re.compile(r"(?i)(password|passwd|token)\s*[:=]\s*['\"][^'\"]+"),
]

BUSINESS_WORDS = re.compile(
    r"\b(order|checkout|cart|payment|invoice|customer|user|product|catalog|"
    r"inventory|stock|discount|promotion|coupon|price|tax|shipping|"
    r"approval|status|eligible|eligibility|validate|cancel|return|refund|"
    r"booking|registration|claim|policy|account|formula|ingredient|supplier|"
    r"compliance|regulatory|workflow|batch|purchase|shipment|employee)\b",
    re.I,
)

CONTROL_WORDS = re.compile(
    r"\b(if|else|elif|switch|case|when|unless|for|while|try|catch|throw|"
    r"return|validate|assert|raise|reject|approve|cancel)\b",
    re.I,
)

SQL_TABLE = re.compile(
    r"\b(?:FROM|JOIN|UPDATE|INTO|TABLE)\s+[`\"\[]?([A-Za-z_][\w$-]*)",
    re.I,
)

SQL_STATEMENT = re.compile(
    r"\b(?:SELECT|INSERT\s+INTO|UPDATE|DELETE\s+FROM|CREATE\s+TABLE|ALTER\s+TABLE)\b",
    re.I,
)

ENDPOINT_PATTERNS = [
    re.compile(r'@\w+\.(get|post|put|patch|delete)\s*\(\s*["\']([^"\']+)', re.I),
    re.compile(r'@(GetMapping|PostMapping|PutMapping|PatchMapping|DeleteMapping)\s*\(\s*["\']?([^"\')]+)', re.I),
    re.compile(r'\b(GET|POST|PUT|PATCH|DELETE)\s+["\']?(/[A-Za-z0-9_{}$:/.-]+)', re.I),
]

FUNCTION_PATTERNS = [
    re.compile(r'^\s*(?:async\s+)?def\s+([A-Za-z_]\w*)\s*\(', re.M),
    re.compile(r'^\s*(?:export\s+)?(?:async\s+)?function\s+([A-Za-z_$]\w*)\s*\(', re.M),
    re.compile(r'^\s*(?:public|private|protected|static|\s)+\s*[A-Za-z_<>\[\], ?]+\s+([A-Za-z_]\w*)\s*\(', re.M),
    re.compile(r'^\s*func\s+(?:\([^)]*\)\s*)?([A-Za-z_]\w*)\s*\(', re.M),
]

CLASS_PATTERN = re.compile(r'^\s*(?:class|interface|struct)\s+([A-Za-z_]\w*)', re.M)
IMPORT_PATTERNS = [
    re.compile(r'^\s*import\s+(.+)$', re.M),
    re.compile(r'^\s*from\s+([\w.]+)\s+import\s+(.+)$', re.M),
    re.compile(r'^\s*(?:using|require)\s+(.+)$', re.M),
]


class StaticAnalyzer:
    def __init__(self, max_files=800, max_file_bytes=250000, max_chunks=50):
        self.max_files = max_files
        self.max_file_bytes = max_file_bytes
        self.max_chunks = max_chunks
    @staticmethod
    def _iter_candidate_files(root: Path):
        dir_count = 0
        for dirpath, dirnames, filenames in os.walk(root):
            dir_count += 1
            if filenames:
                print(f"[static-analyzer] entering dir #{dir_count}: {dirpath} ({len(filenames)} files, {len(dirnames)} subdirs)")
            dirnames[:] = sorted(d for d in dirnames if d not in IGNORE_DIRS)
            for filename in sorted(filenames):
                yield Path(dirpath) / filename


    def analyze(self, root: Path) -> dict:
        files = []
        chunks = []
        secret_hits = []

        for path in self._iter_candidate_files(root):
            if not path.is_file():
                continue
            language = LANGUAGES.get(path.suffix.lower())
            if not language:
                continue
            if len(files) >= self.max_files:
                break

            try:
                print(f"[static-analyzer] stat: {path}")
                size = path.stat().st_size
                if size > self.max_file_bytes:
                    continue
                print(f"[static-analyzer] reading ({size} bytes): {path}")
                source = path.read_text(encoding="utf-8", errors="ignore")
                print(f"[static-analyzer] read OK: {path}")
            except OSError as exc:
                print(f"[static-analyzer] OSError on {path}: {exc}")
                continue

            rel = path.relative_to(root).as_posix()
            print(f"[static-analyzer] analyzing content: {rel} ({len(source)} chars)")
            info = self._analyze_file(rel, language, source)
            files.append(info)
            print(f"[static-analyzer] done ({len(files)}/{self.max_files}): {rel}")

            if any(pattern.search(source) for pattern in SECRET_PATTERNS):
                secret_hits.append(rel)

            lines = source.splitlines()
            for start in range(0, len(lines), 180):
                if len(chunks) >= self.max_chunks:
                    break
                text = "\n".join(lines[start:start + 180])
                if not text.strip():
                    continue
                relevance = bool(BUSINESS_WORDS.search(text) or SQL_STATEMENT.search(text))
                if relevance or len(chunks) < min(10, self.max_chunks):
                    chunks.append({
                        "chunk_id": hashlib.sha1(f"{rel}:{start}".encode()).hexdigest()[:14],
                        "path": rel,
                        "language": language,
                        "start_line": start + 1,
                        "end_line": min(start + 180, len(lines)),
                        "text": self.redact_secrets(text),
                        "business_relevance": relevance,
                        "control_count": len(CONTROL_WORDS.findall(text)),
                    })

        return {
            "file_count": len(files),
            "chunk_count": len(chunks),
            "languages": self._counts(files, "language"),
            "files": files,
            "chunks": chunks,
            "potential_secret_files": secret_hits,
        }

    def _analyze_file(self, path, language, source):
        functions = []
        for pattern in FUNCTION_PATTERNS:
            functions.extend(pattern.findall(source))
        classes = CLASS_PATTERN.findall(source)

        endpoints = []
        for pattern in ENDPOINT_PATTERNS:
            for match in pattern.findall(source):
                if isinstance(match, tuple):
                    endpoints.append({"method": match[0].upper(), "path": match[1]})
                else:
                    endpoints.append({"method": "UNKNOWN", "path": match})

        tables = sorted(set(x for x in SQL_TABLE.findall(source) if x.lower() not in {"select", "where"}))
        imports = []
        for pattern in IMPORT_PATTERNS:
            for match in pattern.findall(source):
                imports.append(" ".join(match) if isinstance(match, tuple) else match)

        rules = []
        lines = source.splitlines()
        for number, line in enumerate(lines, 1):
            if CONTROL_WORDS.search(line) and BUSINESS_WORDS.search(line):
                rules.append({
                    "line": number,
                    "text": self.redact_secrets(line.strip())[:500],
                })

        return {
            "path": path,
            "language": language,
            "lines": len(lines),
            "bytes": len(source.encode("utf-8")),
            "functions": sorted(set(str(x) for x in functions if x)),
            "classes": sorted(set(classes)),
            "endpoints": self._dedupe_dicts(endpoints)[:100],
            "database_tables": tables[:100],
            "imports": sorted(set(str(x) for x in imports))[:100],
            "business_rule_candidates": rules[:100],
        }

    @staticmethod
    def redact_secrets(text):
        result = text
        for pattern in SECRET_PATTERNS:
            result = pattern.sub(lambda m: m.group(0).split("=", 1)[0] + "=<REDACTED>" if "=" in m.group(0) else "<REDACTED>", result)
        return result

    @staticmethod
    def _dedupe_dicts(items):
        seen = set()
        result = []
        for item in items:
            key = (item.get("method"), item.get("path"))
            if key not in seen:
                seen.add(key)
                result.append(item)
        return result

    @staticmethod
    def _counts(items, key):
        out = {}
        for item in items:
            value = item[key]
            out[value] = out.get(value, 0) + 1
        return out
