"""Never infer installed/running versions from a workspace checkout."""
from .security import sha

def version_report(workspace,canonical,installed,running):
    for value in (workspace,canonical,installed,running):
        if value is not None:sha(value)
    if running and running!=installed:raise ValueError('running_release_mismatch')
    return {'workspace_sha':workspace,'canonical_github_sha':canonical,'installed_release_sha':installed,'running_release_sha':running,'installed_matches_canonical':installed is not None and installed==canonical}
