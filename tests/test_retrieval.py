from __future__ import annotations

import pytest

from safereport.evaluation import score_retrieval
from safereport.labels import load_answer_key
from safereport.retrieval import (
    INDEX_DIR,
    Document,
    EmbeddingsUnavailableError,
    IndexRegistry,
    Retriever,
    dense_ready,
    fuse,
    reference_documents,
    tokenize,
)


def doc(doc_id: str, source: str, section: str, title: str, text: str, industries=()) -> Document:
    return Document(doc_id, source, section, section, title, text, industries=list(industries))


@pytest.fixture
def registry() -> IndexRegistry:
    part = [
        doc("1", "1910", "1910.178", "Powered industrial trucks", "(a) Forklift trucks and pallet jacks shall be operated safely."),
        doc("2", "1910", "1910.23", "Ladders", "(b) Ladder rungs and steps shall be level and spaced."),
        doc("3", "1910", "1910.147", "The control of hazardous energy", "(c) Lockout during servicing and maintenance of machines."),
        doc("4", "1910", "1910.212", "General requirements for all machines", "(a) Machine guarding of point of operation and nip points."),
    ]  # fmt: skip
    nep = [
        doc(
            "n1",
            "emphasis_program",
            "CPL 03-00-027",
            "Amputations",
            "amputation machinery rollers",
            ["31", "32", "33"],
        ),
        doc("n2", "emphasis_program", "CPL 03-00-025", "Falls", "falls from ladders and roofs"),
        doc("n3", "emphasis_program", "CPL 03-00-024", "Heat", "heat stress and dehydration"),
        doc("n4", "emphasis_program", "CPL 03-00-008", "Combustible dust", "dust explosions in silos"),
        doc("n5", "emphasis_program", "CPL 03-00-023", "Silica", "silica dust from cutting stone"),
    ]
    gdc = [doc("g", "general_duty", "OSH Act 5(a)(1)", "General Duty Clause", "recognized hazards")]
    return IndexRegistry(
        {"1910": Retriever(part), "emphasis_program": Retriever(nep), "general_duty": Retriever(gdc)}
    )


def test_tokenize_drops_stop_words_and_stems():
    assert tokenize("The employee was guarding the guards") == ["guard", "guard"]


def test_fuse_adds_reciprocal_ranks_with_equal_weight():
    scores = fuse([["a", "b"], ["b", "a"], ["b"]])
    assert scores["b"] > scores["a"]


def test_bm25_finds_the_matching_section(registry: IndexRegistry):
    result = registry.search("forklift struck a worker", naics="311")
    assert result.sections[0].section == "1910.178"
    assert result.sections[0].best.document.doc_id == "1"
    assert 0 < result.margin <= 1


def test_terms_in_the_language_of_the_rules_change_the_ranking(registry: IndexRegistry):
    plain = registry.search("a worker was hit and hurt", naics="311")
    with_terms = registry.search(
        "a worker was hit and hurt", naics="311", terms=["powered industrial truck", "forklift"]
    )
    assert with_terms.sections[0].section == "1910.178"
    assert plain.sections == [] or plain.sections[0].section != "1910.178" or plain.margin < with_terms.margin


def test_construction_falls_back_to_1910_with_a_note(registry: IndexRegistry):
    result = registry.search("fell from a ladder", naics="236220")
    assert result.part == "1910" and "1926" in result.note
    assert registry.part_for("332710") == ("1910", "")


def test_emphasis_programs_apply_by_industry_and_trigger():
    amputations = Document("n1", "emphasis_program", "CPL 03-00-027", "CPL 03-00-027", "Amputations", "text",
                           industries=["31", "32", "33"], triggers=["amputat"])  # fmt: skip
    falls = Document("n2", "emphasis_program", "CPL 03-00-025", "CPL 03-00-025", "Falls", "text",
                     triggers=[r"\b(fell|falls?|falling)\s+(\w+\s+){0,4}(from|off)\b"])  # fmt: skip
    metals = Document("n3", "emphasis_program", "CPL 03-00-018", "CPL 03-00-018", "Primary metals", "text",
                      industries=["331"])  # fmt: skip
    assert amputations.applies_to("fingertip amputated in rollers", "326")
    assert not amputations.applies_to("fingertip amputated in rollers", "452")
    assert falls.applies_to("He fell 12 feet from a ladder", "236")
    assert not falls.applies_to("She slipped on a doormat and fell", "311")
    # Report 20251111409: the dirt fell, not the worker.
    assert not falls.applies_to(
        "A section of dirt/rock fell from the side of the tunnel wall onto his legs.", "238"
    )
    assert falls.applies_to("He was standing on a box when he fell from the scaffold.", "238")
    for worker_fell in ("An employee installing solar panels fell from the roof to the garage.",
                        "An employee connecting structural steel fell approximately 17 feet from the beam.",
                        "An employee hanging dry wall fell from a 6-foot ladder."):  # fmt: skip
        assert falls.applies_to(worker_fell, "238"), worker_fell
    assert not falls.applies_to("The worker was below when a beam fell from the third floor.", "238")
    assert metals.applies_to("anything at all", "331110") and not metals.applies_to("anything", "332")


def test_registry_reports_only_programs_that_apply():
    nep = [
        Document("n1", "emphasis_program", "CPL 03-00-027", "CPL 03-00-027", "Amputations", "amputation",
                 industries=["31", "32", "33"], triggers=["amputat"]),
    ]  # fmt: skip
    part = [doc("1", "1910", "1910.212", "Machines", "(a) Guarding of rollers.")]
    registry = IndexRegistry({"1910": Retriever(part), "emphasis_program": Retriever(nep)})
    assert [
        h.document.citation for h in registry.search("finger amputated by rollers", naics="326").emphasis
    ] == ["CPL 03-00-027"]
    assert registry.search("spider bite at a desk", naics="326").emphasis == []


def test_general_duty_clause_is_always_available(registry: IndexRegistry):
    assert registry.general_duty().citation == "OSH Act 5(a)(1)"


def test_reference_files_are_valid():
    assert [d.citation for d in reference_documents("general_duty")] == ["OSH Act 5(a)(1)"]
    programs = reference_documents("emphasis_program")
    assert len(programs) == 12 and all(d.citation.startswith("CPL ") for d in programs)


needs_dense = pytest.mark.skipif(
    not dense_ready(),
    reason="embeddings extra not installed or the model is not cached (run `safereport build-index`)",
)
needs_index = pytest.mark.skipif(
    not (INDEX_DIR / "manifest.json").exists(), reason="run `safereport build-index` first"
)


@needs_index
def test_bm25_baseline_hit_rate_does_not_regress():
    # Measured on 19 November 2026 after the eCFR parser fixes: strict 0.288 and lenient 0.308
    # at 3 (narrative and OSHA codes). One case is 1.9 points, so the floors leave room for noise;
    # they catch a regression and were not used to tune anything.
    scores = score_retrieval(IndexRegistry.load(dense=False), load_answer_key())
    assert scores.cases == 51
    assert scores.strict_at_3 >= 0.25
    assert scores.lenient_at_3 >= 0.27


@needs_index
@needs_dense
def test_hybrid_hit_rate_does_not_regress():
    # Measured on 19 November 2026 after the eCFR parser fixes: strict 0.404 and lenient 0.500 at 3.
    scores = score_retrieval(IndexRegistry.load(dense=True), load_answer_key())
    assert scores.strict_at_3 >= 0.35
    assert scores.lenient_at_3 >= 0.45


@needs_index
@needs_dense
def test_emphasis_programs_need_shared_words_even_with_embeddings():
    registry = IndexRegistry.load(dense=True)
    assert registry.search("An employee was bitten by a spider at a computer.", naics="332").emphasis == []
    found = registry.search("Hand caught in rollers, fingertip amputated.", naics="326199").emphasis
    assert [h.document.citation for h in found][:1] == ["CPL 03-00-027"]


@needs_index
def test_real_holdout_reports_are_flagged_by_emphasis_programs_only_when_a_rule_fits():
    from safereport.data import REPORTS_PARQUET, ReportStore

    if not REPORTS_PARQUET.exists():
        pytest.skip("run `safereport build-data` first")
    registry = IndexRegistry.load(dense=False)
    rows = ReportStore().frame(
        "SELECT narrative, naics FROM reports WHERE split = 'holdout' ORDER BY id LIMIT 300"
    )
    flagged = sum(bool(registry.search(r.narrative, naics=r.naics).emphasis) for r in rows.itertuples())
    # The similarity ranking used before flagged 224 of these 300; the rules flag far fewer.
    assert flagged < 150


def test_a_missing_model_fails_fast_instead_of_downloading():
    pytest.importorskip("sentence_transformers")
    from safereport.retrieval import Encoder

    # A model that is not in the cache must raise at once, not try the Hugging Face hub.
    with pytest.raises(EmbeddingsUnavailableError, match="build-index"):
        Encoder("safereport-tests/no-such-model")
    assert not dense_ready("safereport-tests/no-such-model")
