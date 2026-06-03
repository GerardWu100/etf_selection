# GUIDE_post.md

## Purpose

`content/post/` contains publishable blog posts derived from the research in
this repository.

Each post should stand on top of the project's real code and saved artifacts.
The writing can simplify and interpret, but it should not drift away from what
the repository actually computes.

## Folder contract

Each post uses this structure:

```text
content/post/<slug>/
├── index.md
└── images/
```

- `index.md`
  - Hugo-compatible Markdown with lowercase frontmatter keys.
- `images/`
  - Charts and figures referenced by that post.

## Current posts

- `etf-selection-walkthrough/`
  - Walks through the ETF selection pipeline from universe screening to
    selector comparison.
