"""Integration coverage for the allocation-method walkthrough notebook."""

from pathlib import Path

import nbformat
from nbconvert.preprocessors import ExecutePreprocessor

PROJECT_ROOT = Path(__file__).resolve().parents[2]
NOTEBOOK_PATH = (
    PROJECT_ROOT
    / "notebooks"
    / "01_project_walkthrough"
    / "explore_allocation_methods.ipynb"
)
EXPECTED_CHART_COUNT = 9


def test_allocation_notebook_executes_and_embeds_charts() -> None:
    """Run the notebook top-to-bottom and require all allocation charts."""
    with NOTEBOOK_PATH.open(encoding="utf-8") as notebook_file:
        notebook = nbformat.read(notebook_file, as_version=4)

    notebook_source = "\n".join(
        "".join(cell.get("source", "")) for cell in notebook.cells
    )
    assert "methods.mean_variance(" in notebook_source
    assert '_show(w, "mean_variance")' in notebook_source

    executor = ExecutePreprocessor(timeout=120, kernel_name="python3")
    executor.preprocess(
        notebook,
        resources={"metadata": {"path": str(PROJECT_ROOT)}},
    )

    embedded_pngs = [
        output
        for cell in notebook.cells
        for output in cell.get("outputs", [])
        if output.get("output_type") in {"display_data", "execute_result"}
        and "image/png" in output.get("data", {})
    ]
    assert len(embedded_pngs) == EXPECTED_CHART_COUNT
