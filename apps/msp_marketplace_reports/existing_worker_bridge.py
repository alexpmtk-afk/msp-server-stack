"""Opt-in contract for the existing scheduler, not a second queue/daemon.

No Redis/HTTP/credential configuration on import. The approved launcher supplies
one sender and root, then binds step_existing_job to the existing queue instance.
Only explicit report-unit jobs are supported; old discovery/finalization jobs
are not migrated. Deployment/host placement must be approved independently.
"""
from __future__ import annotations
import asyncio
import math
from datetime import datetime, timezone
from .generation_store import GenerationError
from .wb_worker_adapter import run_one_step, _dataset

MODE = 'msp-versioned-wb-v1'
SELECTION = 'explicit-wb-report-units-v1'

async def step_existing_job(queue, state, *, root, send):
    """Perform <=1 adapter step, persist through the EXISTING queue API only."""
    if state.get('archive_mode') != MODE or state.get('selection_contract') != SELECTION:
        raise GenerationError('explicit WB bridge job contract required')
    if state.get('phase') != 'DOWNLOAD' or state.get('finalize') or state.get('current_rrd_id', 0):
        raise GenerationError('legacy active cursor/finalization must not be migrated')
    if state.get('completed_report_ids'):
        raise GenerationError('legacy completed IDs need verified coverage reconciliation')
    fragments = state.get('fragments')
    index = state.get('report_index', 0)
    if type(fragments) is not list or not fragments or type(index) is not int or not 0 <= index < len(fragments):
        raise GenerationError('invalid explicit WB report inventory/index')
    fragment = fragments[index]
    if type(fragment) is not dict or type(fragment.get('report_id')) is not int or fragment['report_id'] <= 0:
        raise GenerationError('invalid explicit WB report identity')
    kind = fragment.get('report_type')
    dataset = _dataset(kind)
    # run_one_step owns page-state/cursor and the supplied sender owns admission.
    # Do not call legacy call_spec or reserve a second slot here.
    result = await asyncio.to_thread(run_one_step, root, state['cabinet'], state['year'],
                                    fragment['report_id'], kind, send)
    status = result.get('status')
    if status == 'WAITING_RATE_LIMIT':
        retry = result.get('retry_after_seconds')
        if type(retry) not in (int, float) or not math.isfinite(retry) or retry < 0:
            raise GenerationError('invalid WB retry delay')
        try:
            instant = datetime.fromisoformat(result['not_before_utc'])
            if instant.tzinfo is None:
                raise ValueError('timezone missing')
        except (KeyError, TypeError, ValueError) as exc:
            raise GenerationError('invalid WB not-before timestamp') from exc
        delay = max(float(retry), (instant - datetime.now(timezone.utc)).total_seconds(), 0.0)
        state['status'] = 'WAITING_RATE_LIMIT'
        state['retry_after_seconds'] = delay
        state['not_before_utc'] = instant.isoformat()
        await queue._save(state)
        await queue._schedule(state['job_id'], delay)
    elif status == 'PAGE_STAGED':
        state['status'] = 'QUEUED'
        state.pop('not_before_utc', None)
        state.pop('retry_after_seconds', None)
        # Cursor is only an observation; never use it as a request cursor.
        state['page_cursor_observed'] = result['cursor']
        await queue._save(state)
        await queue._schedule(state['job_id'], 0.0)
    elif status == 'LOCAL_VERIFIED_NOT_PROVIDER_COMPLETE':
        unit = f'{dataset}:{fragment["report_id"]}'
        state.setdefault('verified_report_units', {})[unit] = {
            'generation': result['generation'], 'manifest_sha256': result['manifest_sha256'],
            'rows': result['rows'], 'provider_coverage_proven': False,
        }
        state['report_index'] = index + 1
        state['status'] = 'COMPLETE' if index + 1 == len(fragments) else 'QUEUED'
        state.pop('not_before_utc', None)
        state.pop('retry_after_seconds', None)
        await queue._save(state)
        if state['status'] == 'COMPLETE':
            await queue._unschedule(state['job_id'])
        else:
            await queue._schedule(state['job_id'], 0.0)
    else:
        raise GenerationError('unknown WB adapter outcome; job not acknowledged')
    return {**result, 'job_id': state['job_id'], 'job_status': state['status'],
            'selection_scope': SELECTION, 'provider_coverage_proven': False}
