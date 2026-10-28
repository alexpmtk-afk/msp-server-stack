"""WB-only observed MCP schemas. No inferred four-counter distribution."""
TOOL = 'wb_sku'


def normalize(comments, period):
    """WB comments is an object with comments/cache; period is a daily list."""
    flags=[]
    if not (isinstance(comments,dict) and isinstance(comments.get('comments'),list)):
        comments=None;flags.append('WB_COMMENTS_OBJECT_UNAVAILABLE')
    if not isinstance(period,list):
        period=None;flags.append('WB_PERIOD_LIST_UNAVAILABLE')
    return {'marketplace':'wb','tool':TOOL,'comments':comments,'period':period,
            'quality_flags':flags,'four_counters_verified':False,
            'complete_publication_history':False}
