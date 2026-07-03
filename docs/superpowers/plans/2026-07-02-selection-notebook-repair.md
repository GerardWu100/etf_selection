# Selection Notebook Repair Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `explore_selection_methods.ipynb` a valid Jupyter notebook that executes from top to bottom against the current project modules.

**Architecture:** Keep the notebook's current calculations unchanged. Add one integration test for notebook schema validation and clean execution, discard all saved cell state, execute the notebook in place, and document the executable-notebook contract in the existing notebook and test guides.

**Tech Stack:** Python 3.14, `pytest`, `nbformat`, `nbconvert`, Jupyter notebooks

---

### Task 1: Add the selection notebook regression test

**Files:**
- Create: `tests/integration/test_selection_notebook.py`

- [ ] **Step 1: Write the failing test**

```python
"""Integration coverage for the selection-method walkthrough notebook."""

from pathlib import Path

import nbformat
from nbconvert.preprocessors import ExecutePreprocessor


PROJECT_ROOT = Path(__file__).resolve().parents[2]
NOTEBOOK_PATH = (
    PROJECT_ROOT
    / "notebooks"
    / "01_project_walkthrough"
    / "explore_selection_methods.ipynb"
)
EXECUTION_TIMEOUT_SECONDS = 120


def test_selection_notebook_is_valid_and_executes_without_errors() -> None:
    """Validate and execute every selection walkthrough code cell."""
    with NOTEBOOK_PATH.open(encoding="utf-8") as notebook_file:
        notebook = nbformat.read(notebook_file, as_version=4)

    nbformat.validate(notebook)
    executor = ExecutePreprocessor(
        timeout=EXECUTION_TIMEOUT_SECONDS,
        kernel_name="python3",
    )
    executor.preprocess(
        notebook,
        resources={"metadata": {"path": str(PROJECT_ROOT)}},
    )

    error_outputs = [
        output
        for cell in notebook.cells
        for output in cell.get("outputs", [])
        if output.get("output_type") == "error"
    ]
    assert error_outputs == []
```

- [ ] **Step 2: Run the test and verify the existing notebook fails validation**

Run: `uv run pytest tests/integration/test_selection_notebook.py -v`

Expected: FAIL with `NotebookValidationError: 'name' is a required property`.

- [ ] **Step 3: Commit the failing regression test**

Run `git add .`, then run `git commit -m "test: cover selection notebook execution"` as a separate command.

### Task 2: Remove corrupt saved notebook state

**Files:**
- Modify: `notebooks/01_project_walkthrough/explore_selection_methods.ipynb`

- [ ] **Step 1: Clear all saved outputs and execution counts**

Run these commands separately:

```bash
jq '(.cells[] | select(.cell_type == "code") | .execution_count) = null | (.cells[] | select(.cell_type == "code") | .outputs) = []' notebooks/01_project_walkthrough/explore_selection_methods.ipynb > /tmp/explore_selection_methods.cleared.ipynb
mv /tmp/explore_selection_methods.cleared.ipynb notebooks/01_project_walkthrough/explore_selection_methods.ipynb
```

Expected: every code cell has `execution_count: null` and `outputs: []`.

- [ ] **Step 2: Validate the cleared notebook**

Run:

```bash
uv run python -c 'import nbformat; notebook = nbformat.read("notebooks/01_project_walkthrough/explore_selection_methods.ipynb", as_version=4); nbformat.validate(notebook)'
```

Expected: exit status 0 with no schema error.

- [ ] **Step 3: Execute the notebook in place**

Run:

```bash
env MPLCONFIGDIR=/tmp/mpl IPYTHONDIR=/tmp/ipython UV_CACHE_DIR=/home/gh/.cache/uv uv run python -m nbconvert --ExecutePreprocessor.shutdown_kernel=immediate --to notebook --execute --inplace notebooks/01_project_walkthrough/explore_selection_methods.ipynb
```

Expected: exit status 0 and no Python traceback.

- [ ] **Step 4: Run the regression test**

Run: `uv run pytest tests/integration/test_selection_notebook.py -v`

Expected: PASS.

- [ ] **Step 5: Commit the repaired notebook**

Run `git add .`, then run `git commit -m "fix: regenerate selection walkthrough notebook"` as a separate command.

### Task 3: Update developer guides and verify the repository

**Files:**
- Modify: `notebooks/GUIDE_notebooks.md`
- Modify: `tests/GUIDE_tests.md`

- [ ] **Step 1: Document the notebook contract**

Add to the selection notebook entry in `notebooks/GUIDE_notebooks.md`:

```markdown
  - Imports shared paths from `data_pipeline.paths` and must execute cleanly
    from the repository root without relying on saved kernel state.
```

Add to `tests/GUIDE_tests.md`:

```markdown
- `tests/integration/test_selection_notebook.py`
  - Jupyter schema validation for the selection walkthrough
  - clean top-to-bottom execution from the repository root
```

- [ ] **Step 2: Run focused notebook integration tests**

Run: `uv run pytest tests/integration -v`

Expected: both notebook integration tests pass.

- [ ] **Step 3: Run the complete test suite**

Run: `uv run pytest`

Expected: all tests pass.

- [ ] **Step 4: Inspect the final diff and saved notebook errors**

Run: `git diff --check`

Run:

```bash
jq '[.cells[] | .outputs? // [] | .[] | select(.output_type == "error")] | length' notebooks/01_project_walkthrough/explore_selection_methods.ipynb
```

Expected: `git diff --check` exits with status 0 and `jq` prints `0`.

- [ ] **Step 5: Commit guides and final verification state**

Run `git add .`, then run `git commit -m "docs: record selection notebook execution contract"` as a separate command.
