"""Optional public WB source: current snapshot plus a partial dated review feed.

No seller credentials, marketplace writes or past-state reconstruction. Public
endpoints are unofficial; failures are not converted to empty successful data.
"""
from datetime import datetime, timezone
import gzip
import json
import re
from urllib.parse import urlsplit
import urllib.request


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _get_json(url):
    req = urllib.request.Request(url, headers={'Accept': 'application/json', 'Accept-Encoding': 'gzip'})
    with urllib.request.build_opener(_NoRedirect).open(req, timeout=25) as response:
        body = response.read(8_000_001)
        if len(body) > 8_000_000:
            raise ValueError('PUBLIC_RESPONSE_TOO_LARGE')
        if response.headers.get('Content-Encoding') == 'gzip':
            # Bounded decompression even for an unexpectedly large response.
            from io import BytesIO
            body = gzip.GzipFile(fileobj=BytesIO(body)).read(8_000_001)
        if len(body) > 8_000_000:
            raise ValueError('PUBLIC_RESPONSE_TOO_LARGE')
        return json.loads(body)


def normalize_public_feedbacks(payload, *, sku, imt_id, observed_at_utc):
    if not isinstance(payload, dict) or not isinstance(payload.get('feedbacks'), list):
        raise ValueError('WB_PUBLIC_SCHEMA_UNAVAILABLE')
    records, seen, conflicts = [], {}, set()
    for row in payload['feedbacks']:
        if not isinstance(row, dict) or str(row.get('nmId')) != sku:
            continue
        rating, stamp, identifier = row.get('productValuation'), row.get('createdDate'), row.get('id')
        if type(rating) not in (int, float) or rating not in (1, 2, 3, 4, 5) or not isinstance(identifier, str):
            continue
        try:
            parsed = datetime.fromisoformat(stamp.replace('Z', '+00:00'))
            if parsed.tzinfo is None:
                continue
        except (AttributeError, TypeError, ValueError):
            continue
        exclusion = row.get('excludedFromRating')
        record = {
            'id': identifier, 'sku': sku,
            'published_at_utc': parsed.astimezone(timezone.utc).isoformat(),
            'provider_updated_at': row.get('updatedDate'),
            'valuation': rating,
            'has_text': any(isinstance(row.get(k), str) and bool(row[k].strip()) for k in ('text', 'pros', 'cons')),
            'excluded_from_rating_now': exclusion.get('isExcluded') if isinstance(exclusion, dict) else None,
        }
        if identifier in seen:
            if seen[identifier] != record:
                conflicts.add(identifier)
            continue
        seen[identifier] = record
        records.append(record)
    records = [r for r in records if r['id'] not in conflicts]
    distributions = payload.get('nmValuationDistribution') or []
    own = [r.get('valuationDistribution') for r in distributions
           if isinstance(r, dict) and str(r.get('nm')) == sku]
    return {
        'source': 'WB_PUBLIC_FEEDBACKS_V2_UNOFFICIAL', 'sku': sku, 'imt_id': imt_id,
        'observed_at_utc': observed_at_utc,
        'snapshot_scope': 'CURRENT_IMT_FAMILY_NOT_HISTORICAL_SKU_TOTAL',
        'family_rating': payload.get('valuation'),
        'family_feedback_count': payload.get('feedbackCount'),
        'family_text_feedback_count': payload.get('feedbackCountWithText'),
        'family_star_distribution': payload.get('valuationDistribution'),
        'sku_star_distribution_now': own[0] if len(own) == 1 else None,
        'records': sorted(records, key=lambda r: (r['published_at_utc'], r['id'])),
        'received_sku_records': len(records), 'conflicting_ids_count': len(conflicts),
        'complete_publication_history': False,
        'historical_inclusion_status_known': False,
        'limitation': 'CURRENT_COUNTERS_AND_INCLUSION_FLAGS_CANNOT_BE_BACKDATED',
    }


def collect_public_wb(*, sku, card_url):
    if not isinstance(sku, str) or not re.fullmatch(r'[0-9]{1,20}', sku):
        raise ValueError('INVALID_WB_SKU')
    parsed = urlsplit(card_url)
    expected = f'/vol{int(sku)//100000}/part{int(sku)//1000}/{sku}/info/ru/card.json'
    if (parsed.scheme != 'https' or parsed.username or parsed.password or parsed.port or
            not re.fullmatch(r'basket-[0-9]+\.wbbasket\.ru', parsed.hostname or '') or
            parsed.path != expected or parsed.query or parsed.fragment):
        raise ValueError('UNVERIFIED_WB_CARD_URL')
    card = _get_json(card_url)
    if not isinstance(card, dict) or str(card.get('nm_id')) != sku or type(card.get('imt_id')) is not int:
        raise ValueError('WB_CARD_IDENTITY_MISMATCH')
    imt_id = card['imt_id']
    hosts = _get_json(f'https://feedback-bt.wildberries.ru/feedback/api/v2/host?imt={imt_id}')
    if not isinstance(hosts, list) or not hosts or not isinstance(hosts[0], str):
        raise ValueError('WB_FEEDBACK_HOST_UNAVAILABLE')
    host = hosts[0].rstrip('/')
    h = urlsplit(host)
    if h.scheme != 'https' or not re.fullmatch(r'[a-z0-9-]+\.wb\.ru', h.netloc) or h.path or h.query or h.fragment:
        raise ValueError('UNVERIFIED_WB_FEEDBACK_HOST')
    url = f'{host}/feedbacks/v2/{imt_id}'
    payload = _get_json(url)
    result = normalize_public_feedbacks(payload, sku=sku, imt_id=imt_id,
                                       observed_at_utc=datetime.now(timezone.utc).isoformat())
    result['source_url'] = url
    result['card_url'] = card_url
    return result
