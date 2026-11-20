"""Hybrid retrieval over the rules: BM25 for exact words, embeddings for meaning.

Narratives say "hand caught in the rollers while cleaning"; the standard says "servicing and
maintenance" and "unexpected energization". BM25 alone misses that kind of match and
embeddings alone blur section numbers, so both rank the paragraphs and reciprocal rank fusion
combines them. The index registry keeps one index per source (Part 1910, Part 1926 when built,
the General Duty Clause, emphasis programs) and picks the part from the report's NAICS code.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import re
import tomllib
from typing import Literal

import numpy as np
import pandas as pd
from rank_bm25 import BM25Okapi

from safereport.config import PROJECT_ROOT
from safereport.ecfr import ECFR_DATE, ECFR_DIR, parse_part


# torch and faiss each bring their own OpenMP runtime on macOS; with more than one thread the
# two crash the process, so dense retrieval runs single threaded unless the user says otherwise.
os.environ.setdefault("OMP_NUM_THREADS", "1")

INDEX_DIR = PROJECT_ROOT / "indexes"
REFERENCE_DIR = PROJECT_ROOT / "data" / "reference"
EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"
# bge models expect this instruction in front of a search query, not in front of documents.
QUERY_INSTRUCTION = "Represent this sentence for searching relevant passages: "
RRF_K = 60
CANDIDATES = 100

Source = Literal["1910", "1926", "general_duty", "emphasis_program"]

STOP_WORDS = {
    "a", "an", "the", "and", "or", "of", "to", "in", "on", "at", "by", "for", "with", "from", "as",
    "is", "was", "were", "be", "been", "being", "this", "that", "these", "those", "it", "its", "his",
    "her", "their", "he", "she", "they", "who", "which", "what", "when", "while", "into", "onto",
    "over", "under", "than", "then", "there", "shall", "must", "may", "such", "any", "all", "each",
    "other", "not", "no", "if", "per", "one", "two", "three", "employee", "employees", "employer",
    "employers", "section", "paragraph", "accordance", "required", "requirements",
}  # fmt: skip


def tokenize(text: str) -> list[str]:
    """Lower case word stems without stop words; "guarding" and "guards" both become "guard"."""
    tokens = []
    for word in re.findall(r"[a-z0-9]+", text.lower()):
        if word in STOP_WORDS or len(word) < 2:
            continue
        for suffix in ("ing", "ed", "es", "s"):
            if len(word) > len(suffix) + 3 and word.endswith(suffix):
                word = word[: -len(suffix)]
                break
        tokens.append(word)
    return tokens


# A thing that fell is not a worker who fell ("a section of dirt/rock fell from the tunnel wall").
# Only a thing named as the subject counts: an article or "section of" right before it. A worker
# handling it ("installing solar panels fell from the roof", "connecting structural steel fell")
# still falls.
FALLING_THING = re.compile(
    r"\b(a|an|the|of|some|its|their)\W+((section|piece|pile|stack|load|bundle|sheet|portion|part)\W+of\W+)?"
    r"(\w+/)?(dirt|rocks?|soil|earth|walls?|beams?|loads?|pipes?|objects?|materials?|box(es)?|pallets?|boards?|"
    r"planks?|debris|bundles?|blocks?|bricks?|tools?|parts?|sheets?|panels?|trees?|branch(es)?|steel|"
    r"concrete|truss(es)?|joists?|rebar|coils?|rolls?|stacks?)\W+((had|has|was|suddenly|then)\W+)?$",
    re.IGNORECASE,
)


def _triggered(pattern: str, text: str) -> bool:
    for found in re.finditer(pattern, text, flags=re.IGNORECASE):
        if not FALLING_THING.search(text[max(0, found.start() - 60) : found.start()]):
            return True
    return False


@dataclass
class Document:
    doc_id: str
    source: Source
    citation: str
    section: str
    title: str
    text: str
    context: str = ""
    url: str = ""
    industries: list[str] = field(default_factory=list)
    triggers: list[str] = field(default_factory=list)
    exact_citation: bool = True
    # Emphasis programs only: triggers that apply in any industry, and whether the scope was read
    # from the directive itself (only a verified program can force an inspection).
    anywhere_triggers: list[str] = field(default_factory=list)
    verified: bool = True

    def applies_to(self, text: str, naics: str) -> bool:
        """For an emphasis program: a trigger that applies anywhere matches, or the report's
        industry is covered and one of the industry triggers matches (or there are none)."""
        if any(_triggered(pattern, text) for pattern in self.anywhere_triggers):
            return True
        if self.industries and not any(naics.startswith(i) for i in self.industries):
            return False
        if not self.triggers:
            return bool(self.industries)
        return any(_triggered(pattern, text) for pattern in self.triggers)

    @property
    def search_text(self) -> str:
        return f"{self.title}. {self.context[:240]} {self.text}".strip()


@dataclass
class Hit:
    document: Document
    score: float
    bm25_rank: int | None
    dense_rank: int | None


@dataclass
class SectionHit:
    section: str
    score: float
    best: Hit


@dataclass
class RetrievalResult:
    part: Source
    sections: list[SectionHit]
    emphasis: list[Hit]
    note: str = ""

    @property
    def margin(self) -> float:
        """How far the top section leads the second, as a share of the top score."""
        if len(self.sections) < 2 or self.sections[0].score <= 0:
            return 1.0
        return (self.sections[0].score - self.sections[1].score) / self.sections[0].score


class EmbeddingsUnavailableError(RuntimeError):
    """The embedding model is not on this machine, or its package is not installed."""


def dense_ready(model_name: str = EMBEDDING_MODEL) -> bool:
    """True when the embeddings extra is installed and the model is in the local cache.

    It reads the cache only, so it is cheap and never waits on the network.
    """
    try:
        from huggingface_hub import try_to_load_from_cache
        import sentence_transformers  # noqa: F401
    except ImportError:
        return False
    return isinstance(try_to_load_from_cache(model_name, "modules.json"), str)


class Encoder:
    """Sentence embeddings, loaded only when dense retrieval is used.

    Loading never touches the network unless `allow_download` is set, which only
    `safereport build-index` does. Without a cached model, a search or a test would otherwise
    wait minutes on the Hugging Face hub when the machine is offline.
    """

    def __init__(self, model_name: str = EMBEDDING_MODEL, allow_download: bool = False) -> None:
        try:
            # sentence-transformers pulls in torch, an optional extra, so it loads only here.
            from sentence_transformers import SentenceTransformer
        except ImportError as error:
            raise EmbeddingsUnavailableError(
                "install the embeddings extra: pip install -e '.[embeddings]'"
            ) from error

        self.model_name = model_name
        try:
            self.model = SentenceTransformer(model_name, local_files_only=True)
        except OSError as error:
            if not allow_download:
                raise EmbeddingsUnavailableError(
                    f"{model_name} is not cached on this machine; run `safereport build-index` once online"
                ) from error
            self.model = SentenceTransformer(model_name)

    def documents(self, texts: Sequence[str]) -> np.ndarray:
        return self.model.encode(
            list(texts), batch_size=64, normalize_embeddings=True, show_progress_bar=False
        )

    def query(self, text: str) -> np.ndarray:
        return self.model.encode([QUERY_INSTRUCTION + text], normalize_embeddings=True)[0]


class Retriever:
    """BM25 plus an optional FAISS index over one source's documents."""

    def __init__(self, documents: list[Document], dense_index=None, encoder: Encoder | None = None):
        self.documents = documents
        self.bm25 = BM25Okapi([tokenize(d.search_text) for d in documents])
        self.encoder = encoder
        self.faiss = dense_index if encoder is not None else None

    def _bm25_ranks(self, query: str) -> list[int]:
        scores = self.bm25.get_scores(tokenize(query))
        order = np.argsort(-scores, kind="stable")[:CANDIDATES]
        return [int(i) for i in order if scores[i] > 0]

    def _dense_ranks(self, query: str) -> list[int]:
        if self.faiss is None or self.encoder is None:
            return []
        vector = self.encoder.query(query).astype(np.float32)[None, :]
        _, found = self.faiss.search(vector, min(CANDIDATES, len(self.documents)))
        return [int(i) for i in found[0] if i >= 0]

    def search(self, query: str, k: int = 10) -> list[Hit]:
        bm25 = self._bm25_ranks(query)
        dense = self._dense_ranks(query)
        fused: dict[int, float] = {}
        for ranks in (bm25, dense):
            for rank, index in enumerate(ranks, start=1):
                fused[index] = fused.get(index, 0.0) + 1.0 / (RRF_K + rank)
        bm25_at = {index: rank for rank, index in enumerate(bm25, start=1)}
        dense_at = {index: rank for rank, index in enumerate(dense, start=1)}
        best = sorted(fused, key=lambda i: (-fused[i], i))[:k]
        return [Hit(self.documents[i], fused[i], bm25_at.get(i), dense_at.get(i)) for i in best]


class SectionIndex:
    """One profile per section: its title and the short headings of its paragraphs.

    A narrative rarely shares words with one paragraph, but it often shares them with what a
    whole section is about ("Powered industrial trucks", "Ladders", "Energy control program").
    """

    def __init__(self, documents: list[Document], encoder: Encoder | None = None) -> None:
        titles: dict[str, str] = {}
        headings: dict[str, list[str]] = {}
        for document in documents:
            titles.setdefault(document.section, document.title)
            heading = re.match(r"^\(\w+\)\s*([^.—]{3,80})[.—]", document.text)
            if heading:
                headings.setdefault(document.section, []).append(heading.group(1))
        self.sections = sorted(titles)
        self.titles = titles
        profiles = [
            f"{titles[s]}. " + "; ".join(dict.fromkeys(headings.get(s, [])))[:1500] for s in self.sections
        ]
        self.bm25 = BM25Okapi([tokenize(p) for p in profiles])
        self.encoder = encoder
        self.vectors = encoder.documents(profiles) if encoder is not None else None

    def rankings(self, query: str, depth: int = 50) -> list[list[str]]:
        scores = self.bm25.get_scores(tokenize(query))
        rankings = [[self.sections[i] for i in np.argsort(-scores, kind="stable")[:depth] if scores[i] > 0]]
        if self.vectors is not None and self.encoder is not None:
            similarity = self.vectors @ self.encoder.query(query)
            rankings.append([self.sections[i] for i in np.argsort(-similarity, kind="stable")[:depth]])
        return rankings


def fuse(rankings: list[list[str]]) -> dict[str, float]:
    """Reciprocal rank fusion with equal weights: no weight is tuned on the answer key."""
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, item in enumerate(ranking, start=1):
            scores[item] = scores.get(item, 0.0) + 1.0 / (RRF_K + rank)
    return scores


def rank_sections(hits: list[Hit], k: int = 5) -> list[SectionHit]:
    """One entry per CFR section, scored by its best paragraph."""
    sections: dict[str, SectionHit] = {}
    for hit in hits:
        known = sections.get(hit.document.section)
        if known is None or hit.score > known.score:
            sections[hit.document.section] = SectionHit(hit.document.section, hit.score, hit)
    return sorted(sections.values(), key=lambda s: -s.score)[:k]


def ecfr_documents(part: Literal["1910", "1926"], xml_path: Path | None = None) -> list[Document]:
    xml_path = xml_path or ECFR_DIR / f"title-29-part-{part}.xml"
    documents = []
    for number, paragraph in enumerate(parse_part(xml_path)):
        documents.append(
            Document(
                doc_id=f"{part}-{number:05d}",
                source=part,
                citation=paragraph.citation,
                section=paragraph.section,
                title=paragraph.section_title,
                text=paragraph.text,
                context=paragraph.parent_text,
                url=paragraph.url,
                exact_citation=paragraph.exact,
            )
        )
    return documents


def reference_documents(source: Literal["general_duty", "emphasis_program"]) -> list[Document]:
    name = "general_duty.toml" if source == "general_duty" else "emphasis_programs.toml"
    with (REFERENCE_DIR / name).open("rb") as handle:
        entries = tomllib.load(handle)["documents"]
    return [
        Document(
            doc_id=f"{source}-{number:02d}",
            source=source,
            citation=entry["citation"],
            section=entry["citation"],
            title=entry["title"],
            text=entry["text"],
            url=entry.get("url", ""),
            industries=entry.get("industries", []),
            triggers=entry.get("triggers", []),
            anywhere_triggers=entry.get("anywhere_triggers", []),
            verified=entry.get("verified", True),
        )
        for number, entry in enumerate(entries)
    ]


def flat_index(vectors: np.ndarray):
    """A FAISS inner product index; with normalized vectors that is cosine similarity."""
    import faiss  # optional extra, loaded only for dense retrieval

    index = faiss.IndexFlatIP(vectors.shape[1])
    index.add(np.ascontiguousarray(vectors, dtype=np.float32))
    return index


def build_indexes(index_dir: Path = INDEX_DIR, dense: bool = True, parts: Sequence[str] = ("1910",)) -> dict:
    """Write each source's documents (and embeddings, when dense) to disk, with a manifest."""
    index_dir.mkdir(parents=True, exist_ok=True)
    sources: dict[str, list[Document]] = {part: ecfr_documents(part) for part in parts}
    sources["general_duty"] = reference_documents("general_duty")
    sources["emphasis_program"] = reference_documents("emphasis_program")
    encoder = Encoder(allow_download=True) if dense else None
    counts = {}
    for source, documents in sources.items():
        pd.DataFrame([asdict(d) for d in documents]).to_parquet(
            index_dir / f"{source}_docs.parquet", index=False
        )
        if encoder is not None:
            import faiss  # optional extra, loaded only for dense retrieval

            vectors = encoder.documents([d.search_text for d in documents]).astype(np.float32)
            faiss.write_index(flat_index(vectors), str(index_dir / f"{source}.faiss"))
        counts[source] = len(documents)
    manifest = {
        "built_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "ecfr_date": ECFR_DATE,
        "embedding_model": EMBEDDING_MODEL if dense else None,
        "documents": counts,
    }
    (index_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))
    return manifest


class IndexRegistry:
    """The retrievers by source, and the rule for which part covers which industry."""

    def __init__(self, retrievers: dict[str, Retriever]) -> None:
        self.retrievers = retrievers
        self.section_indexes = {
            part: SectionIndex(r.documents, r.encoder if r.faiss is not None else None)
            for part, r in retrievers.items()
            if part in ("1910", "1926")
        }

    @classmethod
    def load(cls, index_dir: Path = INDEX_DIR, dense: bool = True) -> IndexRegistry:
        manifest = json.loads((index_dir / "manifest.json").read_text())
        model = manifest.get("embedding_model")
        encoder = Encoder(model) if dense and model else None
        retrievers = {}
        for source in manifest["documents"]:
            frame = pd.read_parquet(index_dir / f"{source}_docs.parquet")
            documents = [
                Document(
                    **{
                        **row,
                        "industries": list(row["industries"]),
                        "triggers": list(row.get("triggers", [])),
                        "anywhere_triggers": list(row.get("anywhere_triggers", [])),
                    }
                )
                for row in frame.to_dict("records")
            ]
            faiss_path = index_dir / f"{source}.faiss"
            dense_index = None
            if encoder is not None and faiss_path.exists():
                import faiss  # optional extra, loaded only for dense retrieval

                dense_index = faiss.read_index(str(faiss_path))
            retrievers[source] = Retriever(documents, dense_index, encoder)
        return cls(retrievers)

    @property
    def sources(self) -> list[str]:
        return sorted(self.retrievers)

    def part_for(self, naics: str) -> tuple[Source, str]:
        """Part 1926 for construction (NAICS 23), Part 1910 otherwise, with a note on any fallback."""
        if naics.startswith("23"):
            if "1926" in self.retrievers:
                return "1926", ""
            return "1910", "construction report, but the Part 1926 index is not built; searched Part 1910"
        return "1910", ""

    def search(self, query: str, naics: str = "", k: int = 5, terms: Sequence[str] = ()) -> RetrievalResult:
        """Rank sections for a narrative.

        `terms` are words in the language of the rules that another step adds to the query, for
        example "powered industrial truck" for a forklift. The Standards agent fills them from a
        model in Phase 2; without them the search runs on the narrative alone.
        """
        query = " ".join([query, *terms]).strip()
        part, note = self.part_for(naics)
        retriever = self.retrievers[part]
        paragraph_sections = rank_sections(retriever.search(query, k=60), k=50)
        best = {s.section: s.best for s in paragraph_sections}
        fused = fuse([*self.section_indexes[part].rankings(query), [s.section for s in paragraph_sections]])
        # A definitions section says what words mean, not what an employer must do, so it is
        # never the standard a case points to (1910.211 matched many machine narratives).
        titles = self.section_indexes[part].titles
        fused = {s: v for s, v in fused.items() if not titles.get(s, "").lower().startswith("definitions")}
        top = sorted(fused, key=lambda section: (-fused[section], section))[:k]
        missing = [section for section in top if section not in best]
        if missing:
            scores = retriever.bm25.get_scores(tokenize(query))
            for section in missing:
                rows = [i for i, d in enumerate(retriever.documents) if d.section == section]
                i = max(rows, key=lambda row: scores[row])
                best[section] = Hit(retriever.documents[i], float(scores[i]), None, None)
        sections = [SectionHit(section, fused[section], best[section]) for section in top]
        emphasis = []
        if "emphasis_program" in self.retrievers:
            # An emphasis program can force an inspection (Category 1), so it applies only by
            # rule: the industry is covered and one of the program's triggers matches. Ranking by
            # similarity flagged 224 of 300 holdout reports, a slip on a doormat as a fall.
            emphasis = [
                Hit(document, 1.0, None, None)
                for document in self.retrievers["emphasis_program"].documents
                if document.applies_to(query, naics)
            ]
        return RetrievalResult(part, sections, emphasis, note)

    def general_duty(self) -> Document:
        return self.retrievers["general_duty"].documents[0]
