# Selection notebook repair

## Problem

`explore_selection_methods.ipynb` contains saved output objects that do not
conform to the Jupyter notebook schema. Seven stream outputs lack the required
`name` field. The notebook also retains an old `AttributeError` from a setup
cell version that tried to read `SCREEN_CSV` from `notebook_support`.

The current setup cell is different: it imports `SCREEN_CSV` from
`data_pipeline.paths`, where that path is defined. Preserving the saved output
would retain an error that the current source no longer produces.

## Repair

Clear every code cell's saved outputs and execution count. Do not change the
selection calculations unless clean execution exposes a separate runtime bug.
Execute the notebook from the repository root so Jupyter regenerates valid
results from the current source.

Add an integration test that reads the notebook through `nbformat`, executes
it from the repository root, and checks that all code cells complete without
error outputs. This test will catch invalid notebook JSON and runtime failures,
including future import drift between the notebook and `src/` modules.

## Verification

The repair is complete when:

1. `nbformat` validates the cleared notebook.
2. The new integration test fails against the current invalid notebook, then
   passes after the repair.
3. A clean top-to-bottom notebook execution exits successfully.
4. The full test suite passes.

Update the notebook and test guides to record the executable-notebook contract,
then commit the implementation separately from this design note.
