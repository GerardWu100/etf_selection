# 2026-06-17_001_main_smoke

## Purpose

This folder preserves one reproducible smoke-test run of the repository root
entrypoint.

## Files

- `main.py`
  - Copy of the script that was executed.
- `stdout.txt`
  - Standard output captured from the script.
- `stderr.txt`
  - Standard error captured from the script.
- `exit_code.txt`
  - Process exit code from the script run.

## Command

```bash
uv run python main.py
```
