from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import re
from typing import Any


PROMOTION_CANDIDATES_FILE = "PROMOTION_CANDIDATES.md"

MEMORY_TYPE_BY_FILE = {
    "LEARNINGS.md": "learning",
    "ERRORS.md": "error",
    "FEATURE_REQUESTS.md": "feature_request",
    "POLICY_CANDIDATES.md": "policy_candidate",
    "REGRESSION_TESTS.md": "regression_test",
    "GLOBAL_LEARNINGS.md": "global_learning",
    "GLOBAL_ERRORS.md": "global_error",
    "GLOBAL_FEATURE_REQUESTS.md": "global_feature_request",
}

MEMORY_TYPE_BY_ID_PREFIX = {
    "LRN": "learning",
    "ERR": "error",
    "FEAT": "feature_request",
    "POL": "policy_candidate",
    "REG": "regression_test",
}


@dataclass
class PromotionCandidateView:
    promo_id: str
    target_skill: str
    source_memory_ids: list[str]
    source_memory_file: str
    source_memory_type: str
    occurrence_count: int
    summary: str
    proposed_change: str
    evaluation_plan: str
    rollback_plan: str
    suggested_target_files: list[str]
    status: str
    promotion_score: float | str = "legacy"
    promotion_decision: str = ""
    reason: str = ""
    eligible_target: str = ""
    safety_risk: str = ""
    attribution_confidence: str = ""
    source_memory_exists: bool = True
    missing_source_memory_ids: list[str] | None = None
    error_code: str = ""
    suggested_action: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class PromotionBrowser:
    """Read-only browser for promotion candidates stored in markdown memory."""

    def __init__(
        self,
        *,
        skills_dir: Path | str,
        global_memory_dir: Path | str,
        project_root: Path | str | None = None,
    ):
        self.skills_dir = Path(skills_dir)
        self.global_memory_dir = Path(global_memory_dir)
        self.project_root = Path(project_root) if project_root else self.global_memory_dir.parent

    def list_candidates(self) -> list[PromotionCandidateView]:
        return [
            self._view_from_record(record)
            for record in self._read_promotion_records()
        ]

    def get_candidate(self, promo_id: str) -> PromotionCandidateView | None:
        wanted = promo_id.strip()
        if not wanted:
            return None
        for candidate in self.list_candidates():
            if candidate.promo_id == wanted:
                return candidate
        return None

    def source_memory_text(self, candidate: PromotionCandidateView) -> str:
        if not candidate.source_memory_file:
            return ""
        path = (self.project_root / candidate.source_memory_file).resolve()
        try:
            path.relative_to(self.project_root.resolve())
        except ValueError:
            return ""
        if not path.exists():
            return ""
        text = path.read_text(encoding="utf-8")
        records = _read_heading_records(path, text)
        if not candidate.source_memory_ids:
            return text
        wanted = set(candidate.source_memory_ids)
        blocks = [
            str(record.get("block", ""))
            for record in records
            if str(record["record_id"]) in wanted
        ]
        return "\n".join(blocks)

    def _read_promotion_records(self) -> list[dict[str, Any]]:
        path = self.global_memory_dir / PROMOTION_CANDIDATES_FILE
        if not path.exists():
            return []
        text = path.read_text(encoding="utf-8")
        records = _read_heading_records(path, text)
        if records:
            return records
        return _read_table_records(path, text)

    def _view_from_record(self, record: dict[str, Any]) -> PromotionCandidateView:
        fields = record["fields"]
        is_legacy = not _has_eligibility_fields(fields)
        promo_id = _first_field(fields, "Candidate ID", "Promo ID", "Promotion ID") or record["record_id"]
        summary = _first_field(fields, "Summary", "Proposed Change Summary") or record["title"]
        proposed_change = _first_field(fields, "Proposed Change", "Proposed Change Summary") or summary
        source_ids = _split_csv(
            _first_field(
                fields,
                "Source Memory IDs",
                "Source Memory ID",
                "Source Record IDs",
                "Source Record ID",
                "Record IDs",
                "Record ID",
            )
        )
        source = self._find_source_memory(source_ids)
        missing_source_ids = [
            source_id
            for source_id in source_ids
            if source_id not in set(source.get("found_ids", []))
        ]
        suggested_files = _split_csv(
            _first_field(fields, "Suggested Target Files", "Target Files", "Target File")
        )
        occurrence_count = _parse_int(
            _first_field(fields, "Occurrence Count", "Occurrences"),
            source.get("occurrence_count", 0),
        )
        return PromotionCandidateView(
            promo_id=promo_id,
            target_skill=_first_field(fields, "Target Skill") or "",
            source_memory_ids=source_ids,
            source_memory_file=_first_field(fields, "Source Memory File") or source.get("file", ""),
            source_memory_type=_first_field(fields, "Source Memory Type") or source.get("type", ""),
            occurrence_count=occurrence_count,
            summary=summary,
            proposed_change=proposed_change,
            evaluation_plan=_first_field(fields, "Evaluation Plan") or "",
            rollback_plan=_first_field(fields, "Rollback Plan") or "",
            suggested_target_files=suggested_files,
            status=_first_field(fields, "Status") or "proposed",
            promotion_score=(
                "legacy"
                if is_legacy
                else _parse_float(_first_field(fields, "Promotion Score"), 0.0)
            ),
            promotion_decision=_first_field(fields, "Promotion Decision") or ("legacy" if is_legacy else ""),
            reason=_first_field(fields, "Reason", "Promotion Reason") or "",
            eligible_target=_first_field(fields, "Eligible Target") or ("legacy" if is_legacy else ""),
            safety_risk=_first_field(fields, "Safety Risk") or "",
            attribution_confidence=_first_field(fields, "Attribution Confidence") or "",
            source_memory_exists=not missing_source_ids,
            missing_source_memory_ids=missing_source_ids,
            error_code="SOURCE_MEMORY_NOT_FOUND" if missing_source_ids else "",
            suggested_action=(
                "archive_stale_promo_or_generate_new_candidate"
                if missing_source_ids
                else ""
            ),
        )

    def _find_source_memory(self, source_ids: list[str]) -> dict[str, Any]:
        if not source_ids:
            return {}
        wanted = set(source_ids)
        for path in self._memory_paths():
            if not path.exists():
                continue
            for record in _read_heading_records(path, path.read_text(encoding="utf-8")):
                fields = record["fields"]
                candidates = {
                    str(record["record_id"]),
                    fields.get("ID", ""),
                    fields.get("Record ID", ""),
                }
                if wanted & {item for item in candidates if item}:
                    return {
                        "file": self._display_path(path),
                        "type": MEMORY_TYPE_BY_FILE.get(path.name, path.stem.lower()),
                        "occurrence_count": _parse_int(fields.get("Occurrence Count"), 0),
                        "found_ids": sorted(wanted & {item for item in candidates if item}),
                    }
        prefix = source_ids[0].split("-", 1)[0].upper()
        return {"type": MEMORY_TYPE_BY_ID_PREFIX.get(prefix, ""), "found_ids": []}

    def _memory_paths(self) -> list[Path]:
        paths = list(self.skills_dir.glob("*/memory/*.md"))
        paths.extend(
            path
            for path in self.global_memory_dir.glob("*.md")
            if path.name != PROMOTION_CANDIDATES_FILE
        )
        return sorted(paths)

    def _display_path(self, path: Path) -> str:
        try:
            return path.resolve().relative_to(self.project_root.resolve()).as_posix()
        except ValueError:
            return path.as_posix()


def format_promotion_list(candidates: list[PromotionCandidateView]) -> str:
    if not candidates:
        return "No promotion candidates."
    lines = [
        "Promotion Candidates:",
    ]
    for candidate in candidates:
        data = candidate.to_dict()
        files = ", ".join(data["suggested_target_files"]) or "(none)"
        source_type = data["source_memory_type"] or "(unknown)"
        summary = data["summary"] or "(no summary)"
        lines.append(
            f"{data['promo_id']} [{data['status']}] decision={data['promotion_decision'] or '-'} "
            f"target={data['eligible_target'] or '-'} target_skill={data['target_skill'] or '-'} "
            f"source_memory_type={source_type} occurrence_count={data['occurrence_count']} "
            f"promotion_score={data['promotion_score']} "
            f"suggested_target_files={files} summary={summary}"
        )
    return "\n".join(lines)


def format_promotion_detail(candidate: PromotionCandidateView | None, promo_id: str) -> str:
    if not candidate:
        return f"Unknown promo_id: {promo_id}"
    data = candidate.to_dict()
    return "\n".join(
        [
            f"promo_id: {data['promo_id']}",
            f"target_skill: {data['target_skill']}",
            f"source_memory_ids: {', '.join(data['source_memory_ids']) or '(none)'}",
            f"source_memory_file: {data['source_memory_file'] or '(unknown)'}",
            f"occurrence_count: {data['occurrence_count']}",
            f"summary: {data['summary']}",
            f"proposed_change: {data['proposed_change']}",
            f"evaluation_plan: {data['evaluation_plan']}",
            f"rollback_plan: {data['rollback_plan']}",
            f"suggested_target_files: {', '.join(data['suggested_target_files']) or '(none)'}",
            f"promotion_score: {data['promotion_score']}",
            f"promotion_decision: {data['promotion_decision'] or '(unknown)'}",
            f"reason: {data['reason'] or '(none)'}",
            f"eligible_target: {data['eligible_target'] or '(unknown)'}",
            f"safety_risk: {data['safety_risk'] or '(unknown)'}",
            f"attribution_confidence: {data['attribution_confidence'] or '(unknown)'}",
            f"status: {data['status']}",
        ]
    )


def _read_heading_records(path: Path, text: str) -> list[dict[str, Any]]:
    headings = list(re.finditer(r"(?m)^## .*$", text))
    records = []
    for index, match in enumerate(headings):
        start = match.start()
        end = headings[index + 1].start() if index + 1 < len(headings) else len(text)
        block = text[start:end]
        heading = match.group(0).removeprefix("## ").strip()
        record_id, title = _parse_heading(heading)
        records.append(
            {
                "path": path,
                "record_id": record_id,
                "title": title,
                "fields": _parse_fields(block),
                "block": block,
            }
        )
    return records


def _read_table_records(path: Path, text: str) -> list[dict[str, Any]]:
    lines = [line.strip() for line in text.splitlines() if line.strip().startswith("|")]
    if len(lines) < 2 or not re.fullmatch(r"\|?[\s:|-]+\|?", lines[1]):
        return []
    headers = _split_table_row(lines[0])
    records = []
    for line in lines[2:]:
        cells = _split_table_row(line)
        if len(cells) != len(headers):
            continue
        fields = dict(zip(headers, cells))
        record_id = _first_field(fields, "Candidate ID", "Promo ID", "Promotion ID") or ""
        records.append(
            {
                "path": path,
                "record_id": record_id,
                "title": _first_field(fields, "Summary", "Proposed Change Summary") or "",
                "fields": fields,
            }
        )
    return records


def _parse_heading(heading: str) -> tuple[str, str]:
    parts = heading.split(" - ", 1)
    if len(parts) == 2:
        return parts[0].strip(), parts[1].strip()
    return heading.strip(), ""


def _parse_fields(block: str) -> dict[str, str]:
    fields = {}
    for line in block.splitlines():
        stripped = line.strip()
        if not stripped.startswith("- ") or ":" not in stripped:
            continue
        key, value = stripped[2:].split(":", 1)
        fields[key.strip()] = value.strip()
    return fields


def _first_field(fields: dict[str, str], *names: str) -> str:
    lowered = {key.lower().replace("_", " "): value for key, value in fields.items()}
    for name in names:
        value = lowered.get(name.lower().replace("_", " "))
        if value:
            return value
    return ""


def _has_eligibility_fields(fields: dict[str, str]) -> bool:
    return bool(
        _first_field(fields, "Promotion Score")
        and _first_field(fields, "Promotion Decision")
        and _first_field(fields, "Eligible Target")
    )


def _split_csv(value: str) -> list[str]:
    if not value:
        return []
    return [
        item.strip()
        for item in re.split(r"[,;]", value)
        if item.strip()
    ]


def _parse_int(value: object, default: int = 0) -> int:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


def _parse_float(value: object, default: float = 0.0) -> float:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return default


def _split_table_row(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]
