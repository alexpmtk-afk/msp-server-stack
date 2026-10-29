"""Offline, no-network commands for local marketplace reports."""
import argparse
import json
import os
from pathlib import Path

from .archive import DEFAULT_ROOT, import_csv, verify
from .versioned_archive import import_csv_versioned, verify_versioned_scope
from .generation_recovery import quarantine_uncommitted


def main(argv=None):
    p = argparse.ArgumentParser(description="MSP WB/Ozon local archive (offline stage)")
    p.add_argument("--root", type=Path, default=Path(os.environ.get("MSP_MARKETPLACE_REPORTS_ROOT", str(DEFAULT_ROOT))))
    sub = p.add_subparsers(dest="action", required=True)
    imp = sub.add_parser("import-csv", help="import an existing local CSV, NOT fetch from provider")
    imp.add_argument("--dataset", required=True)
    imp.add_argument("--cabinet", required=True)
    imp.add_argument("--period", required=True, help="YYYY for WB, YYYY-MM for Ozon")
    imp.add_argument("--source", type=Path, required=True)
    vimp = sub.add_parser("import-csv-versioned", help="explicit opt-in immutable generation import; refuses legacy")
    vimp.add_argument("--dataset", required=True)
    vimp.add_argument("--cabinet", required=True)
    vimp.add_argument("--period", required=True)
    vimp.add_argument("--source", type=Path, required=True)
    vchk = sub.add_parser("verify-versioned", help="read-only integrity check of one versioned scope")
    vchk.add_argument("--dataset", required=True)
    vchk.add_argument("--cabinet", required=True)
    vchk.add_argument("--period", required=True)
    repair = sub.add_parser("quarantine-uncommitted", help="explicit evidence retention; NOT full CURRENT restore")
    repair.add_argument("--dataset", required=True)
    repair.add_argument("--cabinet", required=True)
    repair.add_argument("--scope-period", required=True, help="year for Ozon FINAL, usual period otherwise")
    repair.add_argument("--expected-generation", required=True)
    repair.add_argument("--expected-digest", required=True)
    repair.add_argument("--candidate", required=True, action="append")
    repair.add_argument("--acknowledge", required=True, action="store_true")
    sub.add_parser("verify", help="read-only local checksum and row-key verification")
    sub.add_parser("status", help="read-only local file inventory")
    args = p.parse_args(argv)
    if args.action == "import-csv":
        result = import_csv(args.root, args.dataset, args.cabinet, args.period, args.source)
    elif args.action == "import-csv-versioned":
        result = import_csv_versioned(args.root, args.dataset, args.cabinet,
                                      args.period, args.source)
    elif args.action == "verify-versioned":
        result = verify_versioned_scope(args.root, args.dataset, args.cabinet,
                                        args.period)
    elif args.action == "quarantine-uncommitted":
        result = quarantine_uncommitted(
            args.root, args.dataset, args.cabinet, args.scope_period,
            expected_generation=args.expected_generation,
            expected_digest=args.expected_digest,
            candidates=args.candidate, acknowledged=args.acknowledge)
    else:
        result = verify(args.root)
        if args.action == "status":
            result = {"files": result["files"], "ok": result["ok"],
                      "reports": result["verified"], "failures": result["failures"],
                      "provider_coverage_proven": False}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok", True) else 1


if __name__ == "__main__":
    raise SystemExit(main())
