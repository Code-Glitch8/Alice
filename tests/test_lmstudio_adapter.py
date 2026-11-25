"""Integration-contract tests against a tiny fake LM Studio HTTP server.

These tests validate ALICE's HTTP/API wiring without requiring a downloaded
model, Windows, or a live LM Studio installation.
"""
import asyncio
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from alice.ai.lmstudio_adapter import LMStudioAdapter
from alice.ai.runtime_manager import RuntimeManager
from alice.core.config import Config


class FakeLMStudioHandler(BaseHTTPRequestHandler):
    loaded = False
    last_chat = None

    def log_message(self, *_args):
        pass

    def _send(self, status, body):
        raw = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        if self.path == "/api/v1/models":
            instances = [{"id": "qwen35-instance", "config": {"context_length": 4096}}] if self.loaded else []
            self._send(200, {"models": [{
                "type": "llm",
                "key": "qwen/qwen3.5-4b-q4_k_m",
                "display_name": "Qwen 3.5 4B Q4_K_M",
                "size_bytes": 2900000000,
                "params_string": "4B",
                "format": "gguf",
                "quantization": {"name": "Q4_K_M"},
                "loaded_instances": instances,
                "capabilities": {"trained_for_tool_use": True},
            }]})
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        body = json.loads(self.rfile.read(length) or b"{}")
        if self.path == "/api/v1/models/load":
            FakeLMStudioHandler.loaded = True
            self._send(200, {"status": "loaded", "instance_id": "qwen35-instance", "load_time_seconds": 0.01})
        elif self.path == "/api/v1/models/unload":
            FakeLMStudioHandler.loaded = False
            self._send(200, {"instance_id": body.get("instance_id")})
        elif self.path == "/v1/chat/completions":
            FakeLMStudioHandler.last_chat = body
            self._send(200, {"choices": [{"message": {"role": "assistant", "content": "Hello from fake Qwen."}}]})
        else:
            self._send(404, {"error": "not found"})


def test_real_http_adapter_lifecycle_and_chat():
    FakeLMStudioHandler.loaded = False
    server = ThreadingHTTPServer(("127.0.0.1", 0), FakeLMStudioHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        config = Config()
        config.ai.base_url = f"http://127.0.0.1:{server.server_port}"
        config.ai.auto_start_server = False
        config.ai.model_name = "qwen3.5-4b"
        adapter = LMStudioAdapter(config)
        manager = RuntimeManager(adapter, config)

        async def exercise():
            assert await manager.start() is True
            assert await manager.load_model() is True
            answer = await manager.chat([{"role": "user", "content": "Say hello"}])
            assert answer == "Hello from fake Qwen."
            assert FakeLMStudioHandler.last_chat["model"] == "qwen/qwen3.5-4b-q4_k_m"
            assert await manager.unload_model() is True
            assert FakeLMStudioHandler.loaded is False
            await manager.stop()

        asyncio.run(exercise())
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_chat_normalizes_text_content_blocks():
    config = Config()
    adapter = LMStudioAdapter(config)
    adapter.model_loaded = True
    adapter.current_model = "qwen-test"
    adapter._request = lambda *_args, **_kwargs: {
        "choices": [{"message": {"role": "assistant", "content": [
            {"type": "text", "text": "Hello "},
            {"type": "output_text", "text": "from Qwen."},
        ]}}]
    }
    assert adapter.chat([{"role": "user", "content": "Say hello"}]) == "Hello \nfrom Qwen."


def test_chat_raises_diagnostic_instead_of_returning_blank():
    from alice.ai.lmstudio_adapter import LMStudioError

    config = Config()
    adapter = LMStudioAdapter(config)
    adapter.model_loaded = True
    adapter.current_model = "qwen-test"
    adapter._request = lambda *_args, **_kwargs: {
        "choices": [{"finish_reason": "stop", "message": {
            "role": "assistant", "content": None, "reasoning_content": "internal field"
        }}]
    }
    try:
        adapter.chat([{"role": "user", "content": "Say hello"}])
    except LMStudioError as exc:
        assert "empty user-facing answer" in str(exc)
        assert "reasoning_content" in str(exc)
    else:
        raise AssertionError("Expected an informative error for an empty response")


def test_chat_short_factual_question():
    """Test 2: Short factual question."""
    config = Config()
    adapter = LMStudioAdapter(config)
    adapter.model_loaded = True
    adapter.current_model = "qwen-test"
    adapter._request = lambda *_args, **_kwargs: {
        "choices": [{"finish_reason": "stop", "message": {
            "role": "assistant", "content": "Paris is the capital of France."
        }}]
    }
    answer = adapter.chat([{"role": "user", "content": "What is the capital of France?"}])
    assert answer == "Paris is the capital of France."


def test_chat_multi_sentence_explanation():
    """Test 3: Multi-sentence explanation."""
    config = Config()
    adapter = LMStudioAdapter(config)
    adapter.model_loaded = True
    adapter.current_model = "qwen-test"
    adapter._request = lambda *_args, **_kwargs: {
        "choices": [{"finish_reason": "stop", "message": {
            "role": "assistant", "content": "The sky appears blue because of Rayleigh scattering. "
            "Sunlight contains all colors, but blue light is scattered more by the atmosphere."
        }}]
    }
    answer = adapter.chat([{"role": "user", "content": "Why is the sky blue?"}])
    assert "Rayleigh scattering" in answer
    assert "blue light" in answer
    assert len(answer) > 50


def test_chat_reasoning_intensive():
    """Test 4: Reasoning-intensive question with reasoning_content (should not be exposed)."""
    config = Config()
    adapter = LMStudioAdapter(config)
    adapter.model_loaded = True
    adapter.current_model = "qwen-test"
    adapter._request = lambda *_args, **_kwargs: {
        "choices": [{"finish_reason": "stop", "message": {
            "role": "assistant",
            "content": "Let me think... 2 + 2 = 4.",
            "reasoning_content": "The user is asking for basic arithmetic. I should compute 2 + 2 which equals 4."
        }}]
    }
    answer = adapter.chat([{"role": "user", "content": "What is 2 + 2? Show your reasoning."}])
    # reasoning_content should NOT be in the user-facing answer
    assert "reasoning_content" not in answer
    assert "internal" not in answer.lower()
    assert "4" in answer


def test_chat_truncated_response():
    """Test 6: Truncated response (finish_reason='length') with retry."""
    from alice.ai.lmstudio_adapter import LMStudioError, TruncatedResponseError

    config = Config()
    adapter = LMStudioAdapter(config)
    adapter.model_loaded = True
    adapter.current_model = "qwen-test"

    call_count = [0]

    def mock_request(*_args, **_kwargs):
        call_count[0] += 1
        if call_count[0] == 1:
            # First call: truncated
            return {
                "choices": [{
                    "finish_reason": "length",
                    "message": {"role": "assistant", "content": "This is a very long response that gets cut off because"}
                }]
            }
        else:
            # Second call (retry): success with concise answer
            return {
                "choices": [{
                    "finish_reason": "stop",
                    "message": {"role": "assistant", "content": "Concise answer."}
                }]
            }

    adapter._request = mock_request
    answer = adapter.chat([{"role": "user", "content": "Write a very long essay about everything."}])
    assert answer == "Concise answer."
    assert call_count[0] == 2  # Verify retry happened


def test_chat_truncated_response_retry_fails():
    """Test 6b: Truncated response that fails even after retry."""
    from alice.ai.lmstudio_adapter import LMStudioError, TruncatedResponseError

    config = Config()
    adapter = LMStudioAdapter(config)
    adapter.model_loaded = True
    adapter.current_model = "qwen-test"

    call_count = [0]

    def mock_request(*_args, **_kwargs):
        call_count[0] += 1
        return {
            "choices": [{
                "finish_reason": "length",
                "message": {"role": "assistant", "content": "Still truncated"}
            }]
        }

    adapter._request = mock_request
    try:
        adapter.chat([{"role": "user", "content": "Write a very long essay."}])
    except LMStudioError as exc:
        assert "truncated after retry" in str(exc).lower() or "truncated" in str(exc).lower()
    else:
        raise AssertionError("Expected error for truncated response after retry")


def test_chat_tool_call_response():
    """Test 7: Tool-call response should be preserved for ALICE's tool execution."""
    config = Config()
    adapter = LMStudioAdapter(config)
    adapter.model_loaded = True
    adapter.current_model = "qwen-test"
    adapter._request = lambda *_args, **_kwargs: {
        "choices": [{
            "finish_reason": "tool_calls",
            "message": {
                "role": "assistant",
                "content": None,
                "tool_calls": [{
                    "id": "call_123",
                    "type": "function",
                    "function": {"name": "get_weather", "arguments": '{"city": "Paris"}'}
                }]
            }
        }]
    }
    answer = adapter.chat([{"role": "user", "content": "What's the weather in Paris?"}])
    # Tool calls should be preserved as JSON
    import json
    parsed = json.loads(answer)
    assert "tool_calls" in parsed
    assert len(parsed["tool_calls"]) == 1
    assert parsed["tool_calls"][0]["function"]["name"] == "get_weather"
    assert parsed["tool_calls"][0]["function"]["arguments"] == '{"city": "Paris"}'
