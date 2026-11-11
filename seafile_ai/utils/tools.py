import inspect
import json
from copy import deepcopy
from difflib import get_close_matches

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError

from seafile_ai.utils import remove_sources_content_and_snippets
from seafile_ai.utils.thought_process_recorder import ThoughtProcessRecorder


def filter_tool_calls_content(tool_name, results):
    if tool_name == 'read_files':
        return remove_sources_content_and_snippets(deepcopy(results))
    return results


class BasicTool:
    tool = {}

    def register(self, tool_executor, **constant_kwargs):
        tool_executor.register(self.execute, self.tool, **constant_kwargs)

    def execute(self, *args, **kwargs):
        raise NotImplementedError()


class InvalidToolException(Exception):
    pass


class InvalidToolArgumentsException(InvalidToolException):
    """Raised when model-provided arguments do not match a tool's schema."""

    def __init__(
        self,
        tool_name,
        missing_fields=None,
        unexpected_fields=None,
        suggestions=None,
        schema_error=None,
    ):
        self.tool_name = tool_name
        self.missing_fields = missing_fields or []
        self.unexpected_fields = unexpected_fields or []
        self.suggestions = suggestions or {}
        self.schema_error = schema_error

        details = []
        if self.schema_error:
            details.append(self.schema_error)
        if self.missing_fields:
            details.append(f"missing required fields: {', '.join(self.missing_fields)}")
        if self.unexpected_fields:
            unexpected = []
            for field in self.unexpected_fields:
                suggestion = self.suggestions.get(field)
                unexpected.append(f"{field} (did you mean {suggestion}?)" if suggestion else field)
            details.append(f"unexpected fields: {', '.join(unexpected)}")

        message = f"Invalid arguments for tool {tool_name!r}: {'; '.join(details)}. "
        message += 'Call the tool again with arguments that conform to the registered JSON Schema.'
        super().__init__(message)


class BasicToolExecutor:
    def __init__(self):
        self.cache = {}
        self.thought_process = ThoughtProcessRecorder()
        self.clean()

    def register(self, func, tool_info, **constant_kwargs):
        raise NotImplementedError()

    def clean(self, *args, **kwargs):
        raise NotImplementedError()


class OpenAIToolExecutor(BasicToolExecutor):
    tools = {}

    def clean(self):
        self.tools = {}

    def register(self, func, tool_info, **constant_kwargs):
        name = tool_info.get('name')
        if not name:
            raise InvalidToolException(tool_info)
        tool_info = dict(tool_info)
        tool_info.setdefault('strict', False)
        self.tools[name] = {
            'func': func,
            'constant_kwargs': constant_kwargs,
            'tool_info': tool_info,
        }

    def get(self):
        return [tool['tool_info'] for tool in self.tools.values()]

    def validate_arguments(self, name, params):
        """Validate model arguments against the complete registered JSON Schema."""
        parameters = self.tools[name]['tool_info'].get('parameters') or {}
        properties = parameters.get('properties')
        if isinstance(properties, dict):
            valid_fields = set(properties)
            required_fields = parameters.get('required') or []
            missing_fields = sorted(field for field in required_fields if field not in params)
            unexpected_fields = sorted(field for field in params if field not in valid_fields)
            if missing_fields or unexpected_fields:
                suggestions = {}
                for field in unexpected_fields:
                    matches = get_close_matches(field, sorted(valid_fields), n=1, cutoff=0.75)
                    if matches:
                        suggestions[field] = matches[0]
                raise InvalidToolArgumentsException(
                    name,
                    missing_fields=missing_fields,
                    unexpected_fields=unexpected_fields,
                    suggestions=suggestions,
                )

        try:
            validator = Draft202012Validator(parameters)
        except SchemaError as error:
            raise InvalidToolException(
                f'Invalid schema registered for tool {name!r}: {error.message}'
            ) from error

        error = next(validator.iter_errors(params), None)
        if error is None:
            return

        path = '$'
        for component in error.absolute_path:
            path += f'[{component}]' if isinstance(component, int) else f'.{component}'

        raise InvalidToolArgumentsException(
            name,
            schema_error=f'{path}: {error.message}',
        )

    def execute(self, tool_call, call_back=lambda *args, **kwargs: None):
        name = tool_call['name']
        raw_arguments = tool_call.get('arguments')
        if isinstance(raw_arguments, str):
            params = json.loads(raw_arguments or '{}')
        else:
            params = raw_arguments or {}
        if not isinstance(params, dict):
            raise InvalidToolException(tool_call)
        self.validate_arguments(name, params)

        constant_kwargs = self.tools[name]['constant_kwargs']
        available_params = inspect.signature(self.tools[name]['func']).parameters
        params.update({
            key: value
            for key, value in constant_kwargs.items()
            if key in available_params and key not in params
        })

        if 'tool_executor' in available_params and 'tool_executor' not in params:
            params['tool_executor'] = self
        if 'call_back' in available_params and 'call_back' not in params:
            params['call_back'] = call_back

        return self.tools[name]['func'](**params)
