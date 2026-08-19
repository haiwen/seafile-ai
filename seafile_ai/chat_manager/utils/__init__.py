import json
import logging
import os
import re
from copy import deepcopy
from pathlib import Path

from seafile_ai.chat_manager.system_prompts import (
    CHAT_CORE_PROMPT,
    CHAT_CONTENT_GENERATION_RULES,
    CHAT_CONTENT_GENERATOR_TOOLS_EXAMPLES,
    CHAT_GLOBAL_TOOL_RULES,
    CHAT_LIST_FILES_TOOL_RULES,
    CHAT_LIST_FILES_METADATA_DISABLED_RULE,
    CHAT_OUTPUT_FORMAT_RULES,
    CHAT_SEARCH_POLICY,
    CHAT_SEARCH_REFERENCE_RULES,
    CHAT_SEARCH_TOOLS_EXAMPLES,
)
from seafile_ai.repo_metadata.constants import METADATA_TABLE
from seafile_ai.repo_metadata.metadata_server_api import MetadataServerAPI
from seafile_ai.repo_metadata.utils import get_metadata_by_path
from seafile_ai.utils import parse_file

logger = logging.getLogger(__name__)

REFERENCE_MARKER_RE = re.compile(r'\[Reference\s+(\d+)\]')
INTERNAL_REFERENCE_RE = re.compile(r'<reference_(\d+)>')
DOCUMENT_ATTACHMENTS_PROMPT = 'Here are some documents in Json format with title, URL or path, and content.\n\n'
ATTACHMENT_CONTENT_LIMIT = 6000
SUPPORTED_ATTACHMENT_SUFFIXES = {'.sdoc', '.md', '.markdown', '.docx', '.pdf', '.pptx'}
ATTACHMENT_METADATA_SERVER_API = MetadataServerAPI('seafile-ai')

def build_chat_tool_prompt(skip_tool_examples=False):
    tool_prompt_sections = [
        CHAT_GLOBAL_TOOL_RULES,
        CHAT_LIST_FILES_TOOL_RULES,
        CHAT_LIST_FILES_METADATA_DISABLED_RULE,
        CHAT_SEARCH_POLICY,
        CHAT_SEARCH_REFERENCE_RULES,
        CHAT_CONTENT_GENERATION_RULES,
    ]

    if not skip_tool_examples:
        tool_prompt_sections.append(CHAT_SEARCH_TOOLS_EXAMPLES)
        tool_prompt_sections.append(CHAT_CONTENT_GENERATOR_TOOLS_EXAMPLES)

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


def truncate_attachment_content(content, limit=ATTACHMENT_CONTENT_LIMIT):
    content = (content or '').strip()
    if len(content) <= limit:
        return content
    return content[:limit] + '...'


def enrich_attachments_with_content(attachments):
    results = []
    for attachment in attachments or []:
        if not isinstance(attachment, dict):
            continue

        next_attachment = deepcopy(attachment)
        content = next_attachment.get('content')
        if isinstance(content, str) and content.strip():
            next_attachment['content'] = truncate_attachment_content(content)
            results.append(next_attachment)
            continue

        repo_id = next_attachment.get('repo_id')
        path = next_attachment.get('path') or ''
        name = next_attachment.get('name') or os.path.basename(path)
        suffix = Path(name or path).suffix.lower()
        if not repo_id or not path or suffix not in SUPPORTED_ATTACHMENT_SUFFIXES:
            results.append(next_attachment)
            continue

        try:
            row = get_metadata_by_path(repo_id, path, ATTACHMENT_METADATA_SERVER_API)
            obj_id = row.get(METADATA_TABLE.columns.obj_id.name) if row else None
            if obj_id:
                parsed_content = parse_file(name or path, repo_id, obj_id)
                if parsed_content:
                    next_attachment['content'] = truncate_attachment_content(parsed_content)
        except Exception as error:
            logger.warning('parse attachment failed: %s', error)

        results.append(next_attachment)
    return results


def combine_attachments_to_message(attachments, message):
    if not attachments:
        return message
    attachments = enrich_attachments_with_content(attachments)
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
