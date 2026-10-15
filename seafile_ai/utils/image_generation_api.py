"""Single-image Responses integration; no chat fallback or automatic retries."""
import base64
import binascii
import io
import json
import multiprocessing
from threading import Timer
import time
import warnings

import requests
from PIL import Image, UnidentifiedImageError

MAX_RESPONSE_BYTES = 24 * 1024 * 1024
MAX_IMAGE_BYTES = 16 * 1024 * 1024
MAX_IMAGE_PIXELS = 16 * 1024 * 1024
PROMPT_MAX_LENGTH = 2000
GENERATION_TIMEOUT = 180


class CoverGenerationError(Exception):
    def __init__(self, message, status=502):
        super().__init__(message)
        self.status = status


def _generate_image(connection, model_config, prompt):
    try:
        image = ImageGenerationAPI(model_config)._generate_cover(prompt)
        connection.send((image, None, None))
    except CoverGenerationError as error:
        connection.send((None, str(error), error.status))
    except Exception:
        connection.send((None, 'Image generation failed.', 502))
    finally:
        connection.close()


class ImageGenerationAPI:
    def __init__(self, model_config):
        self.model = model_config['model']
        self.url = model_config['url'].rstrip('/') + '/responses'
        self.key = model_config['key']

    def generate_cover(self, prompt):
        if not isinstance(prompt, str) or not 1 <= len(prompt.strip()) <= PROMPT_MAX_LENGTH:
            raise CoverGenerationError('Enter a description of up to 2000 characters.', 400)
        # A read timeout is an inactivity timeout, not a wall-clock deadline.
        # Isolate blocking DNS/TLS/reads so the caller can terminate them safely.
        context = multiprocessing.get_context('spawn')
        receiver, sender = context.Pipe(duplex=False)
        process = context.Process(target=_generate_image, args=(sender, {
            'model': self.model, 'url': self.url.rsplit('/responses', 1)[0], 'key': self.key,
        }, prompt))
        deadline = time.monotonic() + GENERATION_TIMEOUT
        watchdog = None
        try:
            process.start()
            sender.close()
            # Also interrupt a blocked recv if the child stalls mid-result.
            watchdog = Timer(max(0, deadline - time.monotonic()), process.kill)
            watchdog.daemon = True
            watchdog.start()
            if not receiver.poll(max(0, deadline - time.monotonic())):
                raise CoverGenerationError('Image generation timed out.', 504)
            image, error, status = receiver.recv()
            if time.monotonic() > deadline:
                raise CoverGenerationError('Image generation timed out.', 504)
            if error:
                raise CoverGenerationError(error, status)
            return image
        except (EOFError, OSError):
            if time.monotonic() >= deadline:
                raise CoverGenerationError('Image generation timed out.', 504) from None
            raise CoverGenerationError('Image generation failed.') from None
        finally:
            if watchdog is not None:
                watchdog.cancel()
                watchdog.join()
            sender.close()
            receiver.close()
            if process.pid is not None:
                if process.is_alive():
                    process.terminate()
                process.join(timeout=1)
                if process.is_alive():
                    process.kill()
                    process.join()
                process.close()

    def _generate_cover(self, prompt):
        body = {
            'model': self.model,
            'input': (
                'Generate exactly one decorative landscape cover image for a knowledge wiki. '
                'Keep the main subject near the center, with generous space for banner cropping. '
                'Do not include text, lettering, logos or watermarks. Subject description:\n'
                + prompt.strip()
            ),
            'tools': [{
                'type': 'image_generation', 'model': 'gpt-image-2',
                'quality': 'low', 'size': '1536x1024', 'output_format': 'png',
            }],
            'tool_choice': {'type': 'image_generation'},
            'store': False,
        }
        deadline = time.monotonic() + GENERATION_TIMEOUT
        try:
            # requests does not retry POST by default. Never retry an uncertain generation.
            with requests.post(
                self.url, json=body,
                headers={'Authorization': 'Bearer ' + self.key},
                timeout=(10, GENERATION_TIMEOUT), stream=True, allow_redirects=False,
            ) as response:
                if response.status_code != 200:
                    code = 429 if response.status_code == 429 else 502
                    raise CoverGenerationError('Image generation service is unavailable.', code)
                content = bytearray()
                for chunk in response.iter_content(64 * 1024):
                    if time.monotonic() > deadline:
                        raise CoverGenerationError('Image generation timed out.', 504)
                    content.extend(chunk)
                    if len(content) > MAX_RESPONSE_BYTES:
                        raise CoverGenerationError('Image generation response is too large.')
            data = json.loads(content)
        except requests.Timeout:
            raise CoverGenerationError('Image generation timed out.', 504) from None
        except (requests.RequestException, ValueError):
            raise CoverGenerationError('Image generation failed.') from None
        return self.decode_image(data)

    @staticmethod
    def decode_image(data):
        if not isinstance(data, dict) or data.get('status') != 'completed' or data.get('error'):
            raise CoverGenerationError('Image generation did not complete.')
        output = data.get('output')
        if not isinstance(output, list):
            raise CoverGenerationError('Invalid image generation result.')
        images = [item for item in output if isinstance(item, dict)
                  and item.get('type') == 'image_generation_call']
        if len(images) != 1 or images[0].get('status') != 'completed':
            raise CoverGenerationError('Expected one completed image.')
        encoded = images[0].get('result')
        if not isinstance(encoded, str) or not encoded or len(encoded) > MAX_RESPONSE_BYTES:
            raise CoverGenerationError('Invalid generated image.')
        try:
            content = base64.b64decode(encoded, validate=True)
            if len(content) > MAX_IMAGE_BYTES:
                raise CoverGenerationError('Generated image is too large.')
            with warnings.catch_warnings():
                warnings.simplefilter('error', Image.DecompressionBombWarning)
                with Image.open(io.BytesIO(content)) as image:
                    if image.format != 'PNG' or image.width * image.height > MAX_IMAGE_PIXELS:
                        raise CoverGenerationError('Unsupported generated image.')
                    image.verify()
                with Image.open(io.BytesIO(content)) as image:
                    image.load()
                    # Strip metadata, including possible provider prompt metadata.
                    clean = Image.new('RGB', image.size)
                    clean.paste(image.convert('RGB'))
                    result = io.BytesIO()
                    clean.save(result, format='PNG')
            content = result.getvalue()
            if len(content) > MAX_IMAGE_BYTES:
                raise CoverGenerationError('Generated image is too large.')
            return content
        except (binascii.Error, ValueError, OSError, UnidentifiedImageError,
                Image.DecompressionBombError, Image.DecompressionBombWarning):
            raise CoverGenerationError('Invalid generated image.') from None
