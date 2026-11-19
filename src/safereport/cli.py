"""Command line entry point: `safereport <command>`.

Each command imports what it needs when it runs, so `safereport check` starts fast and works
without the optional extras (torch, faiss, model clients).
"""

from __future__ import annotations

import argparse
import json
import time

from safereport import __version__
from safereport.config import MODELS_FILE, load_model_settings
from safereport.labels import LABEL_DIR, load_answer_key


def check() -> None:
    """Load the model config and the answer key, and say what is ready."""
    from safereport.baseline import MODEL_PATH
    from safereport.data import REPORTS_PARQUET
    from safereport.retrieval import INDEX_DIR

    settings = load_model_settings()
    print(f"Models ({MODELS_FILE.name}):")
    for spec in settings.models:
        price = (
            "price unknown"
            if spec.prices is None
            else f"${spec.prices[0]:g} / ${spec.prices[1]:g} per M tokens"
        )
        print(f"  {spec.label:<22} {spec.model_id:<22} {price}, checked {spec.checked_on}")
    print(f"  fallback: {' > '.join(settings.router.fallback_order)}")
    key = load_answer_key()
    with_standard = sum(case.has_standard for case in key)
    print(f"Answer key ({LABEL_DIR.name}/answer_key.csv): {len(key)} cases, {with_standard} with a standard.")
    for label, path in (
        ("Reports", REPORTS_PARQUET),
        ("Indexes", INDEX_DIR / "manifest.json"),
        ("Baseline", MODEL_PATH),
    ):
        print(f"{label}: {'ready' if path.exists() else 'not built'} ({path.name})")


def build_data() -> None:
    from safereport.data import REPORTS_PARQUET, build_parquet

    started = time.perf_counter()
    rows = build_parquet()
    print(f"{rows} reports written to {REPORTS_PARQUET} in {time.perf_counter() - started:.1f}s")


def fetch_ecfr(part: str) -> None:
    from safereport.ecfr import ECFR_DATE, download_part

    path = download_part(part)
    print(f"Part {part} as of {ECFR_DATE} saved to {path} ({path.stat().st_size / 1e6:.1f} MB)")


def build_index(dense: bool) -> None:
    from safereport.retrieval import build_indexes

    print(json.dumps(build_indexes(dense=dense), indent=2))
    if dense:
        from safereport.data import ReportStore
        from safereport.retrieval import Encoder
        from safereport.similar import build_narrative_index

        count = build_narrative_index(ReportStore(), Encoder())
        print(f"Narrative index: {count} reports embedded for the similar injury search")


def train_baseline() -> None:
    from safereport.baseline import (
        CODES_V3_PATH,
        MODEL_PATH,
        EventBaseline,
        accuracy_by_level,
        coverage_curve,
        recode_to_oiics_3,
    )
    from safereport.data import ReportStore

    # The recoded events are rebuilt from scratch, so read the reports without the old ones.
    store = ReportStore(codes_v3=None)
    # Same OIICS version as the 2025 holdout: 2024 and the 2025 reports outside the holdout.
    train = store.frame(
        "SELECT narrative, event_code FROM reports WHERE oiics_version = 3 AND split <> 'holdout'"
    )
    holdout = store.frame("SELECT narrative, event_code FROM reports WHERE split = 'holdout'")
    started = time.perf_counter()
    baseline = EventBaseline().fit(train["narrative"].tolist(), train["event_code"].tolist())
    baseline.save()
    predictions = baseline.predict(holdout["narrative"].tolist())
    actual = holdout["event_code"].tolist()
    print(f"Trained on {len(train)} reports in {time.perf_counter() - started:.0f}s, saved to {MODEL_PATH}")
    print("Holdout accuracy:", accuracy_by_level([p.code for p in predictions], actual))
    print(coverage_curve(predictions, actual, [0.0, 0.3, 0.5, 0.7, 0.9]).to_string(index=False))
    everything = store.frame("SELECT id, narrative, oiics_version, event_code FROM reports")
    codes = recode_to_oiics_3(everything, baseline)
    codes.to_parquet(CODES_V3_PATH, index=False)
    print(
        f"OIICS 3 codes for {len(codes)} reports ({int(codes['event_v3_estimated'].sum())} estimated) in {CODES_V3_PATH}"
    )


def eval_retrieval(dense: bool) -> None:
    from safereport.evaluation import score_retrieval
    from safereport.retrieval import IndexRegistry, dense_ready

    if dense and not dense_ready():
        print(
            "The embedding model is not cached; scoring BM25 only. Run `safereport build-index` once online."
        )
        dense = False
    registry = IndexRegistry.load(dense=dense)
    key = load_answer_key()
    for with_codes in (False, True):
        scores = score_retrieval(registry, key, with_codes=with_codes)
        label = "narrative and OSHA codes" if with_codes else "narrative only"
        print(f"{'hybrid' if dense else 'BM25 only'}, {label}: {scores.as_dict()}")


def eval_baselines(dense: bool) -> None:
    from safereport.evaluation import RESULTS_DIR, write_phase1_results

    print(json.dumps(write_phase1_results(dense=dense), indent=2))
    print(f"Written to {RESULTS_DIR}")


def ask(request: str, mode: str, approve: bool, answers: list[str], live: bool = False) -> None:
    """Run the crew once on the offline backend and print the answer and the trace.

    Questions from the Planner are answered from `--answer key=value` or typed in; the week's list
    is approved with `--approve`, otherwise the command stops and shows it.
    """
    from langgraph.types import Command

    from safereport.graph import build_graph, load_services, run_config, sqlite_checkpointer

    services = load_services(mode=mode, live=live)
    print(
        f"Models answering: {', '.join(sorted(services.router.backends))}"
        f" ({'live where a key is set' if live else 'offline rules'})"
    )
    graph = build_graph(services, sqlite_checkpointer())
    config = run_config()
    given = dict(item.split("=", 1) for item in answers)
    out = graph.invoke({"request": request}, config)
    while "__interrupt__" in out:
        question = out["__interrupt__"][0].value
        if "missing" in question:
            reply = {
                m: given.get(m) or input(f"{q} ")
                for m, q in zip(question["missing"], question["questions"], strict=True)
            }
            out = graph.invoke(Command(resume=reply), config)
            continue
        for row in question["rows"]:
            print(
                f"  {row['decision']:<11} {row['report_id']:<14} priority {row['priority']:<6g} {row['reason']}"
            )
        if not approve:
            print("Stopped at the approval step; run again with --approve to approve the list.")
            return
        out = graph.invoke(Command(resume={"action": "approve", "by": "command line"}), config)
    print(out["answer"])
    print("\nTrace:")
    for step in out["trace"]:
        model = f" [{step['model']}]" if step.get("model") else ""
        print(f"  {step['agent']}{model}: {step['summary']}")


def employer_pairs(draw: bool) -> None:
    from safereport.employer_check import PAIRS_FILE, draw_pairs, score, write_pairs

    if draw:
        from safereport.data import ReportStore

        pairs = draw_pairs(ReportStore())
        write_pairs(pairs)
        print(f"{len(pairs)} pairs written to {PAIRS_FILE}; fill same_employer with yes or no.")
    print(json.dumps(score(), indent=2))


def eval_live(model: str, smoke_count: int, run_score: bool) -> None:
    from safereport import live_eval

    if smoke_count:
        for row in live_eval.smoke(model, smoke_count):
            print(f"{row['id']}: {row['terms']}\n    {row['narrative']}")
    if run_score:
        print(json.dumps(live_eval.score(model), indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(prog="safereport", description="SafeReport Crew, by Seven Team-5374.")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("check", help="validate the model config and the answer key, and list what is built")
    commands.add_parser("build-data", help="write the reports as Parquet with the 2025 holdout split")
    fetch = commands.add_parser("fetch-ecfr", help="download a part of Title 29 from the eCFR API")
    fetch.add_argument("--part", default="1910", choices=["1910", "1926"])
    index = commands.add_parser(
        "build-index", help="build the retrieval indexes from eCFR and data/reference"
    )
    index.add_argument("--no-dense", action="store_true", help="BM25 only, without embeddings")
    commands.add_parser("train-baseline", help="train the TF IDF and logistic regression event coder")
    evaluate = commands.add_parser("eval-retrieval", help="score standards retrieval on the answer key")
    evaluate.add_argument("--no-dense", action="store_true", help="BM25 only, without embeddings")
    baselines = commands.add_parser(
        "eval-baselines", help="score every Phase 1 baseline and save to eval/results"
    )
    baselines.add_argument("--no-dense", action="store_true", help="BM25 only, without embeddings")
    pairs = commands.add_parser("employer-pairs", help="score the hand check of employer matching")
    pairs.add_argument("--draw", action="store_true", help="draw a new sample of pairs first")
    live = commands.add_parser("eval-live", help="the live standards experiment (paid, cached, capped)")
    live.add_argument("--model", required=True, choices=["claude", "gpt_nano", "gemini_flash", "gemma_local"])
    live.add_argument("--smoke", type=int, default=0, help="show terms for this many reports outside the key")
    live.add_argument("--score", action="store_true", help="run once over the answer key and score it")
    commands.add_parser("live-summary", help="compare the scored live runs with the baseline (no calls)")
    run = commands.add_parser("ask", help="run the crew on a request with the offline backend")
    run.add_argument("request")
    run.add_argument("--mode", default="lowest_cost", choices=["lowest_cost", "best_quality", "private"])
    run.add_argument("--approve", action="store_true", help="approve the week's list when asked")
    run.add_argument(
        "--answer", action="append", default=[], help="answer a Planner question, e.g. state=Texas"
    )
    args = parser.parse_args()
    if args.command == "check":
        check()
    elif args.command == "build-data":
        build_data()
    elif args.command == "fetch-ecfr":
        fetch_ecfr(args.part)
    elif args.command == "build-index":
        build_index(dense=not args.no_dense)
    elif args.command == "train-baseline":
        train_baseline()
    elif args.command == "eval-retrieval":
        eval_retrieval(dense=not args.no_dense)
    elif args.command == "eval-baselines":
        eval_baselines(dense=not args.no_dense)
    elif args.command == "employer-pairs":
        employer_pairs(args.draw)
    elif args.command == "eval-live":
        eval_live(args.model, args.smoke, args.score)
    elif args.command == "live-summary":
        from safereport import live_eval

        print(json.dumps(live_eval.summary(), indent=2))
    elif args.command == "ask":
        ask(args.request, args.mode, args.approve, args.answer, live=args.live)


if __name__ == "__main__":
    main()
