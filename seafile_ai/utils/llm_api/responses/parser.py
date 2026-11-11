from dataclasses import dataclass, field

from seafile_ai.utils.llm_api.responses.constants import STREAM_TEXT_DELTA, STREAM_COMPLETED


@dataclass
class ResponsesResult:
    content: str = ''
    tool_calls: list = field(default_factory=list)
    output: list = field(default_factory=list)
    usage: dict = field(default_factory=dict)


class ResponsesParser:
    @staticmethod
    def parse_output(response):
        if not isinstance(response, dict):
            response = response.model_dump(exclude_none=True)
        status = response.get('status')
        error = response.get('error')
        incomplete_details = response.get('incomplete_details')
        if status != 'completed' or error is not None or incomplete_details is not None:
            raise RuntimeError(
                f'Responses API response error: status={status}, error={error}, '
                f'incomplete_details={incomplete_details}'
            )
        output = response.get('output') or []
        content = ''.join(
            part.get('text') or ''
            for item in output if item.get('type') == 'message'
            for part in item.get('content') or []
        )
        usage = response.get('usage') or {}
        return ResponsesResult(
            content=content or response.get('output_text') or '',
            tool_calls=[item for item in output if item.get('type') == 'function_call'],
            output=output,
            usage={key: usage[key] for key in ('input_tokens', 'output_tokens', 'total_tokens') if key in usage},
        )

    @staticmethod
    def iter_stream(events):
        for event in events:
            if not isinstance(event, dict):
                event = event.model_dump(exclude_none=True)
            event_type = event.get('type')
            if event_type == 'response.output_text.delta':
                if event.get('delta'):
                    yield STREAM_TEXT_DELTA, event['delta']
            elif event_type == 'response.completed':
                yield STREAM_COMPLETED, ResponsesParser.parse_output(event['response'])
                return
            elif event_type in ('error', 'response.failed', 'response.incomplete'):
                error = event.get('error') or (event.get('response') or {}).get('error') or event_type
                raise RuntimeError(f'Responses API stream error: {error}')
        raise RuntimeError('Responses API stream ended before completion')
