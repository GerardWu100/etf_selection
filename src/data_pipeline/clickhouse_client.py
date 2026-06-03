"""
ClickHouse connection helper shared by pipeline and correlation stages.
"""

from __future__ import annotations

import os

import clickhouse_connect
from dotenv import load_dotenv

from data_pipeline.paths import ENV_PATH


def build_client() -> clickhouse_connect.driver.Client:
    """
    Build a ClickHouse HTTP client from ``.env`` credentials.

    Returns
    -------
    clickhouse_connect.driver.Client
        Connected client using CLICKHOUSE_* environment variables.
    """
    # Load credentials once per call so scripts and notebooks behave the same
    # whether or not the caller already imported another pipeline module.
    load_dotenv(ENV_PATH)

    host = os.environ["CLICKHOUSE_HOST"]
    port = int(os.environ["CLICKHOUSE_PORT"])
    user = os.environ["CLICKHOUSE_USER"]
    password = os.environ["CLICKHOUSE_PASSWORD"]
    secure = os.environ.get("CLICKHOUSE_SECURE", "false").lower() == "true"
    verify = os.environ.get("CLICKHOUSE_VERIFY", "false").lower() == "true"

    return clickhouse_connect.get_client(
        host=host,
        port=port,
        username=user,
        password=password,
        secure=secure,
        verify=verify,
    )
