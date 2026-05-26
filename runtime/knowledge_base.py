"""Local knowledge-base store: ingest + browse + Q&A context provider.

A knowledge base lives at ``.knowledge_bases/<kb_id>/`` with:
  - ``meta.json`` — name, description, source_type, source_url, counters
  - ``files/`` — file tree mirroring the original paths

Hard safety boundaries (covered by tests):
- All file lookups go through ``_safe_path`` which resolves and asserts
  the path is inside ``files/``. Symlinks, ``..`` segments and absolute
  paths cannot escape.
- ``add_files`` ignores any file whose individual size exceeds
  ``MAX_FILE_BYTES`` and stops once total size exceeds ``MAX_TOTAL_BYTES``.
- ``import_github`` only downloads the codeload tarball over HTTPS; no
  arbitrary git protocols. Owner / repo must match ``GITHUB_SLUG_RE``.
- Binary files are stored but their content is never returned inline;
  the API returns a ``"binary"`` placeholder so an attacker cannot
  exfiltrate raw bytes through the file-read endpoint.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import io
import json
import os
from pathlib import Path
import re
import shutil
import tarfile
import tempfile
import uuid
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


MAX_FILE_BYTES = 2 * 1024 * 1024          # 2 MB per file
MAX_TOTAL_BYTES = 100 * 1024 * 1024        # 100 MB per KB
MAX_QA_CONTEXT_BYTES = 30 * 1024           # 30 KB sent to LLM per Q&A call
DEFAULT_BRANCH_CANDIDATES = ("main", "master")

GITHUB_SLUG_RE = re.compile(r"^https?://(?:www\.)?github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+?)(?:\.git)?(?:/.*)?$")

TEXT_EXTENSIONS = {
    ".md", ".markdown", ".txt", ".rst", ".org",
    ".py", ".pyi", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs",
    ".go", ".rs", ".java", ".kt", ".scala", ".swift", ".m", ".mm",
    ".c", ".h", ".hpp", ".hh", ".cc", ".cpp", ".cxx",
    ".cs", ".vb", ".fs", ".php", ".rb", ".pl", ".lua", ".r",
    ".sh", ".bash", ".zsh", ".fish", ".ps1", ".bat", ".cmd",
    ".sql", ".graphql", ".gql", ".proto",
    ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".env",
    ".xml", ".html", ".htm", ".css", ".scss", ".sass", ".less",
    ".csv", ".tsv", ".jsonl", ".ndjson",
    ".lock", ".log",
    ".dockerfile", ".gitignore", ".gitattributes",
}

CODE_LIKE_EXTENSIONS = {
    ".py", ".pyi", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs",
    ".go", ".rs", ".java", ".kt", ".scala", ".swift", ".m", ".mm",
    ".c", ".h", ".hpp", ".hh", ".cc", ".cpp", ".cxx",
    ".cs", ".vb", ".fs", ".php", ".rb", ".pl", ".lua", ".r",
    ".sh", ".bash", ".zsh", ".fish", ".ps1", ".bat", ".cmd",
    ".sql", ".graphql", ".gql", ".proto",
    ".html", ".htm", ".css", ".scss", ".sass", ".less",
}

SKIP_DIR_PREFIXES = (".git/", "node_modules/", ".venv/", "venv/", "__pycache__/", "dist/", "build/", ".next/", ".cache/")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _short_id() -> str:
    return f"KB-{uuid.uuid4().hex[:8].upper()}"


@dataclass
class KnowledgeBaseMeta:
    kb_id: str
    name: str
    description: str
    source_type: str  # "local" | "github"
    source_url: str
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)
    file_count: int = 0
    total_bytes: int = 0
    truncated: bool = False
    import_error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class KnowledgeBaseStore:
    """File-system backed KB store with ingest and read APIs."""

    def __init__(self, project_root: Path | str):
        self.root = Path(project_root) / ".knowledge_bases"
        self.root.mkdir(parents=True, exist_ok=True)

    # ---- listing / metadata -------------------------------------------

    def list(self) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for kb_dir in sorted(self.root.iterdir()):
            if not kb_dir.is_dir():
                continue
            meta = self._read_meta(kb_dir)
            if meta is None:
                continue
            items.append(meta)
        return items

    def get(self, kb_id: str) -> dict[str, Any] | None:
        kb_dir = self._kb_dir(kb_id)
        if kb_dir is None:
            return None
        return self._read_meta(kb_dir)

    # ---- create / delete ----------------------------------------------

    def create(
        self,
        *,
        name: str,
        description: str = "",
        source_type: str = "local",
        source_url: str = "",
    ) -> dict[str, Any]:
        if source_type not in {"local", "github"}:
            raise ValueError(f"unsupported source_type: {source_type}")
        clean_name = (name or "").strip()
        if not clean_name:
            raise ValueError("name is required")
        meta = KnowledgeBaseMeta(
            kb_id=_short_id(),
            name=clean_name,
            description=(description or "").strip(),
            source_type=source_type,
            source_url=(source_url or "").strip(),
        )
        kb_dir = self.root / meta.kb_id
        (kb_dir / "files").mkdir(parents=True, exist_ok=False)
        self._write_meta(kb_dir, meta.to_dict())
        return meta.to_dict()

    def delete(self, kb_id: str) -> bool:
        kb_dir = self._kb_dir(kb_id)
        if kb_dir is None:
            return False
        shutil.rmtree(kb_dir)
        return True

    # ---- file ingest --------------------------------------------------

    def add_files(self, kb_id: str, files: dict[str, bytes]) -> dict[str, Any]:
        kb_dir = self._require_kb_dir(kb_id)
        files_root = kb_dir / "files"
        meta = self._read_meta(kb_dir) or {}
        total_bytes = int(meta.get("total_bytes", 0) or 0)
        file_count = int(meta.get("file_count", 0) or 0)
        truncated = bool(meta.get("truncated", False))
        for raw_path, data in files.items():
            if not isinstance(data, (bytes, bytearray)):
                continue
            payload = bytes(data)
            if len(payload) > MAX_FILE_BYTES:
                truncated = True
                continue
            target = self._safe_path(files_root, raw_path)
            if target is None:
                continue
            if total_bytes + len(payload) > MAX_TOTAL_BYTES:
                truncated = True
                break
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(payload)
            total_bytes += len(payload)
            file_count += 1
        meta["file_count"] = file_count
        meta["total_bytes"] = total_bytes
        meta["truncated"] = truncated
        meta["updated_at"] = utc_now()
        self._write_meta(kb_dir, meta)
        return meta

    # ---- github tarball import ---------------------------------------

    def import_github(
        self,
        kb_id: str,
        repo_url: str,
        *,
        branch: str = "",
        path_prefix: str = "",
    ) -> dict[str, Any]:
        kb_dir = self._require_kb_dir(kb_id)
        match = GITHUB_SLUG_RE.match(repo_url.strip())
        if not match:
            return self._record_import_error(kb_dir, "repo_url must be a https://github.com/<owner>/<repo> URL")
        owner, repo = match.group(1), match.group(2)
        if repo.endswith(".git"):
            repo = repo[: -len(".git")]
        candidates = [branch] if branch else list(DEFAULT_BRANCH_CANDIDATES)
        last_error = ""
        for candidate in candidates:
            if not candidate:
                continue
            try:
                payload = self._fetch_tarball(owner, repo, candidate)
            except (HTTPError, URLError, TimeoutError) as exc:
                last_error = f"download failed for branch {candidate}: {exc}"
                continue
            if not payload:
                last_error = f"empty tarball for branch {candidate}"
                continue
            try:
                files = self._read_tarball(payload, path_prefix)
            except (tarfile.TarError, ValueError) as exc:
                last_error = f"tarball error: {exc}"
                continue
            meta = self.add_files(kb_id, files)
            meta["source_url"] = f"https://github.com/{owner}/{repo}"
            meta["source_type"] = "github"
            meta["import_error"] = ""
            self._write_meta(kb_dir, meta)
            return meta
        return self._record_import_error(
            kb_dir,
            last_error or f"could not download tarball for {owner}/{repo}",
        )

    # ---- browse / read -----------------------------------------------

    def tree(self, kb_id: str) -> list[dict[str, Any]]:
        kb_dir = self._require_kb_dir(kb_id)
        files_root = kb_dir / "files"
        entries: list[dict[str, Any]] = []
        if not files_root.exists():
            return entries
        for path in sorted(files_root.rglob("*")):
            if not path.is_file():
                continue
            relative = path.relative_to(files_root).as_posix()
            entries.append(
                {
                    "path": relative,
                    "size": path.stat().st_size,
                    "kind": _classify_kind(path),
                }
            )
        return entries

    def read(self, kb_id: str, relative_path: str) -> dict[str, Any]:
        kb_dir = self._require_kb_dir(kb_id)
        files_root = kb_dir / "files"
        target = self._safe_path(files_root, relative_path)
        if target is None or not target.exists() or not target.is_file():
            raise FileNotFoundError(f"file not found in kb: {relative_path}")
        kind = _classify_kind(target)
        size = target.stat().st_size
        if kind == "binary":
            return {
                "path": relative_path,
                "kind": "binary",
                "size": size,
                "content": "",
                "truncated": False,
            }
        raw = target.read_bytes()
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            try:
                text = raw.decode("utf-8", errors="replace")
            except UnicodeDecodeError:
                return {
                    "path": relative_path,
                    "kind": "binary",
                    "size": size,
                    "content": "",
                    "truncated": False,
                }
        truncated = False
        max_chars = 200_000
        if len(text) > max_chars:
            text = text[:max_chars]
            truncated = True
        return {
            "path": relative_path,
            "kind": kind,
            "size": size,
            "content": text,
            "truncated": truncated,
        }

    # ---- Q&A context provider ----------------------------------------

    def qa_context(self, kb_ids: list[str], *, byte_budget: int = MAX_QA_CONTEXT_BYTES) -> dict[str, Any]:
        """Concatenate text files from selected KBs into a single payload
        capped at ``byte_budget`` bytes. Returns the payload plus a list
        of files actually consulted so callers can show provenance.
        """
        chunks: list[str] = []
        sources: list[dict[str, Any]] = []
        used = 0
        for kb_id in kb_ids[:3]:  # hard cap of 3 KBs at the boundary
            meta = self.get(kb_id)
            if meta is None:
                continue
            for entry in self.tree(kb_id):
                if entry["kind"] == "binary":
                    continue
                if used >= byte_budget:
                    break
                try:
                    payload = self.read(kb_id, entry["path"])
                except FileNotFoundError:
                    continue
                if payload["kind"] == "binary":
                    continue
                remaining = byte_budget - used
                excerpt = payload["content"][: max(0, remaining)]
                if not excerpt.strip():
                    continue
                header = f"\n\n--- {meta['name']}::{entry['path']} ---\n"
                chunks.append(header + excerpt)
                used += len(header) + len(excerpt)
                sources.append({
                    "kb_id": kb_id,
                    "kb_name": meta["name"],
                    "path": entry["path"],
                    "size": entry["size"],
                })
            if used >= byte_budget:
                break
        return {
            "context": "".join(chunks),
            "sources": sources,
            "byte_budget": byte_budget,
            "used_bytes": used,
        }

    # ---- internals ----------------------------------------------------

    def _kb_dir(self, kb_id: str) -> Path | None:
        if not kb_id or not re.fullmatch(r"KB-[A-Z0-9]{4,}", kb_id):
            return None
        kb_dir = self.root / kb_id
        if not kb_dir.exists() or not kb_dir.is_dir():
            return None
        return kb_dir

    def _require_kb_dir(self, kb_id: str) -> Path:
        kb_dir = self._kb_dir(kb_id)
        if kb_dir is None:
            raise FileNotFoundError(f"unknown kb_id: {kb_id}")
        return kb_dir

    def _read_meta(self, kb_dir: Path) -> dict[str, Any] | None:
        meta_path = kb_dir / "meta.json"
        if not meta_path.exists():
            return None
        try:
            return json.loads(meta_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None

    def _write_meta(self, kb_dir: Path, meta: dict[str, Any]) -> None:
        (kb_dir / "meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")

    def _safe_path(self, base: Path, raw_path: str) -> Path | None:
        cleaned = (raw_path or "").replace("\\", "/").strip().lstrip("/")
        if not cleaned or cleaned.startswith(".."):
            return None
        if any(part in {"", ".."} for part in cleaned.split("/")):
            return None
        for prefix in SKIP_DIR_PREFIXES:
            if cleaned.startswith(prefix):
                return None
        if "\x00" in cleaned:
            return None
        candidate = (base / cleaned).resolve()
        try:
            candidate.relative_to(base.resolve())
        except ValueError:
            return None
        return candidate

    def _record_import_error(self, kb_dir: Path, message: str) -> dict[str, Any]:
        meta = self._read_meta(kb_dir) or {}
        meta["import_error"] = message
        meta["updated_at"] = utc_now()
        self._write_meta(kb_dir, meta)
        return meta

    def _fetch_tarball(self, owner: str, repo: str, branch: str) -> bytes:
        url = f"https://codeload.github.com/{owner}/{repo}/tar.gz/refs/heads/{branch}"
        request = Request(url, headers={"User-Agent": "harness_agent/kb"})
        with urlopen(request, timeout=30) as response:
            return response.read()

    def _read_tarball(self, payload: bytes, path_prefix: str) -> dict[str, bytes]:
        prefix = (path_prefix or "").strip("/")
        files: dict[str, bytes] = {}
        with tarfile.open(fileobj=io.BytesIO(payload), mode="r:gz") as tar:
            for member in tar:
                if not member.isfile():
                    continue
                if member.size > MAX_FILE_BYTES:
                    continue
                # tarball wraps everything in <repo>-<branch>/. Strip that
                # leading segment then optional path_prefix.
                rel = member.name.split("/", 1)[1] if "/" in member.name else member.name
                if prefix and not rel.startswith(prefix + "/") and rel != prefix:
                    continue
                if prefix:
                    rel = rel[len(prefix) + 1 :] if rel.startswith(prefix + "/") else rel
                if not rel or any(rel.startswith(skip) for skip in SKIP_DIR_PREFIXES):
                    continue
                fobj = tar.extractfile(member)
                if fobj is None:
                    continue
                files[rel] = fobj.read()
        return files


def _classify_kind(path: Path) -> str:
    suffix = path.suffix.lower()
    name = path.name.lower()
    if suffix in CODE_LIKE_EXTENSIONS:
        return "code"
    if suffix in TEXT_EXTENSIONS or name in {"makefile", "dockerfile", "readme", "license", "license.txt"}:
        return "text"
    # Empty extension files might still be plain text scripts; sniff first bytes.
    if path.exists() and path.is_file():
        try:
            head = path.read_bytes()[:512]
        except OSError:
            return "binary"
        if not head:
            return "text"
        if b"\x00" in head:
            return "binary"
        try:
            head.decode("utf-8")
            return "text"
        except UnicodeDecodeError:
            return "binary"
    return "binary"


def normalize_kb_id(value: str) -> str:
    cleaned = (value or "").strip().upper()
    if not cleaned.startswith("KB-"):
        return ""
    return cleaned
