"""Issue #38: the Colab notebook is built from its section files, parses, and stays offline.

No data, no kernel and no network: these read the files only. Running the notebook end to end is
a separate check (notebooks/README.md).
"""

from __future__ import annotations

import ast
import importlib.util
import json
from pathlib import Path
import re

import pytest


ROOT = Path(__file__).parents[1]
SPEC = importlib.util.spec_from_file_location("build_notebook", ROOT / "notebooks" / "build_notebook.py")
build_mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(build_mod)

NOTEBOOK = json.loads(build_mod.NOTEBOOK.read_text(encoding="utf-8"))
CODE_CELLS = ["".join(c["source"]) for c in NOTEBOOK["cells"] if c["cell_type"] == "code"]
# Shapes of real keys (Anthropic, OpenAI, Google) and assignments of a literal to a key variable.
SECRET = re.compile(
    r"sk-ant-[A-Za-z0-9_-]{10,}|sk-[A-Za-z0-9]{20,}|AIza[0-9A-Za-z_-]{20,}"
    r"|(API_KEY|AUTH_TOKEN)['\"]?\s*[:=]\s*['\"][^'\"]+['\"]"
)


def test_notebook_matches_its_sections():
    assert build_mod.sources(NOTEBOOK) == build_mod.sources(build_mod.build(existing=None))


def test_notebook_is_valid_nbformat_4():
    assert NOTEBOOK["nbformat"] == 4
    assert NOTEBOOK["metadata"]["kernelspec"]["name"] == "python3"
    ids = [c["id"] for c in NOTEBOOK["cells"]]
    assert len(ids) == len(set(ids))
    for cell in NOTEBOOK["cells"]:
        assert cell["cell_type"] in {"markdown", "code"}
        if cell["cell_type"] == "code":
            assert {"execution_count", "outputs"} <= set(cell)


@pytest.mark.parametrize("index", range(len(CODE_CELLS)))
def test_every_code_cell_parses(index: int):
    ast.parse(CODE_CELLS[index])


def test_each_code_cell_follows_an_explanation():
    previous = None
    for cell in NOTEBOOK["cells"]:
        if cell["cell_type"] == "code" and previous is None:
            pytest.fail("the notebook starts with code")
        previous = cell["cell_type"]
    first_code = [i for i, c in enumerate(NOTEBOOK["cells"]) if c["cell_type"] == "code"]
    # A code cell follows markdown, or another code cell of the same step (at most two in a row).
    for i in first_code:
        assert (
            NOTEBOOK["cells"][i - 1]["cell_type"] == "markdown"
            or NOTEBOOK["cells"][i - 2]["cell_type"] == "markdown"
        )


def test_no_secret_in_cells_or_outputs():
    text = json.dumps(NOTEBOOK)
    assert not SECRET.search(text)


def test_stays_offline():
    code = "\n".join(CODE_CELLS)
    assert "live=False" in code
    assert "live=True" not in code
    assert "--live" not in code
    assert "OfflineBackend" in code  # the run is refused if any backend is not offline
    assert "[models]" not in code and ",models" not in code  # the paid model clients are not installed
    assert "userdata" not in code  # Colab secrets are never read


def test_pins_a_commit_or_tag():
    code = "\n".join(CODE_CELLS)
    ref = re.search(r'^REPO_REF = "([^"]+)"', code, re.MULTILINE)
    assert ref and ref.group(1) not in {"main", "master", "HEAD"}


def test_sections_name_their_owner():
    for path in build_mod.section_files():
        first = path.read_text(encoding="utf-8").splitlines()[0]
        assert first.startswith("# Owner:"), path.name


def test_parse_section_splits_markdown_and_code():
    text = "# Owner: x\n\n# %% [markdown]\n# ## Title\n# Some text.\n#\n# More.\n\n# %%\nx = 1\n\n\n# %%\nprint(x)\n"
    cells = build_mod.parse_section(text)
    assert [c["kind"] for c in cells] == ["markdown", "code", "code"]
    assert cells[0]["source"] == "## Title\nSome text.\n\nMore."
    assert cells[1]["source"] == "x = 1"


def test_rebuild_keeps_outputs_of_unchanged_cells(tmp_path: Path):
    sections = tmp_path / "sections"
    sections.mkdir()
    (sections / "10_a.py").write_text(
        "# Owner: a\n# %% [markdown]\n# Hi\n# %%\nx = 1\n# %%\ny = 2\n", encoding="utf-8"
    )
    first = build_mod.build(sections, existing=None)
    first["cells"][1]["outputs"] = [{"output_type": "stream", "name": "stdout", "text": ["1\n"]}]
    first["cells"][1]["execution_count"] = 1
    saved = tmp_path / "nb.ipynb"
    saved.write_text(json.dumps(first), encoding="utf-8")
    (sections / "10_a.py").write_text(
        "# Owner: a\n# %% [markdown]\n# Hi\n# %%\nx = 1\n# %%\ny = 3\n", encoding="utf-8"
    )
    again = build_mod.build(sections, existing=saved)
    assert again["cells"][1]["outputs"] == first["cells"][1]["outputs"]
    assert again["cells"][2]["outputs"] == []
