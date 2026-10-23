"""Read-only selection of one existing self-purchase SKU for Hermes on-demand analysis.

This module never calls marketplace APIs, executes write SQL, sends messages or
exposes credentials. A caller must independently perform only the dated MPSTATS
reads returned by plan_requested_sku(), then call existing report assemblers.
"""
from __future__ import annotations

from pathlib import Path
import re
import sqlite3

try:
    from apps.msp_self_analytics.checkpoint_workflow import plan_checkpoint_reads
except ModuleNotFoundError:
    from checkpoint_workflow import plan_checkpoint_reads


class SkuRequestError(ValueError):
    pass


def _identity(marketplace: str, store: str, sku: str) -> tuple[str, str, str]:
    if not all(isinstance(v, str) and v == v.strip() and v for v
               in (marketplace, store, sku)):
        raise SkuRequestError("INVALID_CARD_IDENTITY")
    if marketplace not in ("wb", "oz"):
        raise SkuRequestError("UNSUPPORTED_MARKETPLACE")
    if not re.fullmatch(r"[a-zA-Z0-9_-]{1,50}", store):
        raise SkuRequestError("INVALID_STORE")
    if marketplace == "wb" and not re.fullmatch(r"[0-9]{1,20}", sku):
        raise SkuRequestError("INVALID_WB_SKU")
    if marketplace == "oz" and not re.fullmatch(r"[a-zA-Z0-9_.-]{1,100}", sku):
        raise SkuRequestError("INVALID_OZON_SKU")
    return marketplace, store, sku


def load_existing_series(
    database: str | Path,
    *,
    marketplace: str,
    store: str,
    sku: str,
    max_rows: int = 200,
) -> list[dict]:
    """Load one series; read-only SQLite URI plus parameterized selection.

    A recorded purchase date is the minimum observed completion evidence in
    this table. Review dates may be missing and must never be invented.
    """
    marketplace, store, sku = _identity(marketplace, store, sku)
    if type(max_rows) is not int or max_rows < 1:
        raise SkuRequestError("INVALID_ROW_LIMIT")
    path = Path(database).expanduser().resolve()
    if not path.is_file():
        raise SkuRequestError("SQLITE_NOT_FOUND")
    connection = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=10)
    try:
        connection.execute("PRAGMA query_only=ON")
        if connection.execute("PRAGMA query_only").fetchone()[0] != 1:
            raise SkuRequestError("SQLITE_NOT_READ_ONLY")
        cursor = connection.execute("""
            SELECT marketplace, store, marketplace_sku,
                   purchase_date, review_date, quantity, source_ordinal
            FROM self_purchase
            WHERE marketplace = ? AND store = ? AND marketplace_sku = ?
              AND purchase_date IS NOT NULL AND TRIM(purchase_date) <> ''
            ORDER BY purchase_date ASC, source_ordinal ASC
            LIMIT ?
        """, (marketplace, store, sku, max_rows + 1))
        raw = cursor.fetchall()
        if not raw:
            raise SkuRequestError("SKU_HAS_NO_RECORDED_PURCHASES")
        if len(raw) > max_rows:
            raise SkuRequestError("SERIES_ROW_LIMIT_EXCEEDED")
        return [
            {"marketplace": r[0], "store": r[1], "marketplace_sku": r[2],
             "purchase_date": r[3], "review_date": r[4],
             "quantity": r[5], "source_row": str(r[3]) + ":" + str(r[6]),
             "purchase_status": "completed"}
            for r in raw
        ]
    finally:
        connection.close()


def plan_requested_sku(
    database: str | Path,
    *,
    marketplace: str,
    store: str,
    sku: str,
    as_of: str,
    requested_days: int = 30,
    max_checkpoints: int = 12,
    max_provider_reads: int = 24,
) -> dict:
    """Select one card and return exact provider dates without fetching data.

    This first on-demand adapter is proven for WB external wb_sku(full).
    For Ozon, selection is possible but the WB provider cannot be substituted
    for an unverified Ozon source.
    """
    rows = load_existing_series(database, marketplace=marketplace,
                                store=store, sku=sku)
    if marketplace != "wb":
        return {"status": "OZON_PROVIDER_MAPPING_NOT_YET_VERIFIED",
                "identity": (marketplace, store, sku),
                "recorded_purchase_rows": len(rows),
                "source_writes": 0, "marketplace_actions_allowed": False,
                "requests": []}
    plan = plan_checkpoint_reads(
        rows, as_of=as_of, requested_days=requested_days,
        max_checkpoints=max_checkpoints, max_provider_reads=max_provider_reads,
    )
    return {"status": plan["status"],
            "identity": (marketplace, store, sku),
            "recorded_purchase_rows": len(rows),
            "rows_for_local_analysis_only": rows,
            "analysis_plan": plan,
            "provider": "MPSTATS_WB_SKU_FULL",
            "source_writes": 0,
            "marketplace_actions_allowed": False}
