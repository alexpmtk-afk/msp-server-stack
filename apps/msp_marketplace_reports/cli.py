"""Offline, no-network commands for local marketplace reports."""
import argparse
import json
import os
from pathlib import Path

from .archive import DEFAULT_ROOT, import_csv, verify


def main(argv=None):
    p = argparse.ArgumentParser(description="MSP WB/Ozon local archive (offline stage)")
    p.add_argument("--root", type=Path, default=Path(os.environ.get("MSP_MARKETPLACE_REPORTS_ROOT", str(DEFAULT_ROOT))))
    sub = p.add_subparsers(dest="action", required=True)
    imp = sub.add_parser("import-csv", help="import an existing local CSV, NOT fetch from provider")
    imp.add_argument("--dataset", required=True)
    imp.add_argument("--cabinet", required=True)
    imp.add_argument("--period", required=True, help="YYYY for WB, YYYY-MM for Ozon")
    imp.add_argument("--source", type=Path, required=True)
    sub.add_parser("verify", help="read-only local checksum and row-key verification")
    sub.add_parser("status", help="read-only local file inventory")
    args = p.parse_args(argv)
    if args.action == "import-csv":
        result = import_csv(args.root, args.dataset, args.cabinet, args.period, args.source)
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
