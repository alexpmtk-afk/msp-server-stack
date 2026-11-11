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
        if request != Request('ozon', PLAN['path'], {'year': 2026, 'month': PLAN['month']}):
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
    if header.get('start_date', '')[:10] != f"2026-{PLAN['month']:02d}-01" or header.get('stop_date', '')[:10] != f"2026-{PLAN['month']:02d}-{calendar.monthrange(2026,PLAN['month'])[1]}":
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
        result.append({**row, 'report_year': 2026, 'report_month': f"2026-{PLAN['month']:02d}"})
    return header, result

def execute(state=None, factory=None):
    state = STATE if state is None else state
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
        request = Request('ozon', PLAN['path'], {'year': 2026, 'month': PLAN['month']})
        rules = gate.reserve(request)
        save(entry, doc(PLAN))  # durable before HTTP; quota-only wait consumes no send
        opener = factory() if factory else urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())
        req = urllib.request.Request('https://api-seller.ozon.ru' + PLAN['path'],
                    data=doc({'year':2026,'month':PLAN['month']}), headers=headers, method='POST')
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
            'period': f"2026-{PLAN['month']:02d}", 'rows': len(rows), 'response_sha256': sha(raw),
            'csv_sha256': sha(stage.read_bytes()), 'provider_http_status': 200,
            'max_send_entries': 1, 'annual_coverage_complete': False}

ARCHIVE = Path('/opt/mcp/data/msp-marketplace-reports')
HISTORY = ARCHIVE / 'ozon-final-2026'
CABINETS = ('ozon_dmitrieva', 'ozon_laser_master', 'ozon_novokshenov')

def load_job(path):
    import stat
    st = path.lstat()
    if not stat.S_ISREG(st.st_mode) or st.st_uid != 0 or st.st_mode & 0o022 or st.st_nlink != 1:
        raise ValueError('job ownership')
    job = strict(path.read_bytes())
    if set(job) != {'cabinet', 'month', 'year', 'nonce', 'expires_epoch'}:
        raise ValueError('job schema')
    if job['cabinet'] not in CABINETS or type(job['month']) is not int or not 1 <= job['month'] <= 10 or job['year'] != 2026:
        raise ValueError('job outside approved closed months')
    if not re.fullmatch('[0-9a-f]{32}', job['nonce']) or not time.time() < job['expires_epoch'] <= time.time() + 600:
        raise ValueError('job nonce or expiry')
    return job

def seed_verified_pilot(state):
    if PLAN['cabinet'] != 'ozon_dmitrieva' or PLAN['month'] != 1 or (state / 'entry.json').exists():
        return
    source = ARCHIVE / 'ozon-pilot-20261110'
    raw = (source / 'response.json').read_bytes()
    csv = (source / 'report.csv').read_bytes()
    if sha(raw) != 'e2373acc17d2dedbbc8dacc8a072d8ecb9bc1b8b02e54bc24d3b434933cc5e49' or sha(csv) != '3e95d6d28b8f54c0e4420abb82b57d0781b538164987b01323734102fe458134':
        raise ValueError('verified pilot changed; no refetch')
    entry = strict((source / 'entry.json').read_bytes())
    meta = strict((source / 'response.meta.json').read_bytes())
    if entry != PLAN or meta.get('status') != 200 or meta.get('sha256') != sha(raw):
        raise ValueError('pilot provenance')
    save(state / 'entry.json', doc(entry))
    save(state / 'response.json', raw)
    save(state / 'response.meta.json', doc(meta))

def business_rows(raw):
    import csv,io
    rows = list(csv.DictReader(io.StringIO(raw.decode('utf-8-sig')), delimiter=';'))
    indexed = {}
    for row in rows:
        key = tuple(row[k] for k in ('report_year', 'report_month', 'row_number'))
        if key in indexed:
            raise ValueError('duplicate published key')
        indexed[key] = row
    return indexed

def open_ozon_read_access(root, cabinet):
    """Only financial files in this exact Ozon scope; writer locks stay private."""
    import stat
    dataset = root / '.b7-generations' / 'ozon_final_realization'
    scope = dataset / cabinet / '2026'
    selected = [dataset, dataset / cabinet, scope, *scope.rglob('*')]
    for path in selected:
        st = path.lstat()
        if stat.S_ISLNK(st.st_mode) or st.st_uid != os.geteuid() or st.st_mode & 0o022:
            raise ValueError('unsafe Ozon reader path')
        if stat.S_ISDIR(st.st_mode):
            os.chmod(path, 0o755)
        elif stat.S_ISREG(st.st_mode) and st.st_nlink == 1:
            if path.name != '.writer.lock':
                os.chmod(path, 0o644)
        else:
            raise ValueError('unknown Ozon archive inode')

def publish_verified(state, result, root=ARCHIVE):
    from apps.msp_marketplace_reports import generation_store as g
    from apps.msp_marketplace_reports.versioned_archive import import_csv_versioned, read_csv_versioned
    period = f"2026-{PLAN['month']:02d}"
    cabinet = PLAN['cabinet']
    source = state / 'report.csv'
    expected = business_rows(source.read_bytes())
    active = g.read_active(root, 'ozon_final_realization', cabinet, '2026')
    name = 'monthly/' + period + '.csv'
    if active and name in active['files'] and business_rows(active['files'][name]) != expected:
        raise ValueError('existing published month conflicts; no replacement')
    receipt = import_csv_versioned(root, 'ozon_final_realization', cabinet, period, source)
    raw, pinned = read_csv_versioned(root, 'ozon_final_realization', cabinet, period,
                                    pinned_generation=receipt['generation'], expected_digest=receipt['manifest_sha256'])
    if business_rows(raw) != expected:
        raise ValueError('published values differ from staged response')
    open_ozon_read_access(root, cabinet)
    return {**result, 'status': 'COMPLETE', 'generation': receipt['generation'],
            'published_sha256': pinned['sha256'], 'published_manifest_sha256': receipt['manifest_sha256'],
            'provider_coverage': 'one complete nonpaginated monthly realization response',
            'annual_coverage_complete': False}

def main():
    global PLAN,STATE
    job = load_job(Path(__file__).parent / 'job.json')
    PLAN = {'cabinet': job['cabinet'], 'year': 2026, 'month': job['month'],
            'path': '/v1/finance/realization/posting', 'max_send_entries': 1}
    STATE = HISTORY / job['cabinet'] / f"2026-{job['month']:02d}"
    try:
        seed_verified_pilot(STATE)
        result = publish_verified(STATE, execute())
        code = 0
    except q.QuotaBusy as exc:
        result = {'status': 'WAIT_QUOTA', 'wait_seconds': min(300, max(1, exc.retry_after_seconds)),
                  'entry_consumed': (STATE / 'entry.json').exists()}
        code = 0
    except Exception as exc:
        result = {'status': 'HOLD', 'error_type': type(exc).__name__,
                  'entry_consumed': (STATE / 'entry.json').exists(),
                  'response_retained': (STATE / 'response.json').exists(),
                  'frames': [{'file': Path(f.filename).name, 'function': f.name, 'line': f.lineno}
                             for f in traceback.extract_tb(exc.__traceback__)[-6:]]}
        meta = STATE / 'response.meta.json'
        if meta.exists():
            details = strict(meta.read_bytes())
            result['provider_http_status'] = details.get('status')
        code = 1
    result.update(cabinet=job['cabinet'], period=f"2026-{job['month']:02d}", nonce=job['nonce'])
    save(STATE / 'runs' / (job['nonce'] + '.json'), doc(result), 0o644)
    return code

if __name__ == '__main__':
    raise SystemExit(main())
