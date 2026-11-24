"""Assemble notebooks/safereport_crew.ipynb from the section files in notebooks/sections/.

Usage:
    python -I notebooks/build_notebook.py           # write the notebook (code cells without outputs)
    python -I notebooks/build_notebook.py --check   # exit 1 if the notebook's cells differ from the sections

Each section is a plain Python file in the "percent" format, so two people can edit their own
sections without touching the same JSON:

    # %% [markdown]
    # ## A heading
    # Text of the markdown cell, each line starting with "# ".

    # %%
    print("a code cell")

Sections are joined in file name order (10_..., 20_..., 30_...). The first line of a section file
is a comment naming its owner and is not copied into the notebook. Outputs saved by a Colab run
are kept when the cell's source is unchanged, so rebuilding does not throw away a run.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys


HERE = Path(__file__).resolve().parent
SECTIONS = HERE / "sections"
NOTEBOOK = HERE / "safereport_crew.ipynb"
MARKDOWN = "# %% [markdown]"
CODE = "# %%"

METADATA = {
    "colab": {"provenance": [], "toc_visible": True, "name": "safereport_crew.ipynb"},
    "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
    "language_info": {"name": "python"},
}


def parse_section(text: str) -> list[dict]:
    """The cells of one section file, in order; text before the first marker is dropped."""
    cells: list[dict] = []
    kind, lines = None, []

    def close() -> None:
        if kind is None:
            return
        body = list(lines)
        while body and not body[-1].strip():
            body.pop()
        while body and not body[0].strip():
            body.pop(0)
        if kind == "markdown":
            body = [line[2:] if line.startswith("# ") else line.lstrip("#") for line in body]
        if body:
            cells.append({"kind": kind, "source": "\n".join(body)})

    for line in text.splitlines():
        stripped = line.rstrip()
        if stripped == MARKDOWN:
            close()
            kind, lines = "markdown", []
        elif stripped == CODE:
            close()
            kind, lines = "code", []
        else:
            lines.append(stripped)
    close()
    return cells


def section_files(folder: Path = SECTIONS) -> list[Path]:
    return sorted(p for p in folder.glob("*.py") if p.name[:2].isdigit())


def cell_id(index: int, source: str) -> str:
    return hashlib.sha1(f"{index}:{source}".encode()).hexdigest()[:12]  # noqa: S324 - an id, not security


def to_notebook_cell(index: int, cell: dict, outputs: dict[str, dict]) -> dict:
    lines = cell["source"].splitlines(keepends=True)
    if cell["kind"] == "markdown":
        return {
            "cell_type": "markdown",
            "id": cell_id(index, cell["source"]),
            "metadata": {},
            "source": lines,
        }
    kept = outputs.get(cell["source"], {})
    return {
        "cell_type": "code",
        "execution_count": kept.get("execution_count"),
        "id": cell_id(index, cell["source"]),
        "metadata": {},
        "outputs": kept.get("outputs", []),
        "source": lines,
    }


def saved_outputs(path: Path) -> dict[str, dict]:
    """Outputs of the existing notebook's code cells, keyed by their source."""
    if not path.exists():
        return {}
    notebook = json.loads(path.read_text(encoding="utf-8"))
    return {
        "".join(c["source"]): {"outputs": c.get("outputs", []), "execution_count": c.get("execution_count")}
        for c in notebook["cells"]
        if c["cell_type"] == "code"
    }


def build(folder: Path = SECTIONS, existing: Path | None = NOTEBOOK) -> dict:
    cells = [
        cell for path in section_files(folder) for cell in parse_section(path.read_text(encoding="utf-8"))
    ]
    outputs = saved_outputs(existing) if existing else {}
    return {
        "cells": [to_notebook_cell(i, cell, outputs) for i, cell in enumerate(cells)],
        "metadata": METADATA,
        "nbformat": 4,
        "nbformat_minor": 5,
    }


def sources(notebook: dict) -> list[tuple[str, str]]:
    return [(c["cell_type"], "".join(c["source"])) for c in notebook["cells"]]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="compare only; do not write")
    args = parser.parse_args(argv)
    notebook = build()
    if args.check:
        if not NOTEBOOK.exists():
            print(f"{NOTEBOOK} does not exist; run without --check")
            return 1
        current = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
        if sources(current) != sources(notebook):
            print(f"{NOTEBOOK.name} is out of date with notebooks/sections; run build_notebook.py")
            return 1
        print(f"{NOTEBOOK.name} matches the {len(section_files())} section files")
        return 0
    NOTEBOOK.write_text(
        json.dumps(notebook, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n"
    )
    print(f"Wrote {NOTEBOOK} with {len(notebook['cells'])} cells from {len(section_files())} sections")
    return 0


if __name__ == "__main__":
    sys.exit(main())
