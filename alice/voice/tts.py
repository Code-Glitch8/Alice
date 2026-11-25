#!/usr/bin/env python3
"""
Text-to-Speech for ALICE using Piper TTS.
"""

import logging
import asyncio
import subprocess
from typing import Any, Optional, Dict

logger = logging.getLogger(__name__)


class PiperTTS:
    """Piper Text-to-Speech engine for ALICE."""

    def __init__(self, config: Any):
        self.config = config
        self.engine: str = config.voice.tts_engine
        self.voice: str = config.voice.tts_voice
        self.rate: int = config.voice.tts_rate
        self._process: Optional[subprocess.Popen] = None

    async def speak(self, text: str) -> None:
        """Convert text to speech and play audio."""
        if self._process and self._process.poll() is None:
            logger.warning("TTS already speaking")
            return

        logger.info(f"Speaking: {text[:50]}...")

        # Find piper model path
        model_path = self._find_model_path()

        if not model_path:
            logger.error("Piper model not found")
            return

        try:
            # Build piper command
            cmd = [
                "piper",
                "--model", model_path,
                "--output_device", str(self._get_default_speaker()),
            ]

            # Set rate if supported
            if hasattr(self, 'rate') and self.rate:
                # Piper may not support rate via CLI, adjust voice instead
                pass

            self._process = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE
            )

            # Write text to stdin and close
            if self._process.stdin:
                self._process.stdin.write(text.encode('utf-8'))
                self._process.stdin.close()

            # Wait for process to finish
            self._process.wait()

            self._process = None

        except Exception as e:
            logger.error(f"TTS error: {e}")
            self._process = None

    def _find_model_path(self) -> Optional[str]:
        """Find Piper model file."""
        # In production, search for .onnx models
        # For now, return None
        return None

    def _get_default_speaker(self) -> int:
        """Get default audio output device."""
        # In production, use sounddevice or similar
        return 0

    def get_voice_info(self) -> Dict[str, Any]:
        """Get available voice information."""
        return {
            "engine": self.engine,
            "voice": self.voice,
            "rate": self.rate,
        }


if __name__ == "__main__":
    import sys
    sys.path.insert(0, '.')
    from alice.core.config import Config

    config = Config.load()
    tts = PiperTTS(config)

    async def test():
        await tts.speak("ALICE is speaking test.")
        info = tts.get_voice_info()
        print(f"TTS voice info: {info}")

    import asyncio
    asyncio.run(test())