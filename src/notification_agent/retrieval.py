"""
Semantic retrieval layer for the Customer Notification Assurance Agent.

Checkpoint 3.1 — hybrid RAG design.

This module implements the retrieval half of the agent: it indexes anonymized
runbook / SOP / glossary chunks and returns the most relevant ones for a given
exception query. It intentionally uses ZERO third-party dependencies so it runs
anywhere; the embedding is a lightweight TF cosine-similarity stand-in for a real
text-embedding model. The interface (embed -> store -> query top-k with a score)
mirrors what a production vector store (FAISS, pgvector, a managed store) exposes,
so the model could be swapped in without changing the agent logic.

Design choices demonstrated here (mapping to the 3.1 write-up):
  - Data source selection: only anonymized runbooks/SOPs/glossary are indexed.
  - Chunking: documents split by section heading (procedure-level chunks).
  - Metadata filtering: chunks tagged by notification_type; queries pre-filter.
  - top-k: default 3.
  - Failure-mode mitigation: a similarity threshold below which the KB is treated
    as "silent" so the agent defers to human review instead of forcing a match.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from pathlib import Path


# ---- Tunable retrieval design parameters (see 3.1 write-up) -----------------

TOP_K = 3               # how many chunks to retrieve
SIMILARITY_THRESHOLD = 0.08   # below this, treat KB as silent -> human review

_TOKEN_RE = re.compile(r"[a-z0-9_]+")
_STOPWORDS = {
    "the", "a", "an", "is", "are", "of", "to", "and", "or", "for", "on", "in",
    "as", "be", "it", "this", "that", "with", "by", "at", "from", "not", "no",
}


def _tokenize(text: str) -> list[str]:
    return [t for t in _TOKEN_RE.findall(text.lower()) if t not in _STOPWORDS]


def _term_freq(tokens: list[str]) -> dict[str, float]:
    tf: dict[str, float] = {}
    for tok in tokens:
        tf[tok] = tf.get(tok, 0.0) + 1.0
    return tf


def _cosine(a: dict[str, float], b: dict[str, float]) -> float:
    if not a or not b:
        return 0.0
    common = set(a) & set(b)
    dot = sum(a[t] * b[t] for t in common)
    na = math.sqrt(sum(v * v for v in a.values()))
    nb = math.sqrt(sum(v * v for v in b.values()))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


@dataclass
class Chunk:
    text: str
    notification_type: str          # metadata used for pre-filtering
    reason_code: str | None
    source: str
    _vec: dict[str, float] = field(default_factory=dict, repr=False)


@dataclass
class RetrievalResult:
    chunk: Chunk
    score: float


class KnowledgeBase:
    """A minimal in-memory vector store over runbook / SOP / glossary chunks."""

    def __init__(self) -> None:
        self.chunks: list[Chunk] = []

    # --- ingestion ---------------------------------------------------------

    def add_chunk(self, text: str, notification_type: str,
                  reason_code: str | None, source: str) -> None:
        chunk = Chunk(
            text=text.strip(),
            notification_type=notification_type,
            reason_code=reason_code,
            source=source,
            _vec=_term_freq(_tokenize(text)),
        )
        self.chunks.append(chunk)

    def load_directory(self, kb_dir: Path) -> None:
        """Ingest every markdown file, chunking by section heading (##)."""
        for md_file in sorted(kb_dir.glob("*.md")):
            self._ingest_file(md_file)

    def _ingest_file(self, md_file: Path) -> None:
        raw = md_file.read_text()
        # Split into procedure-level chunks on "## " headings.
        sections = re.split(r"\n(?=## )", raw)
        for section in sections:
            section = section.strip()
            if not section or section.startswith("# "):
                # skip the top-level title block
                if not section.startswith("## "):
                    continue
            notif = _extract_field(section, "notification_type") or "ANY"
            reason = _extract_field(section, "reason_code")
            self.add_chunk(
                text=section,
                notification_type=notif.upper(),
                reason_code=reason,
                source=md_file.name,
            )

    # --- query -------------------------------------------------------------

    def query(self, text: str, notification_type: str | None = None,
              top_k: int = TOP_K) -> list[RetrievalResult]:
        """Semantic search with optional metadata pre-filter by notification type."""
        qvec = _term_freq(_tokenize(text))
        candidates = self.chunks
        if notification_type:
            nt = notification_type.upper()
            candidates = [c for c in candidates
                          if c.notification_type in (nt, "ANY")]
        scored = [RetrievalResult(c, _cosine(qvec, c._vec)) for c in candidates]
        scored.sort(key=lambda r: r.score, reverse=True)
        return scored[:top_k]


def _extract_field(text: str, field_name: str) -> str | None:
    m = re.search(rf"{field_name}:\s*([A-Za-z0-9_]+)", text)
    return m.group(1) if m else None


def build_default_kb() -> KnowledgeBase:
    # knowledge_base/ lives at the repo root (one level above src/).
    kb = KnowledgeBase()
    kb.load_directory(Path(__file__).resolve().parents[2] / "data" / "knowledge_base")
    return kb
