#!/usr/bin/env python3
"""Run a read-only historical source query from this checkout, not installed Skill."""
import argparse
from datetime import datetime
import json
from pathlib import Path
import sys
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from apps.msp_self_analytics.rating_history_query import (
    query_history, format_history_ru, review_date_summary, format_review_date_summary_ru,
)
from scripts.remote.msp_self_sku_report_cli import MpstatsReader


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--marketplace', required=True, choices=['wb', 'oz'])
    parser.add_argument('--sku', required=True)
    parser.add_argument('--from', dest='d1', required=True)
    parser.add_argument('--to', dest='d2', required=True)
    parser.add_argument('--json', action='store_true')
    parser.add_argument('--review-date', help='Exact review_date from the registry, never purchase_date')
    parser.add_argument('--own-review-date', action='append', default=[], help='Other registered own review dates')
    args = parser.parse_args()
    try:
        result = query_history(MpstatsReader(), marketplace=args.marketplace, sku=args.sku,
                               d1=args.d1, d2=args.d2,
                               as_of=datetime.now(ZoneInfo('Europe/Moscow')).date().isoformat())
        if args.review_date:
            result['review_date_analysis'] = review_date_summary(
                result, review_date=args.review_date, own_review_dates=args.own_review_date)
    except (ValueError, RuntimeError, OSError):
        # Transport exceptions may contain authenticated URLs. Never echo them.
        print('Запрос не выполнен: проверьте даты, доступ и лимит чтений.', file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        if args.review_date:
            print(format_review_date_summary_ru(result['review_date_analysis']))
        else:
            print(format_history_ru(result))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
