def build_sdoc_ai_context(data, username):
    context = {
        'username': username,
        'org_id': data.get('org_id'),
        'repo_id': data.get('repo_id'),
        'scenario': data.get('scenario') or 'chat',
    }
    request_timeout = data.get('request_timeout_seconds')
    if isinstance(request_timeout, (int, float)) and not isinstance(request_timeout, bool):
        context['request_timeout_seconds'] = min(max(request_timeout, 1), 180)
    return context
