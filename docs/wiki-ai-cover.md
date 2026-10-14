# Wiki AI cover configuration

Cover generation reuses the existing proxy through its OpenAI-compatible
Responses endpoint. It does not use Chat Completions or track image costs locally.

LiteLLM 1.83.14 Responses was checked against a local mock HTTP server: it
preserves the image tool options and result. The integration deliberately uses
the existing `requests` dependency instead, to bound the raw JSON response before
SDK parsing, disable redirects and avoid SDK-level retries. No external generation
was made during this compatibility test; live proxy/landscape verification remains
required.

Add an authorized GPT model to `global.LLM_MODELS` in your deployment YAML,
using the existing proxy URL ending in `/v1` and your existing server-side key.
Set `global.AI_COVER_MODEL: gpt-6.1-sol` to select that model explicitly.
Keep the existing default chat model unchanged. Never commit credentials.

The proxy must support `POST /v1/responses` with the built-in
`image_generation` tool and `gpt-image-2`. Missing/invalid task selection disables
cover generation without falling back to another model. Restart seafile-ai after
changing configuration.

The internal `/api/v1/generate-cover-image/` endpoint requires a service JWT with
an expiration. GET reports availability without generating an image. POST takes
`{"prompt": "your description"}` and returns one validated PNG.

Generation requests use landscape 1536x1024, low quality, and a 180-second
upstream read timeout. Seahub allows 195 seconds. Configure the deployment's web
proxy timeouts to accommodate this synchronous operation, and validate latency,
landscape output and impact on other AI requests before rollout. A successful
square-image test alone does not establish landscape support or acceptable latency.
There is no automatic POST retry; a timeout may still have generated an image.

No database migration, worker, queue or persistent candidate storage is added.
Images remain in the browser until explicitly uploaded and selected as a cover.
