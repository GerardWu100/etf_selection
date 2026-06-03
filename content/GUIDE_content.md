# GUIDE_content.md

## Purpose

The `content/` tree stores human-facing writing that explains the research in
this repository.

Right now that means Hugo-style blog posts under `content/post/`. These posts
are not the source of truth for the quantitative methods. The source of truth
remains the Python modules, notebooks, and checked-in output artifacts. The
content layer translates those technical pieces into a narrative that is easier
to read and share.

## What lives here

- `post/`
  - One folder per article.
  - Each post folder contains an `index.md` file and a local `images/` folder
    for charts copied or generated for that article.

## How this connects to the rest of the repo

- `src/` and `notebooks/` provide the implementation and research logic.
- `outputs/` provides the charts and tables that posts can cite or reuse.
- `content/` packages that material into a reader-facing explanation.

## Editing expectations

- Keep posts evidence-backed. Do not invent metrics, charts, or claims that are
  not supported by the repository.
- Store article-specific images inside the post folder instead of pointing at
  `outputs/` directly. That keeps each post self-contained.
- When adding a new article folder, add or update the relevant guide if the
  structure changes.
