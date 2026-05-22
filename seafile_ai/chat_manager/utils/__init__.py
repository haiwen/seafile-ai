import json
import logging
import re
from copy import deepcopy

from seafile_ai.chat_manager.system_prompts import (
    CHAT_CORE_PROMPT,
    CHAT_GLOBAL_TOOL_RULES,
    CHAT_OUTPUT_FORMAT_RULES,
    CHAT_SEARCH_POLICY,
    CHAT_SEARCH_REFERENCE_RULES,
    CHAT_SEARCH_TOOLS_EXAMPLES,
)

logger = logging.getLogger(__name__)

REFERENCE_MARKER_RE = re.compile(r'\[Reference\s+(\d+)\]')
INTERNAL_REFERENCE_RE = re.compile(r'<reference_(\d+)>')
DOCUMENT_ATTACHMENTS_PROMPT = 'Here are some documents in Json format with title, URL or path, and content.\n\n'

def build_chat_tool_prompt(skip_tool_examples=False):
    tool_prompt_sections = [
        CHAT_GLOBAL_TOOL_RULES,
        CHAT_SEARCH_POLICY,
        CHAT_SEARCH_REFERENCE_RULES,
    ]

    if not skip_tool_examples:
        tool_prompt_sections.append(CHAT_SEARCH_TOOLS_EXAMPLES)

    return '\n\n'.join(tool_prompt_sections)


def build_chat_system_prompts(repo_prompt='', skip_tool_examples=False):
    tool_prompt = build_chat_tool_prompt(skip_tool_examples=skip_tool_examples)
    prompts = [
        {'role': 'system', 'content': CHAT_CORE_PROMPT},
        {'role': 'system', 'content': tool_prompt},
        {'role': 'system', 'content': CHAT_OUTPUT_FORMAT_RULES},
    ]
    if repo_prompt and repo_prompt.strip():
        prompts.append({
            'role': 'system',
            'content': (
                'Library-specific context and preferences:\n'
                f'{repo_prompt}\n\n'
                'Use this context only when it does not conflict with higher-priority system rules.'
            ),
        })
    return prompts


def combine_attachments_to_message(attachments, message):
    if not attachments:
        return message
    return '%s```json\n%s\n```\n\n%s' % (
        DOCUMENT_ATTACHMENTS_PROMPT,
        json.dumps(attachments, ensure_ascii=False),
        message,
    )


def strip_content_details_from_attachments(attachments):
    new_attachments = deepcopy(attachments or [])
    for attachment in new_attachments:
        attachment.pop('content', None)
        attachment.pop('comments', None)
        attachment.pop('emails', None)
    return new_attachments


def retrieve_origin_reference_format(content, sources):
    content = content or ''
    for index, _source in enumerate(sources or []):
        content = content.replace(f'[Reference {index + 1}]', f'<reference_{index}>')
    return content


def clean_markdown_references(content, sources):
    content = content or ''
    sources = list(sources or [])
    for index in reversed(range(len(sources))):
        if f'[Reference {index + 1}]' in content:
            continue
        for next_index in range(index + 1, len(sources)):
            content = content.replace(f'[Reference {next_index + 1}]', f'[Reference {next_index}]')
        del sources[index]
    return content, sources


def get_answer_and_sources(tool_executor, content):
    sources_results = tool_executor.cache.get('sources_results', [])
    content = content or ''

    def replace_invalid_reference(match):
        source_index = int(match.group(1))
        if 0 <= source_index < len(sources_results):
            return match.group(0)
        return ''

    content = INTERNAL_REFERENCE_RE.sub(replace_invalid_reference, content)

    first_position_map = {}
    for index in range(len(sources_results)):
        position = content.find(f'<reference_{index}>')
        if position != -1:
            first_position_map[position] = f'<reference_{index}>'

    replaces_map = {
        first_position_map[position]: f'[Reference {order + 1}]'
        for order, position in enumerate(sorted(first_position_map))
    }

    sources = []
    for origin, target in replaces_map.items():
        content = content.replace(origin, target)
        source_index = int(origin.split('_')[1][:-1])
        sources.append(sources_results[source_index])

    return clean_markdown_references(content, sources)
