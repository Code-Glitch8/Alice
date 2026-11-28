#!/usr/bin/env python3
"""Local Piper TTS with Windows SAPI fallback."""
from __future__ import annotations

import asyncio
import logging
import os
import subprocess
import tempfile
import wave
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class PiperTTS:
    """Speak locally using a Piper voice when installed, otherwise Windows SAPI."""

    def __init__(self, config: Any):
        self.config = config
        self.engine = getattr(config.voice, "tts_engine", "piper")
        self.voice = getattr(config.voice, "tts_voice", "default")
        self.rate = int(getattr(config.voice, "tts_rate", 150))
        self._process: Optional[subprocess.Popen] = None
        self._sapi_engine = None
        self._speaking = False

    async def speak(self, text: str) -> None:
        text = str(text or "").strip()
        if not text:
            return
        if self._speaking:
            logger.warning("TTS is already speaking")
            return
        self._speaking = True
        try:
            await asyncio.to_thread(self._speak_sync, text)
        finally:
            self._speaking = False

    def _speak_sync(self, text: str) -> None:
        model_path = self._find_model_path()
        if model_path:
            try:
                self._speak_piper(text, model_path)
                return
            except Exception:
                logger.exception("Piper playback failed; using Windows speech fallback")
        self._speak_sapi(text)

    def _find_model_path(self) -> Optional[str]:
        """Find an explicitly configured or locally installed Piper ONNX voice."""
        configured = getattr(self.config.voice, "tts_model_path", "")
        candidates = []
        if configured:
            candidates.append(Path(os.path.expandvars(os.path.expanduser(configured))))
        root = Path(self.config.data_dir).expanduser()
        for folder in (root / "voice" / "models", root / "voice" / "voices", root / "voices"):
            if folder.exists():
                candidates.extend(sorted(folder.glob("*.onnx")))
        for candidate in candidates:
            if candidate.is_file() and candidate.suffix.lower() == ".onnx":
                return str(candidate)
        return None

    def _speak_piper(self, text: str, model_path: str) -> None:
        """Synthesize through Piper's Python API and play through the default output."""
        from piper import PiperVoice
        import sounddevice as sd
        import numpy as np

        voice = PiperVoice.load(model_path)
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as handle:
            wav_path = handle.name
        try:
            with wave.open(wav_path, "wb") as output:
                voice.synthesize_wav(text, output)
            with wave.open(wav_path, "rb") as source:
                channels = source.getnchannels()
                rate = source.getframerate()
                width = source.getsampwidth()
                frames = source.readframes(source.getnframes())
            if width == 2:
                audio = np.frombuffer(frames, dtype=np.int16)
            elif width == 4:
                audio = np.frombuffer(frames, dtype=np.int32)
            else:
                raise RuntimeError(f"Unsupported Piper sample width: {width}")
            if channels > 1:
                audio = audio.reshape(-1, channels)
            sd.play(audio, rate, blocking=True)
        finally:
            try:
                os.unlink(wav_path)
            except OSError:
                pass

    def _speak_sapi(self, text: str) -> None:
        """Use the Windows built-in speech engine; no downloaded voice model needed."""
        try:
            import pyttsx3
        except ImportError as exc:
            raise RuntimeError(
                "No Piper voice model is installed and pyttsx3 is unavailable."
            ) from exc
        if self._sapi_engine is None:
            self._sapi_engine = pyttsx3.init()
            self._sapi_engine.setProperty("rate", self.rate)
        self._sapi_engine.say(text)
        self._sapi_engine.runAndWait()

    def stop(self) -> None:
        try:
            import sounddevice as sd
            sd.stop()
        except Exception:
            pass
        if self._sapi_engine is not None:
            try:
                self._sapi_engine.stop()
            except Exception:
                logger.debug("Could not stop SAPI playback", exc_info=True)
        if self._process and self._process.poll() is None:
            self._process.terminate()
        self._process = None
        self._speaking = False

    def get_voice_info(self) -> Dict[str, Any]:
        return {
            "engine": self.engine,
            "voice": self.voice,
            "rate": self.rate,
            "model_path": self._find_model_path(),
            "fallback": "Windows SAPI",
        }
