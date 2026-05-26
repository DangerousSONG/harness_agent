"""BM25 retrieval over knowledge-base file chunks. Zero external deps.

Pipeline:
  add_files / import_github → chunk_text per file → tokenize → index.json
  qa_context(kb_ids, query=...) → BM25Search.query → top-k chunks
The chat orchestrator passes the user message as `query`, so KB-aware
answers go through this path. Backward compat: when a KB was indexed
before this module shipped, ``qa_context`` falls back to naive
concatenation.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import math
import re
from typing import Any


CHUNK_TARGET_CHARS = 800
CHUNK_OVERLAP_CHARS = 100
MAX_CHUNKS_PER_KB = 5000
DEFAULT_TOP_K = 8
K1 = 1.5
B = 0.75

TOKEN_RE = re.compile(r"[a-z0-9_]+")
CJK_RUN_RE = re.compile(r"[一-鿿]+")
PARAGRAPH_BREAK_RE = re.compile(r"\n\s*\n")

STOPWORDS = {
    # English
    "the", "a", "an", "and", "or", "is", "are", "was", "were", "be", "been", "being",
    "to", "of", "in", "on", "for", "with", "by", "as", "at", "from", "this", "that",
    "it", "its", "if", "then", "else", "but", "not", "no", "yes", "do", "does", "did",
    "have", "has", "had", "i", "you", "he", "she", "we", "they", "them", "us",
    # Chinese (high-frequency 2-grams are usually safe to keep; only drop single-char fluff)
    "的", "了", "是", "在", "和", "与", "我", "你", "他", "她", "它", "们", "也", "都",
    "对", "把", "被", "让", "给", "向", "从", "到", "要", "就", "去", "来", "上", "下",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def tokenize(text: str) -> list[str]:
    """Lowercase ASCII word tokens (len ≥ 2) plus CJK character bigrams.

    Splitting CJK into 2-grams gives reasonable recall for Chinese
    queries without needing a real segmenter. Stopwords are dropped.
    """
    lowered = text.lower()
    tokens: list[str] = [t for t in TOKEN_RE.findall(lowered) if len(t) >= 2 and t not in STOPWORDS]
    for run in CJK_RUN_RE.findall(text):
        if len(run) == 1:
            if run not in STOPWORDS:
                tokens.append(run)
            continue
        for i in range(len(run) - 1):
            bigram = run[i:i + 2]
            if bigram and bigram not in STOPWORDS:
                tokens.append(bigram)
    return tokens


def chunk_text(content: str, *, target: int = CHUNK_TARGET_CHARS, overlap: int = CHUNK_OVERLAP_CHARS) -> list[dict[str, Any]]:
    """Return a list of {start, end, text} chunks. We split on paragraph
    breaks when possible, fall through to hard-cut with overlap when a
    single paragraph exceeds the target."""
    if not content:
        return []
    if len(content) <= target:
        return [{"start": 0, "end": len(content), "text": content}]

    paragraphs: list[tuple[int, int, str]] = []
    cursor = 0
    for match in PARAGRAPH_BREAK_RE.finditer(content):
        para = content[cursor:match.start()]
        if para.strip():
            paragraphs.append((cursor, match.start(), para))
        cursor = match.end()
    tail = content[cursor:]
    if tail.strip():
        paragraphs.append((cursor, len(content), tail))

    chunks: list[dict[str, Any]] = []
    buf_text = ""
    buf_start = 0
    buf_end = 0

    def flush() -> None:
        nonlocal buf_text, buf_start, buf_end
        if buf_text.strip():
            chunks.append({"start": buf_start, "end": buf_end, "text": buf_text})
        buf_text = ""
        buf_start = 0
        buf_end = 0

    for (p_start, p_end, p_text) in paragraphs:
        # Single paragraph too big: hard-split with overlap.
        if len(p_text) > target:
            flush()
            local = 0
            while local < len(p_text):
                slice_end = min(len(p_text), local + target)
                chunks.append({
                    "start": p_start + local,
                    "end": p_start + slice_end,
                    "text": p_text[local:slice_end],
                })
                if slice_end >= len(p_text):
                    break
                local = slice_end - overlap
            continue
        # Otherwise pack paragraphs together up to target.
        separator = "\n\n" if buf_text else ""
        if len(buf_text) + len(separator) + len(p_text) > target and buf_text:
            flush()
            separator = ""
        if not buf_text:
            buf_start = p_start
        buf_text = buf_text + separator + p_text
        buf_end = p_end
    flush()
    return chunks


def build_index(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Build an index JSON payload from records of the form
    {"path": str, "start": int, "end": int, "text": str}.

    Stores per-chunk text and pre-computed token length so search can
    rebuild the inverted index quickly on read.
    """
    truncated = False
    if len(records) > MAX_CHUNKS_PER_KB:
        records = records[:MAX_CHUNKS_PER_KB]
        truncated = True
    chunks: list[dict[str, Any]] = []
    total_len = 0
    for idx, record in enumerate(records):
        tokens = tokenize(record["text"])
        token_len = len(tokens) or 1
        total_len += token_len
        chunks.append({
            "id": f"c{idx}",
            "path": record["path"],
            "start": record["start"],
            "end": record["end"],
            "text": record["text"],
            "len": token_len,
        })
    avgdl = (total_len / len(chunks)) if chunks else 1.0
    return {
        "version": 1,
        "indexed_at": utc_now(),
        "stats": {"k1": K1, "b": B, "avgdl": avgdl, "N": len(chunks), "truncated": truncated},
        "chunks": chunks,
    }


class BM25Search:
    """Read-only BM25 scorer over an index JSON payload. Cheap enough
    to rebuild the inverted index per query (≈10-30 ms for 5k chunks)."""

    def __init__(self, index: dict[str, Any]):
        self.chunks: list[dict[str, Any]] = index.get("chunks", []) or []
        stats = index.get("stats", {}) or {}
        self.k1 = float(stats.get("k1", K1))
        self.b = float(stats.get("b", B))
        self.avgdl = float(stats.get("avgdl", 1.0)) or 1.0
        self.N = max(1, len(self.chunks))
        self.df: dict[str, int] = {}
        self.postings: dict[str, list[tuple[int, int]]] = {}
        for chunk_idx, chunk in enumerate(self.chunks):
            tokens = tokenize(chunk["text"])
            freq: dict[str, int] = {}
            for token in tokens:
                freq[token] = freq.get(token, 0) + 1
            for token, count in freq.items():
                self.df[token] = self.df.get(token, 0) + 1
                self.postings.setdefault(token, []).append((chunk_idx, count))

    def query(self, text: str, *, top_k: int = DEFAULT_TOP_K) -> list[dict[str, Any]]:
        if not self.chunks:
            return []
        q_tokens = tokenize(text)
        if not q_tokens:
            return []
        scores: dict[int, float] = {}
        matched_terms: dict[int, set[str]] = {}
        for q_token in set(q_tokens):
            postings = self.postings.get(q_token)
            if not postings:
                continue
            df = self.df.get(q_token, 0)
            if df <= 0:
                continue
            idf = math.log((self.N - df + 0.5) / (df + 0.5) + 1.0)
            for chunk_idx, count in postings:
                doc_len = self.chunks[chunk_idx]["len"]
                denom = count + self.k1 * (1.0 - self.b + self.b * doc_len / self.avgdl)
                contribution = idf * (count * (self.k1 + 1.0)) / denom
                scores[chunk_idx] = scores.get(chunk_idx, 0.0) + contribution
                matched_terms.setdefault(chunk_idx, set()).add(q_token)
        ranked = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))[:top_k]
        results: list[dict[str, Any]] = []
        for chunk_idx, score in ranked:
            chunk = self.chunks[chunk_idx]
            results.append({
                "chunk_id": chunk["id"],
                "path": chunk["path"],
                "start": chunk["start"],
                "end": chunk["end"],
                "text": chunk["text"],
                "score": round(score, 4),
                "matched_terms": sorted(matched_terms.get(chunk_idx, set())),
            })
        return results


def serialize_index(index: dict[str, Any]) -> str:
    return json.dumps(index, ensure_ascii=False)


def deserialize_index(text: str) -> dict[str, Any]:
    return json.loads(text)
