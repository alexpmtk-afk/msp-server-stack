"""Ozon-only MCP schemas verified independently of WB: arrays and no_data."""
TOOL = 'ozon_sku'


def normalize(comments, period):
    """Do not invent WB cache metadata or accept WB comment envelopes."""
    flags=[]
    if isinstance(comments,list):
        normalized_comments={'comments':comments}
    else:
        normalized_comments=None;flags.append('OZON_COMMENTS_LIST_UNAVAILABLE')
    normalized_period=None
    if isinstance(period,list):
        normalized_period=[]
        for row in period:
            if not isinstance(row,dict):
                flags.append('OZON_MALFORMED_DAILY_ROW');continue
            # Ozon no_data is a provider missing-data flag, never an observed
            # zero rating/count. Missing/invalid flag is not proven coverage.
            valid=type(row.get('no_data')) is int and row['no_data']==0
            normalized_period.append({**row,'daynum':1 if valid else 0})
    else:flags.append('OZON_PERIOD_LIST_UNAVAILABLE')
    return {'marketplace':'oz','tool':TOOL,'comments':normalized_comments,
            'period':normalized_period,'quality_flags':flags,
            'four_counters_verified':False,'complete_publication_history':False}
