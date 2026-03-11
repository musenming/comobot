"""Memory search engine: hybrid BM25 + vector search over memory files."""

from __future__ import annotations

import math
import re
import sqlite3
import struct
import time
from datetime import date, datetime
from pathlib import Path
from typing import Any

from loguru import logger

from comobot.utils.helpers import ensure_dir

# Date pattern for daily log files
_DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")


class MemoryChunk:
    """A chunk of text from a memory file."""

    __slots__ = ("file_path", "start_line", "end_line", "content", "score")

    def __init__(
        self,
        file_path: str,
        start_line: int,
        end_line: int,
        content: str,
        score: float = 0.0,
    ):
        self.file_path = file_path
        self.start_line = start_line
        self.end_line = end_line
        self.content = content
        self.score = score

    def to_dict(self) -> dict[str, Any]:
        return {
            "file": self.file_path,
            "lines": f"{self.start_line}-{self.end_line}",
            "content": self.content[:700],
            "score": round(self.score, 4),
        }


class MemorySearchEngine:
    """Hybrid search engine for memory files using SQLite FTS5 + optional vector search."""

    def __init__(
        self,
        workspace: Path,
        *,
        chunk_target_tokens: int = 400,
        chunk_overlap_tokens: int = 80,
        vector_weight: float = 0.7,
        text_weight: float = 0.3,
        candidate_multiplier: int = 4,
        temporal_decay_enabled: bool = True,
        half_life_days: int = 30,
        mmr_enabled: bool = False,
        mmr_lambda: float = 0.7,
        embedding_fn=None,
    ):
        self.workspace = workspace
        self.memory_dir = ensure_dir(workspace / "memory")
        self.chunk_target_tokens = chunk_target_tokens
        self.chunk_overlap_tokens = chunk_overlap_tokens
        self.vector_weight = vector_weight
        self.text_weight = text_weight
        self.candidate_multiplier = candidate_multiplier
        self.temporal_decay_enabled = temporal_decay_enabled
        self.half_life_days = half_life_days
        self.mmr_enabled = mmr_enabled
        self.mmr_lambda = mmr_lambda
        self._embedding_fn = embedding_fn

        # SQLite index
        db_path = workspace / "memory" / ".memory_index.sqlite"
        self._db = sqlite3.connect(str(db_path))
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute("PRAGMA busy_timeout=5000")
        self._init_db()

    def _init_db(self) -> None:
        """Initialize database schema."""
        self._db.executescript("""
            CREATE TABLE IF NOT EXISTS chunks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_path TEXT NOT NULL,
                start_line INTEGER NOT NULL,
                end_line INTEGER NOT NULL,
                content TEXT NOT NULL,
                embedding BLOB,
                file_mtime REAL NOT NULL,
                updated_at REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_chunks_file ON chunks(file_path);
        """)
        # Create FTS5 virtual table if not exists
        try:
            self._db.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts
                USING fts5(content, content=chunks, content_rowid=id)
            """)
        except sqlite3.OperationalError:
            logger.warning("FTS5 not available, falling back to text-only search")
        self._db.commit()

    def close(self) -> None:
        """Close the database connection."""
        if self._db:
            self._db.close()

    # ── Indexing ──────────────────────────────────────────────────

    def reindex(self) -> int:
        """Reindex all memory files. Returns number of chunks indexed."""
        memory_files = self._discover_files()
        total = 0

        for file_path, abs_path in memory_files:
            mtime = abs_path.stat().st_mtime

            # Check if file changed
            row = self._db.execute(
                "SELECT MAX(file_mtime) FROM chunks WHERE file_path = ?", (file_path,)
            ).fetchone()
            if row[0] is not None and abs(row[0] - mtime) < 0.01:
                # Count existing chunks
                cnt = self._db.execute(
                    "SELECT COUNT(*) FROM chunks WHERE file_path = ?", (file_path,)
                ).fetchone()[0]
                total += cnt
                continue

            # Re-chunk this file
            self._db.execute("DELETE FROM chunks WHERE file_path = ?", (file_path,))
            try:
                self._db.execute(
                    "DELETE FROM chunks_fts WHERE rowid IN "
                    "(SELECT id FROM chunks WHERE file_path = ?)",
                    (file_path,),
                )
            except sqlite3.OperationalError:
                pass

            content = abs_path.read_text(encoding="utf-8")
            chunks = self._chunk_markdown(content, file_path)

            now = time.time()
            for chunk in chunks:
                embedding_blob = None
                if self._embedding_fn:
                    try:
                        vec = self._embedding_fn(chunk.content)
                        if vec:
                            embedding_blob = _pack_vector(vec)
                    except Exception:
                        logger.debug("Embedding failed for chunk in {}", file_path)

                cur = self._db.execute(
                    "INSERT INTO chunks (file_path, start_line, end_line, content, embedding, file_mtime, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (file_path, chunk.start_line, chunk.end_line, chunk.content, embedding_blob, mtime, now),
                )
                # Insert into FTS
                try:
                    self._db.execute(
                        "INSERT INTO chunks_fts(rowid, content) VALUES (?, ?)",
                        (cur.lastrowid, chunk.content),
                    )
                except sqlite3.OperationalError:
                    pass

            total += len(chunks)

        self._db.commit()
        logger.info("Memory index: {} chunks across {} files", total, len(memory_files))
        return total

    def _discover_files(self) -> list[tuple[str, Path]]:
        """Discover all memory markdown files."""
        files = []

        # MEMORY.md at workspace root
        mem_file = self.workspace / "MEMORY.md"
        if mem_file.exists():
            files.append(("MEMORY.md", mem_file))

        # Also check memory/MEMORY.md
        mem_file2 = self.memory_dir / "MEMORY.md"
        if mem_file2.exists() and mem_file2 != mem_file:
            files.append(("memory/MEMORY.md", mem_file2))

        # All .md files in memory/
        for p in sorted(self.memory_dir.glob("*.md")):
            if p.name == "MEMORY.md":
                continue
            if p.name.startswith("."):
                continue
            rel = f"memory/{p.name}"
            files.append((rel, p))

        return files

    def _chunk_markdown(self, text: str, file_path: str) -> list[MemoryChunk]:
        """Split markdown into overlapping chunks by paragraphs/sections."""
        lines = text.split("\n")
        chunks: list[MemoryChunk] = []

        # Split on blank lines or headings to get logical sections
        sections: list[tuple[int, int, str]] = []
        section_start = 0
        section_lines: list[str] = []

        for i, line in enumerate(lines):
            if line.strip() == "" and section_lines:
                content = "\n".join(section_lines).strip()
                if content:
                    sections.append((section_start + 1, i, content))
                section_lines = []
                section_start = i + 1
            elif line.startswith("#") and section_lines:
                content = "\n".join(section_lines).strip()
                if content:
                    sections.append((section_start + 1, i, content))
                section_lines = [line]
                section_start = i
            else:
                section_lines.append(line)

        if section_lines:
            content = "\n".join(section_lines).strip()
            if content:
                sections.append((section_start + 1, len(lines), content))

        # Merge small sections, split large ones
        target_chars = self.chunk_target_tokens * 4  # ~4 chars/token
        overlap_chars = self.chunk_overlap_tokens * 4

        buffer_content = ""
        buffer_start = 0
        buffer_end = 0

        for start, end, content in sections:
            if not buffer_content:
                buffer_content = content
                buffer_start = start
                buffer_end = end
            elif len(buffer_content) + len(content) < target_chars:
                buffer_content += "\n\n" + content
                buffer_end = end
            else:
                chunks.append(MemoryChunk(file_path, buffer_start, buffer_end, buffer_content))
                # Overlap: keep tail of previous chunk
                if overlap_chars > 0 and len(buffer_content) > overlap_chars:
                    overlap_text = buffer_content[-overlap_chars:]
                    buffer_content = overlap_text + "\n\n" + content
                else:
                    buffer_content = content
                buffer_start = start
                buffer_end = end

        if buffer_content.strip():
            chunks.append(MemoryChunk(file_path, buffer_start, buffer_end, buffer_content))

        return chunks

    # ── Search ────────────────────────────────────────────────────

    def search(self, query: str, max_results: int = 5) -> list[MemoryChunk]:
        """Hybrid search: BM25 + optional vector similarity."""
        n_candidates = max_results * self.candidate_multiplier

        # BM25 search via FTS5
        bm25_results = self._bm25_search(query, n_candidates)

        # Vector search
        vector_results = self._vector_search(query, n_candidates) if self._embedding_fn else []

        # Merge results
        merged = self._merge_results(bm25_results, vector_results)

        # Apply temporal decay
        if self.temporal_decay_enabled:
            merged = self._apply_temporal_decay(merged)

        # Sort by score descending
        merged.sort(key=lambda c: c.score, reverse=True)

        # MMR re-ranking
        if self.mmr_enabled and len(merged) > max_results:
            merged = self._mmr_rerank(merged, max_results)

        return merged[:max_results]

    def _bm25_search(self, query: str, limit: int) -> list[tuple[int, float]]:
        """BM25 search via FTS5. Returns [(chunk_id, bm25_rank)]."""
        try:
            rows = self._db.execute(
                "SELECT rowid, rank FROM chunks_fts WHERE chunks_fts MATCH ? ORDER BY rank LIMIT ?",
                (self._fts_escape(query), limit),
            ).fetchall()
            return [(r[0], r[1]) for r in rows]
        except sqlite3.OperationalError:
            # FTS5 not available, fallback to LIKE search
            return self._like_search(query, limit)

    def _like_search(self, query: str, limit: int) -> list[tuple[int, float]]:
        """Fallback text search using LIKE."""
        terms = query.lower().split()
        if not terms:
            return []
        conditions = " AND ".join(["LOWER(content) LIKE ?"] * len(terms))
        params = [f"%{t}%" for t in terms]
        rows = self._db.execute(
            f"SELECT id, 0.0 FROM chunks WHERE {conditions} LIMIT ?",
            (*params, limit),
        ).fetchall()
        # Assign pseudo-scores based on match count
        results = []
        for chunk_id, _ in rows:
            content = self._db.execute(
                "SELECT content FROM chunks WHERE id = ?", (chunk_id,)
            ).fetchone()
            if content:
                lower = content[0].lower()
                match_count = sum(1 for t in terms if t in lower)
                results.append((chunk_id, -match_count))  # Negative = better (like BM25 rank)
        return results

    def _vector_search(self, query: str, limit: int) -> list[tuple[int, float]]:
        """Vector similarity search. Returns [(chunk_id, cosine_similarity)]."""
        if not self._embedding_fn:
            return []
        try:
            query_vec = self._embedding_fn(query)
            if not query_vec:
                return []
        except Exception:
            logger.debug("Failed to embed query")
            return []

        # Load all embeddings (for small memory corpora this is fine)
        rows = self._db.execute(
            "SELECT id, embedding FROM chunks WHERE embedding IS NOT NULL"
        ).fetchall()

        results = []
        for chunk_id, blob in rows:
            if blob:
                vec = _unpack_vector(blob)
                sim = _cosine_similarity(query_vec, vec)
                results.append((chunk_id, sim))

        results.sort(key=lambda x: x[1], reverse=True)
        return results[:limit]

    def _merge_results(
        self,
        bm25_results: list[tuple[int, float]],
        vector_results: list[tuple[int, float]],
    ) -> list[MemoryChunk]:
        """Merge BM25 and vector results with weighted scoring."""
        scores: dict[int, dict[str, float]] = {}

        # BM25 scores: convert rank to 0..1 score
        for chunk_id, rank in bm25_results:
            text_score = 1.0 / (1.0 + max(0.0, -rank if rank < 0 else rank))
            scores.setdefault(chunk_id, {"text": 0, "vector": 0})["text"] = text_score

        # Vector scores (already 0..1 cosine similarity)
        for chunk_id, sim in vector_results:
            scores.setdefault(chunk_id, {"text": 0, "vector": 0})["vector"] = max(0, sim)

        # Compute final weighted score
        total_weight = self.vector_weight + self.text_weight
        vw = self.vector_weight / total_weight if total_weight > 0 else 0.5
        tw = self.text_weight / total_weight if total_weight > 0 else 0.5

        chunks = []
        for chunk_id, s in scores.items():
            final = vw * s["vector"] + tw * s["text"]
            row = self._db.execute(
                "SELECT file_path, start_line, end_line, content FROM chunks WHERE id = ?",
                (chunk_id,),
            ).fetchone()
            if row:
                chunks.append(MemoryChunk(row[0], row[1], row[2], row[3], final))

        return chunks

    def _apply_temporal_decay(self, chunks: list[MemoryChunk]) -> list[MemoryChunk]:
        """Apply exponential decay based on file age."""
        if self.half_life_days <= 0:
            return chunks

        lambda_val = math.log(2) / self.half_life_days
        today = date.today()

        for chunk in chunks:
            # Evergreen files don't decay
            if self._is_evergreen(chunk.file_path):
                continue

            file_date = self._extract_date(chunk.file_path)
            if file_date:
                age_days = (today - file_date).days
            else:
                # Fallback to file mtime
                abs_path = self.workspace / chunk.file_path
                if abs_path.exists():
                    mtime = abs_path.stat().st_mtime
                    age_days = (time.time() - mtime) / 86400
                else:
                    age_days = 0

            if age_days > 0:
                decay = math.exp(-lambda_val * age_days)
                chunk.score *= decay

        return chunks

    def _mmr_rerank(self, chunks: list[MemoryChunk], k: int) -> list[MemoryChunk]:
        """MMR re-ranking for diversity."""
        if not chunks:
            return chunks

        selected: list[MemoryChunk] = []
        remaining = list(chunks)
        lam = self.mmr_lambda

        # Always select the top result first
        selected.append(remaining.pop(0))

        while len(selected) < k and remaining:
            best_idx = 0
            best_mmr = float("-inf")

            for i, candidate in enumerate(remaining):
                max_sim = max(
                    _jaccard_similarity(candidate.content, s.content) for s in selected
                )
                mmr_score = lam * candidate.score - (1 - lam) * max_sim
                if mmr_score > best_mmr:
                    best_mmr = mmr_score
                    best_idx = i

            selected.append(remaining.pop(best_idx))

        return selected

    @staticmethod
    def _is_evergreen(file_path: str) -> bool:
        """Check if a file is evergreen (not a dated daily log)."""
        name = Path(file_path).stem
        return not bool(_DATE_RE.fullmatch(name))

    @staticmethod
    def _extract_date(file_path: str) -> date | None:
        """Extract date from filename like 2026-03-11.md."""
        match = _DATE_RE.search(Path(file_path).stem)
        if match:
            try:
                return datetime.strptime(match.group(1), "%Y-%m-%d").date()
            except ValueError:
                pass
        return None

    @staticmethod
    def _fts_escape(query: str) -> str:
        """Escape FTS5 special characters, converting to simple term query."""
        # Remove FTS5 operators and wrap each term in quotes
        terms = re.findall(r"\w+", query)
        return " OR ".join(f'"{t}"' for t in terms) if terms else query


# ── Vector utilities ──────────────────────────────────────────────


def _pack_vector(vec: list[float]) -> bytes:
    """Pack a float vector into bytes."""
    return struct.pack(f"{len(vec)}f", *vec)


def _unpack_vector(blob: bytes) -> list[float]:
    """Unpack bytes into a float vector."""
    n = len(blob) // 4
    return list(struct.unpack(f"{n}f", blob))


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    if len(a) != len(b) or not a:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _jaccard_similarity(a: str, b: str) -> float:
    """Compute Jaccard similarity between two text strings."""
    tokens_a = set(a.lower().split())
    tokens_b = set(b.lower().split())
    if not tokens_a or not tokens_b:
        return 0.0
    intersection = tokens_a & tokens_b
    union = tokens_a | tokens_b
    return len(intersection) / len(union)
