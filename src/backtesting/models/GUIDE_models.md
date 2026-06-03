# GUIDE_models.md

## Part 1 -- Conceptual Explanation

### Purpose and problem statement

This folder is currently a reserved placeholder for future model artifacts used
by the backtesting module.

At the moment, the buy-and-hold baseline does not train or load any models, so
this folder has no active runtime role. It exists so that future
model-driven extensions can store serialized artifacts locally to the
backtesting module rather than polluting the project root.

### Current state

- No active code writes here.
- The folder currently contains only `.gitkeep`.
- Nothing in the current pipeline depends on this folder.

## Part 2 -- Folder Tree and File Map

```text
backtesting/models/
├── GUIDE_models.md -- This folder guide.
└── .gitkeep        -- Keeps the empty folder under version control.
```

## Part 3 -- Code Reference

### Current code relationship

No current Python module reads from or writes to `backtesting/models/`.

If future backtesting work adds trained predictors, cached signal files, or
serialized model parameters, this folder is the intended home.

