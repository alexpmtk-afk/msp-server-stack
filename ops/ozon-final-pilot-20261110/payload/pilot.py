"""One fixed FINAL read. Retain response before parsing; never auto-retry."""
import asyncio
import calendar
import hashlib
import json
import os
import re
from pathlib import Path
import sys
import time
import traceback
import urllib.error
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parent))
from apps.msp_marketplace_reports import quota as q
from apps.msp_marketplace_reports.providers import Request
from apps.msp_marketplace_reports.runtime import load_credentials, _headers, _NoRedirect
from apps.msp_marketplace_reports.ingest import write_staging_csv
from apps.msp_marketplace_reports.shared_rate_limit import build_rules, RateRule, key_prefix

PLAN = {"cabinet": "ozon_dmitrieva", "year": 2026, "month": 1,
        "path": "/v1/finance/realization/posting", "max_send_entries": 1}
STATE = Path('/opt/mcp/data/msp-marketplace-reports/ozon-pilot-20261110')
LIMIT = 128 * 1024 * 1024

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def syncdir(path):
    fd = os.open(path, os.O_DIRECTORY | os.O_RDONLY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)

def save(path, raw, mode=0o600):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode)
    try:
        with os.fdopen(fd, 'wb', closefd=False) as stream:
            stream.write(raw)
            stream.flush()
        os.fchmod(fd, mode)
        os.fsync(fd)
    finally:
        os.close(fd)
    syncdir(path.parent)

def doc(value):
    return (json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False) + '\n').encode()

def strict(raw):
    def pairs(items):
        out = {}
        for k, v in items:
            if k in out:
                raise ValueError('duplicate JSON key')
            out[k] = v
        return out
    return json.loads(raw, object_pairs_hook=pairs,
                      parse_constant=lambda x: (_ for _ in ()).throw(ValueError('nonfinite JSON')))

class FinalQuota(q.SharedQuota):
    """Scoped FINAL approval, not the legacy four-method blanket gate."""
    def reserve(self, request):
        if request != Request('ozon', PLAN['path'], {'year': 2026, 'month': 1}):
            raise ValueError('outside fixed FINAL pilot')
        url = self._approved_url()
        owner = q.stable_owner_key('ozon', self.credentials)
        rules = build_rules(service='ozon', cabinet_key=owner,
                            host='api-seller.ozon.ru', operation_id='ozon_finance', scope='finance')
        # Additional local pacing, NOT a claim about Ozon's method maximum.
        rules.append(RateRule(key_prefix('ozon', owner) + ':msp-finance-safety', 60.0))
        async def work(ctl):
            return await ctl.try_acquire(rules)
        granted, wait = asyncio.run(q._with_controller(url, work))
        if not granted:
            raise q.QuotaBusy(wait)
        return rules

def validate(raw):
    data = strict(raw)
    if not isinstance(data, dict) or not isinstance(data.get('header'), dict) or not isinstance(data.get('rows'), list):
        raise ValueError('unexpected report envelope')
    header, rows = data['header'], data['rows']
    if header.get('start_date', '')[:10] != '2026-01-01' or header.get('stop_date', '')[:10] != '2026-01-31':
        raise ValueError('report period mismatch')
    if not isinstance(header.get('number'), str) or not header['number'].strip():
        raise ValueError('report identity missing')
    if not rows:
        raise ValueError('empty report requires explicit coverage reconciliation')
    seen = set()
    result = []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError('row object required')
        number = row.get('row_number')
        if type(number) is not int or number <= 0 or number in seen:
            raise ValueError('invalid or duplicate row identity')
        if any(k in row for k in ('report_year', 'report_month', '_raw_json')):
            raise ValueError('source collides with archive keys')
        seen.add(number)
        result.append({**row, 'report_year': 2026, 'report_month': '2026-01'})
    return header, result

def execute(state=STATE, factory=None):
    """A verified retained response is replayed locally, without credentials or HTTP."""
    entry = state / 'entry.json'
    rawpath = state / 'response.json'
    meta = state / 'response.meta.json'
    if rawpath.exists():
        ledger = strict(entry.read_bytes())
        details = strict(meta.read_bytes())
        raw = rawpath.read_bytes()
        if ledger != PLAN or details.get('status') != 200 or details.get('sha256') != sha(raw):
            raise ValueError('saved response integrity failure')
    else:
        if entry.exists() or meta.exists():
            raise ValueError('previous entry outcome requires reconciliation; no retry')
        credentials = load_credentials(Path(os.environ['CREDENTIALS_DIRECTORY']) / 'cabinets.json')
        if set(credentials) != {PLAN['cabinet']}:
            raise ValueError('pilot credentials scope')
        cred = credentials[PLAN['cabinet']]
        headers = _headers('ozon', cred)
        gate = FinalQuota('ozon', cred)
        gate._approved_url()
        save(entry, doc(PLAN))  # conservative cumulative entry, never reset
        request = Request('ozon', PLAN['path'], {'year': 2026, 'month': 1})
        rules = gate.reserve(request)
        opener = factory() if factory else urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())
        req = urllib.request.Request('https://api-seller.ozon.ru' + PLAN['path'],
                    data=b'{"year":2026,"month":1}', headers=headers, method='POST')
        save(state / 'dispatch.json', doc({'attempts': 1}))
        try:
            with opener.open(req, timeout=60) as response:
                status = int(response.status)
                raw = response.read(LIMIT + 1)
        except urllib.error.HTTPError as exc:
            save(meta, doc({'status': int(exc.code)}))
            if exc.code == 429:
                gate.cooldown(rules, exc.headers)
            raise ValueError('HTTP non-success; no retry') from None
        if len(raw) > LIMIT:
            save(meta, doc({'status': status, 'oversize': True}))
            raise ValueError('response exceeds bounded storage')
        save(rawpath, raw)
        save(meta, doc({'status': status, 'bytes': len(raw), 'sha256': sha(raw)}))
        if status != 200:
            raise ValueError('unexpected HTTP status')
    header, rows = validate(raw)
    stage = state / 'report.csv'
    if not stage.exists():
        temporary = state / 'report.csv.staging'
        if temporary.exists():
            raise ValueError('interrupted CSV publication requires reconciliation')
        write_staging_csv(temporary, rows, ('report_year', 'report_month', 'row_number'))
        with temporary.open('rb') as stream:
            os.fsync(stream.fileno())
        os.chmod(temporary, 0o644)
        os.rename(temporary, stage)
        syncdir(state)
    else:
        # Verify existing CSV via the same canonical encoder without filesystem writes.
        import tempfile
        with tempfile.TemporaryDirectory(dir=state, prefix='verify-') as tmp:
            check = Path(tmp) / 'report.csv'
            write_staging_csv(check, rows, ('report_year', 'report_month', 'row_number'))
            if check.read_bytes() != stage.read_bytes():
                raise ValueError('saved CSV differs from retained response')
    for path in (rawpath, meta, entry):
        os.chmod(path, 0o644)
    return {'status': 'VALIDATED_PILOT_NOT_PUBLISHED', 'cabinet': PLAN['cabinet'],
            'period': '2026-01', 'rows': len(rows), 'response_sha256': sha(raw),
            'csv_sha256': sha(stage.read_bytes()), 'provider_http_status': 200,
            'max_send_entries': 1, 'annual_coverage_complete': False}

def main():
    try:
        approval = strict((Path(__file__).parent / 'approval.json').read_bytes())
        if approval.get('plan') != PLAN or not time.time() < approval.get('expires_epoch', 0):
            raise ValueError('pilot authorization missing or expired')
        receipt = execute()
        code = 0
    except Exception as exc:
        receipt = {'status': 'HOLD', 'error_type': type(exc).__name__,
                   'cabinet': PLAN['cabinet'], 'period': '2026-01',
                   'response_retained': (STATE / 'response.json').exists(),
                   'entry_consumed': (STATE / 'entry.json').exists(),
                   'frames': [{'file': Path(f.filename).name, 'function': f.name, 'line': f.lineno}
                              for f in traceback.extract_tb(exc.__traceback__)[-6:]]}
        meta = STATE / 'response.meta.json'
        if meta.exists():
            try:
                status = strict(meta.read_bytes()).get('status')
                if type(status) is int:
                    receipt['provider_http_status'] = status
            except Exception:
                pass
        if (STATE / 'response.json').exists():
            try:
                data = strict((STATE / 'response.json').read_bytes())
                shape = {'top_type': type(data).__name__}
                if isinstance(data, dict):
                    shape['known_top_keys'] = [k for k in ('header', 'rows', 'result', 'error', 'code', 'message') if k in data]
                    rows = data.get('rows')
                    shape['rows_type'] = type(rows).__name__
                    if isinstance(rows, list):
                        shape['row_count'] = len(rows)
                        if rows and isinstance(rows[0], dict):
                            shape['first_row_fields'] = sorted(k for k in rows[0] if re.fullmatch('[a-z_]{1,60}', k))[:64]
                    header = data.get('header')
                    if isinstance(header, dict):
                        shape['report_number_present'] = bool(header.get('number'))
                        for field in ('start_date', 'stop_date'):
                            value = header.get(field)
                            if isinstance(value, str) and re.fullmatch(r'[0-9T:Z+. -]{1,40}', value):
                                shape[field] = value
                receipt['response_shape'] = shape
            except Exception:
                pass
        code = 1
    save(STATE / 'worker-result.json', doc(receipt), 0o644)
    return code

if __name__ == '__main__':
    raise SystemExit(main())
