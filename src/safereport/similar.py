"""Past injuries like this one: nearest narratives by meaning, over all 105,996 reports.

The narratives are embedded once with the same model as the rules and kept in a FAISS index on
disk. Without the model or the index, the search falls back to reports with the same estimated
OIICS 3 event group in the same industry, so the Analyst always has an answer and says which.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from safereport.data import ReportStore
from safereport.retrieval import INDEX_DIR, Encoder, dense_ready, flat_index


NARRATIVE_INDEX = INDEX_DIR / "narratives.faiss"
NARRATIVE_IDS = INDEX_DIR / "narratives_ids.parquet"


@dataclass
class Similar:
    report_id: str
    event_date: str
    state: str
    narrative: str
    score: float


def build_narrative_index(store: ReportStore, encoder: Encoder, folder: Path = INDEX_DIR) -> int:
    import faiss  # optional extra, loaded only for dense retrieval

    rows = store.frame("SELECT id, narrative FROM reports ORDER BY id")
    vectors = encoder.documents(rows["narrative"].tolist()).astype(np.float32)
    faiss.write_index(flat_index(vectors), str(folder / NARRATIVE_INDEX.name))
    rows[["id"]].to_parquet(folder / NARRATIVE_IDS.name, index=False)
    return len(rows)


class SimilarReports:
    def __init__(self, store: ReportStore, folder: Path = INDEX_DIR, dense: bool = True) -> None:
        self.store = store
        self.index = None
        self.ids: list[str] = []
        self.encoder: Encoder | None = None
        index_path = folder / NARRATIVE_INDEX.name
        if dense and dense_ready() and index_path.exists():
            import faiss  # optional extra, loaded only for dense retrieval

            self.index = faiss.read_index(str(index_path))
            self.ids = pd.read_parquet(folder / NARRATIVE_IDS.name)["id"].tolist()
            self.encoder = Encoder()

    @property
    def method(self) -> str:
        return "narrative embeddings" if self.index is not None else "same event group and industry"

    def find(
        self, narrative: str, naics: str = "", event_group: str = "", k: int = 3, exclude: str = ""
    ) -> list[Similar]:
        if self.index is not None and self.encoder is not None:
            vector = self.encoder.query(narrative).astype(np.float32)[None, :]
            scores, found = self.index.search(vector, k + 5)
            picked = [(self.ids[i], float(s)) for i, s in zip(found[0], scores[0], strict=True) if i >= 0]
            picked = [(i, s) for i, s in picked if i != exclude][:k]
            if not picked:
                return []
            rows = self.store.frame(
                "SELECT id, event_date, state, narrative FROM reports WHERE list_contains(?, id)",
                [[i for i, _ in picked]],
            ).set_index("id")
            return [
                Similar(
                    i, str(rows.loc[i, "event_date"])[:10], rows.loc[i, "state"], rows.loc[i, "narrative"], s
                )
                for i, s in picked
                if i in rows.index
            ]
        if not event_group:
            return []
        rows = self.store.frame(
            "SELECT id, event_date, state, narrative FROM reports WHERE starts_with(event_code_v3, ?) "
            "AND starts_with(naics, ?) AND id <> ? ORDER BY event_date DESC LIMIT ?",
            [event_group, naics[:3], exclude, k],
        )
        return [Similar(r.id, str(r.event_date)[:10], r.state, r.narrative, 0.0) for r in rows.itertuples()]
