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
