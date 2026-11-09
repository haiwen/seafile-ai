import json
from html import escape
from html.parser import HTMLParser

from seafile_ai.chat_manager.utils.content_blocks import CONTENT_BLOCK_TAGS, parse_content_blocks


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
    for block in parse_content_blocks(answer, CONTENT_BLOCK_TAGS):
        if block['type'] != 'block' or block['tag'] != 'seafile-ai-seadoc':
            output.append(block['raw'])
            continue
        if not block['complete']:
            continue
        parser = SdocReferenceParser()
        parser.feed('<seafile-ai-seadoc%s>' % block['attributes'])
        identifier = parser.sdoc_create_uuid
        cached = cached_results.get(identifier)
        if cached is None:
            continue
        # Ignore model-supplied metadata, status, and body for every tag variant.
        attributes = ' '.join('%s="%s"' % (key, escape(value, quote=True)) for key, value in (
            ('sdoc_create_uuid', identifier), ('file_name', cached['file_name']),
            ('description', cached['description'])))
        body = json.dumps(cached['content'], ensure_ascii=False, allow_nan=False, separators=(',', ':'))
        body = body.replace('&', '\\u0026').replace('<', '\\u003c').replace('>', '\\u003e')
        output.append('<seafile-ai-seadoc %s>\n%s\n</seafile-ai-seadoc>' % (attributes, body))
    return ''.join(output)
