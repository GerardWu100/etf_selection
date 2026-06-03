"""
cli.py
------
Command-line entrypoint for the point-in-time feature-engineering pipeline.
"""
# ruff: noqa: E402

from __future__ import annotations

import argparse
import json
import pathlib
import tomllib
from typing import Any

import pandas as pd

from correlation_analysis.correlate_utils import build_client, resolve_analysis_window
from data_pipeline.paths import PROJECT_ROOT
from feature_engineering.cross_sectional import run_cross_sectional_features
from feature_engineering.enrich import apply_context_joins
from feature_engineering.features import build_timeframe_frames, run_feature_registry
from feature_engineering.labels import run_label_registry
from feature_engineering.normalize import normalize_source_frames
from feature_engineering.sessionize import (
    attach_session_primitives,
    build_session_primitives,
)
from feature_engineering.source_adapters import load_source_frame


def _load_config(config_path: pathlib.Path) -> dict[str, Any]:
    """Read the TOML configuration for one feature-engineering run."""
    with config_path.open("rb") as handle:
        return tomllib.load(handle)


def _parse_args() -> argparse.Namespace:
    """Parse the small CLI surface for research runs."""
    parser = argparse.ArgumentParser(
        description="Point-in-time feature engineering pipeline"
    )
    parser.add_argument(
        "--config",
        type=pathlib.Path,
        default=pathlib.Path(__file__).with_name("config.toml"),
        help="Path to the feature-engineering config TOML.",
    )
    parser.add_argument(
        "--start-date",
        type=str,
        default=None,
        help="Optional inclusive start-date override.",
    )
    parser.add_argument(
        "--end-date",
        type=str,
        default=None,
        help="Optional inclusive end-date override.",
    )
    parser.add_argument(
        "--run-name", type=str, default=None, help="Optional output-folder override."
    )
    return parser.parse_args()


def _build_source_lists(
    config: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Split the config into primary and context source lists."""
    primary_sources = [dict(source) for source in config.get("primary_sources", [])]
    if not primary_sources:
        raise ValueError("Config must define at least one [[primary_sources]] entry.")
    for source in primary_sources:
        source["is_primary_source"] = True

    context_sources = [dict(source) for source in config.get("context_sources", [])]
    for source in context_sources:
        source["is_primary_source"] = False

    return primary_sources, context_sources


def _load_all_sources(
    client,
    all_sources: list[dict[str, Any]],
    start_date: str,
    end_date: str,
) -> dict[str, pd.DataFrame]:
    """Load every configured source from ClickHouse."""
    raw_frames: dict[str, pd.DataFrame] = {}
    for source in all_sources:
        if not bool(source.get("enabled", True)):
            raw_frames[str(source["name"])] = pd.DataFrame()
            continue
        raw_frames[str(source["name"])] = load_source_frame(
            client,
            source_config=source,
            start_date=start_date,
            end_date=end_date,
        )
    return raw_frames


def _build_primary_frame(
    normalized_frames: dict[str, pd.DataFrame],
    primary_sources: list[dict[str, Any]],
) -> pd.DataFrame:
    """Concatenate primary sources into one base frame."""
    parts = [
        normalized_frames[str(source["name"])]
        for source in primary_sources
        if bool(source.get("enabled", True))
    ]
    if not parts:
        raise ValueError("At least one primary source must be enabled.")
    primary_frame = pd.concat(parts, ignore_index=True)
    return primary_frame.sort_values(["symbol", "timestamp"]).reset_index(drop=True)


def _apply_symbol_metadata(
    frame: pd.DataFrame,
    symbol_metadata: dict[str, dict[str, Any]],
) -> pd.DataFrame:
    """Attach optional per-symbol metadata such as peer groups."""
    if not symbol_metadata:
        frame["peer_group"] = pd.NA
        return frame

    enriched = frame.copy()
    metadata_frame = pd.DataFrame.from_dict(symbol_metadata, orient="index")
    metadata_frame.index.name = "symbol"
    metadata_frame = metadata_frame.reset_index()
    enriched = enriched.merge(metadata_frame, on="symbol", how="left")
    if "peer_group" not in enriched.columns:
        enriched["peer_group"] = pd.NA
    return enriched


def _build_run_paths(
    config: dict[str, Any], run_name_override: str | None
) -> pathlib.Path:
    """Create the output folder for one run."""
    folder_name = run_name_override or str(config["run"]["name"])
    configured_output_dir = pathlib.Path(
        str(config["run"].get("output_dir", "outputs/feature_engineering"))
    )
    if configured_output_dir.is_absolute():
        output_root = configured_output_dir
    else:
        output_root = PROJECT_ROOT / configured_output_dir
    run_dir = output_root / folder_name
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def _write_run_audit(
    run_dir: pathlib.Path,
    config: dict[str, Any],
    session_primitives: pd.DataFrame,
    enriched_context: pd.DataFrame,
    feature_matrix: pd.DataFrame,
    context_audit: pd.DataFrame,
    feature_manifest: pd.DataFrame,
) -> None:
    """Write one compact audit log describing the run outputs and null coverage."""
    audit_rows = [
        {
            "section": "run",
            "name": "output_dir",
            "metric": "value",
            "value": run_dir.as_posix(),
        },
        {
            "section": "run",
            "name": "analysis_window",
            "metric": "value",
            "value": f"{config['run']['start_date']} -> {config['run']['end_date']}",
        },
        {
            "section": "output",
            "name": "session_primitives",
            "metric": "rows",
            "value": int(len(session_primitives)),
        },
        {
            "section": "output",
            "name": "enriched_context",
            "metric": "rows",
            "value": int(len(enriched_context)),
        },
        {
            "section": "output",
            "name": "feature_matrix",
            "metric": "rows",
            "value": int(len(feature_matrix)),
        },
    ]

    for row in feature_manifest.itertuples(index=False):
        audit_rows.append(
            {
                "section": row.kind,
                "name": row.name,
                "metric": "null_rate",
                "value": row.null_rate,
            }
        )

    for row in context_audit.to_dict(orient="records"):
        for metric in [
            "null_rate",
            "stale_rate",
            "mean_effective_lag_minutes",
            "max_effective_lag_minutes",
        ]:
            audit_rows.append(
                {
                    "section": "context_join",
                    "name": row["context_name"],
                    "metric": metric,
                    "value": row.get(metric),
                }
            )

    pd.DataFrame(audit_rows).to_csv(run_dir / "run_audit_log.csv", index=False)


def main() -> None:
    """Run the full feature-engineering pipeline."""
    args = _parse_args()
    config = _load_config(args.config)
    primary_sources, context_sources = _build_source_lists(config)

    start_date, end_date = resolve_analysis_window(
        args.start_date or config["run"]["start_date"],
        args.end_date or config["run"]["end_date"],
    )
    config["run"]["start_date"] = start_date
    config["run"]["end_date"] = end_date
    internal_timezone = str(config["run"]["internal_timezone"])
    run_dir = _build_run_paths(config, args.run_name)

    client = build_client()
    all_sources = primary_sources + context_sources
    raw_frames = _load_all_sources(client, all_sources, start_date, end_date)
    normalized_frames = normalize_source_frames(
        raw_frames, all_sources, internal_timezone
    )

    primary_frame = _build_primary_frame(normalized_frames, primary_sources)
    primary_frame = _apply_symbol_metadata(
        primary_frame, config.get("symbol_metadata", {})
    )

    classified_bars, session_primitives = build_session_primitives(primary_frame)
    base_bars = attach_session_primitives(classified_bars, session_primitives)
    regular_bars = base_bars[base_bars["market_session"] == "regular"].copy()
    regular_bars = regular_bars.sort_values(["symbol", "timestamp"]).reset_index(
        drop=True
    )

    normalized_context_frames = {
        str(source["name"]): normalized_frames[str(source["name"])]
        for source in context_sources
        if bool(source.get("enabled", True))
    }
    enriched_context, context_audit = apply_context_joins(
        regular_bars,
        context_configs=context_sources,
        normalized_context_frames=normalized_context_frames,
    )

    timeframe_frames = build_timeframe_frames(
        regular_bars,
        timeframe_configs=config.get("timeframes", []),
    )
    feature_frame, feature_manifest = run_feature_registry(
        enriched_context,
        timeframe_frames=timeframe_frames,
        feature_configs=config.get("features", []),
    )
    xs_frame, xs_manifest = run_cross_sectional_features(
        feature_frame,
        cross_sectional_configs=config.get("cross_sectional", []),
    )
    feature_matrix, label_manifest = run_label_registry(
        xs_frame,
        session_primitives=session_primitives,
        label_configs=config.get("labels", []),
    )
    full_manifest = pd.concat(
        [feature_manifest, xs_manifest, label_manifest],
        ignore_index=True,
    )

    session_primitives.to_parquet(run_dir / "session_primitives.parquet", index=False)
    enriched_context.to_parquet(run_dir / "enriched_context.parquet", index=False)
    feature_matrix.to_parquet(run_dir / "feature_matrix.parquet", index=False)
    full_manifest.to_csv(run_dir / "feature_manifest.csv", index=False)
    context_audit.to_csv(run_dir / "context_join_audit.csv", index=False)
    _write_run_audit(
        run_dir=run_dir,
        config=config,
        session_primitives=session_primitives,
        enriched_context=enriched_context,
        feature_matrix=feature_matrix,
        context_audit=context_audit,
        feature_manifest=full_manifest,
    )

    (run_dir / "resolved_config.json").write_text(
        json.dumps(config, indent=2), encoding="utf-8"
    )

    print(f"Saved feature-engineering artifacts to {run_dir}")
    print(f"Session primitives rows: {len(session_primitives):,}")
    print(f"Enriched regular-bar rows: {len(enriched_context):,}")
    print(f"Feature matrix rows: {len(feature_matrix):,}")


if __name__ == "__main__":
    main()
