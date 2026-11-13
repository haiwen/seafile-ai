import json
from functools import lru_cache
from html import escape
from html.parser import HTMLParser
from pathlib import Path

from seafile_ai.chat_manager.utils.content_blocks import CONTENT_BLOCK_TAGS, parse_content_blocks


@lru_cache(maxsize=1)
def get_sdoc_specification():
    """Read the authoring specification once per process, independent of cwd."""
    return (Path(__file__).resolve().parents[1] / 'SDOC_SPECIFICATION.md').read_text(encoding='utf-8')


class SdocReferenceParser(HTMLParser):
    sdoc_create_uuid = None

    def handle_starttag(self, tag, attrs):
        identifiers = [value for key, value in attrs if key == 'sdoc_create_uuid']
        if tag == 'seafile-ai-seadoc' and len(identifiers) == 1:
            self.sdoc_create_uuid = identifiers[0]


def resolve_sdoc_results(answer, tool_executor):
    """Every consumer-visible SDoc must be rebuilt from the current tool cache."""
    cached_results = tool_executor.cache.get('sdoc_create_results', {})
    output = []
    authorized_ranges = set()
    length = 0
    for block in parse_content_blocks(answer, CONTENT_BLOCK_TAGS):
        if block['type'] != 'block' or block['tag'] != 'seafile-ai-seadoc':
            output.append(block['raw'])
            length += len(block['raw'])
            continue
        if not block['complete']:
            output.append('\u200b')
            length += 1
            continue
        parser = SdocReferenceParser()
        parser.feed('<seafile-ai-seadoc%s>' % block['attributes'])
        identifier = parser.sdoc_create_uuid
        cached = cached_results.get(identifier)
        if cached is None:
            # A non-Markdown boundary prevents joining the surrounding syntax.
            # The final parse below remains necessary: text edits are not tokens.
            output.append('\u200b')
            length += 1
            continue
        # Ignore model-supplied metadata, status, and body for every tag variant.
        attributes = ' '.join('%s="%s"' % (key, escape(value, quote=True)) for key, value in (
            ('sdoc_create_uuid', identifier), ('file_name', cached['file_name']),
            ('description', cached['description'])))
        body = json.dumps(cached['content'], ensure_ascii=False, allow_nan=False, separators=(',', ':'))
        body = body.replace('&', '\\u0026').replace('<', '\\u003c').replace('>', '\\u003e')
        expanded = '<seafile-ai-seadoc %s>\n%s\n</seafile-ai-seadoc>' % (attributes, body)
        output.append(expanded)
        authorized_ranges.add((length, length + len(expanded)))
        length += len(expanded)
    result = ''.join(output)
    position = 0
    for block in parse_content_blocks(result, CONTENT_BLOCK_TAGS):
        end = position + len(block['raw'])
        if (block.get('tag') == 'seafile-ai-seadoc' and block['complete'] and
                not block['self_closing'] and (position, end) not in authorized_ranges):
            # Fail closed rather than run another rewrite that can expose more
            # blocks. Provenance is an output range, not a UUID/body comparison.
            return escape(result, quote=False)
        position = end
    return result
