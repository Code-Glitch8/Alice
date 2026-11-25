# ALICE Project Status — Verified Phase 1 Foundation

## Current status

The original scaffold contained several modules that looked complete in the summary but were placeholders or had mismatched interfaces. The current revision corrects the initial local-AI integration path. It does not claim the entire assistant is complete.

## Implemented in this revision

### LM Studio adapter
- Uses LM Studio's real local REST API, not simulated responses.
- Checks `GET /api/v1/models` for installed LLMs.
- Resolves the configured Qwen 3.5 4B model against actual model keys and display names.
- Loads through `POST /api/v1/models/load`.
- Unloads through `POST /api/v1/models/unload`.
- Sends chat requests through `POST /v1/chat/completions`.
- Supports server-sent-event text streaming.
- Reads tool-use capability from model metadata instead of assuming it.
- Provides actionable errors when the server is unavailable or the model cannot be selected.
- Can attempt `lms server start` if the CLI is available; otherwise instructs the user to start the server in LM Studio Developer.
- Does not terminate the LM Studio server on ALICE shutdown because another local application may be using it.

### Runtime manager
- Uses `asyncio.to_thread` for blocking local HTTP calls.
- Loads the model on demand when chat is requested.
- Tracks activity and unloads after the configured idle timeout.
- Cancels its idle monitor cleanly during shutdown.

### Configuration
- Defaults to Qwen 3.5 4B model matching, localhost port 1234, and a 4096-token context.
- Uses `D:\Alice` as the default ALICE data/config root on Windows.
- Supports `ALICE_HOME` and `ALICE_CONFIG` overrides.

### CLI
- `python -m alice.cli --check-ai` checks server connectivity and lists installed LLMs.
- `python -m alice.cli --chat` starts a real local interactive chat.
- `--model` can specify an exact LM Studio model key.

### Tests
- Unit/integration-contract tests use a local fake LM Studio HTTP server.
- Current test suite: 11 tests passing in the development container.
- Tests do not replace a real Windows + LM Studio + Qwen acceptance test.

## Not yet verified / not complete

- Real Qwen 3.5 4B model load on the HP Victus.
- Planner-to-tool-call loop and safe execution of model-requested tools.
- Real application launching and file operations through the natural-language planner.
- Visible Chrome automation using the user's browser session.
- Real STT, TTS, microphone capture, and wake-word detection.
- Dashboard Send button connected to the runtime.
- OMEN dedicated key interception on the exact laptop.
- Windows installer and end-user packaging.

## Next phase

1. Verify the LM Studio server and Qwen model from the target Windows laptop.
2. Add a typed tool-call result object rather than serializing tool calls into assistant text.
3. Connect Qwen tool definitions to the existing registered tool registry.
4. Add confirmation gates and result verification before claiming actions succeeded.
5. Connect the dashboard to the same runtime manager.
