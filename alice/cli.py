#!/usr/bin/env python3
"""Command-line diagnostics and local chat entry point for ALICE."""
from __future__ import annotations

import argparse
import asyncio
import json
import sys

from alice.core.application import AliceApplication
from alice.core.config import Config


async def run_check(app: AliceApplication) -> int:
    ok = await app.initialize()
    print(json.dumps(app.get_status(), indent=2, ensure_ascii=False))
    if not ok:
        print("\nLM Studio is not reachable. In LM Studio press Ctrl+2, then turn on Start server.")
        print("Alternatively install/enable the `lms` CLI so ALICE can start the server itself.")
        print(f"Details: {app.ai_adapter.last_error}")
        return 2
    models = await asyncio.to_thread(app.ai_adapter.list_models)
    print("\nInstalled local LLMs:")
    for model in models:
        mark = " [loaded]" if model.get("loaded") else ""
        print(f" - {model['id']} ({model.get('quantization') or 'quantization unknown'}){mark}")
    return 0


async def _confirm_category_b_action(tool_name: str, description: str) -> bool:
    """Ask the local CLI user before a Category B desktop action."""
    prompt = (
        f"\nALICE is asking permission to: {description} "
        f"(tool: {tool_name}).\nAllow this action? [y/N] "
    )
    answer = await asyncio.to_thread(input, prompt)
    approved = answer.strip().lower() in {"y", "yes"}
    if not approved:
        print("Permission not granted. ALICE will not perform that action.")
    return approved


async def run_chat(app: AliceApplication, model: str | None) -> int:
    app.permission_confirmation_callback = _confirm_category_b_action
    if not await app.initialize():
        print(f"Could not connect to LM Studio: {app.ai_adapter.last_error}", file=sys.stderr)
        return 2
    if model:
        loaded = await app.runtime.load_model(model)
    else:
        loaded = await app.runtime.load_model()
    if not loaded:
        print(f"Could not load Qwen: {app.ai_adapter.last_error}", file=sys.stderr)
        return 3
    print(f"ALICE connected to {app.runtime.current_model}. Type /exit to quit.")
    print("Try: 'open notepad', 'search for pdf files', 'create folder test on desktop'")
    history = []
    try:
        while True:
            prompt = await asyncio.to_thread(input, "You> ")
            if prompt.strip().lower() in {"/exit", "/quit"}:
                break
            if not prompt.strip():
                continue
            history.append({"role": "user", "content": prompt})
            try:
                answer = await app.chat_with_tools(history)
            except Exception as exc:
                print(f"ALICE error: {exc}")
                history.pop()
                continue
            if not isinstance(answer, str) or not answer.strip():
                print("ALICE> [No text response was returned by LM Studio.]")
                continue
            print(f"ALICE> {answer}\n", flush=True)
            history.append({"role": "assistant", "content": answer})
    finally:
        await app.runtime.unload_model()
        await app.shutdown_async()
    return 0


async def run_intent(app: AliceApplication, intent: str) -> int:
    """Execute a single intent using the task planner."""
    app.permission_confirmation_callback = _confirm_category_b_action
    if not await app.initialize():
        print(f"Could not connect to LM Studio: {app.ai_adapter.last_error}", file=sys.stderr)
        return 2
    if not await app.runtime.load_model():
        print(f"Could not load model: {app.ai_adapter.last_error}", file=sys.stderr)
        return 3

    print(f"Executing intent: {intent}")
    result = await app.execute_intent(intent)
    print(json.dumps(result, indent=2))
    return 0


async def _run(args) -> int:
    config = Config.load(args.config)
    app = AliceApplication(config)
    try:
        if args.intent:
            return await run_intent(app, args.intent)
        if args.chat:
            return await run_chat(app, args.model)
        code = await run_check(app)
        if code != 0 or not args.model:
            return code
        if not await app.runtime.load_model(args.model):
            print("Model load failed:", app.ai_adapter.last_error)
            return 3
        print("Model load: success")
        return 0
    finally:
        await app.shutdown_async()


def main() -> None:
    parser = argparse.ArgumentParser(description="ALICE local AI runtime tools")
    parser.add_argument("--config", help="Path to ALICE config JSON")
    parser.add_argument("--check-ai", action="store_true", help="Check local LM Studio server and list installed models")
    parser.add_argument("--chat", action="store_true", help="Start an interactive local Qwen chat with tools")
    parser.add_argument("--intent", help="Execute a single intent (e.g., 'open notepad')")
    parser.add_argument("--model", help="Model key/name to load; defaults to configured Qwen 3.5 4B")
    args = parser.parse_args()
    raise SystemExit(asyncio.run(_run(args)))


if __name__ == "__main__":
    main()
