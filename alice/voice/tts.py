#!/usr/bin/env python3
"""Local neural speech synthesis for ALICE.

Kokoro is the preferred voice. Piper is the offline fallback when its voice pack
is installed, and Windows SAPI is the final compatibility fallback.
Kokoro model assets are downloaded once into ALICE_HOME/voice/models.
"""
from __future__ import annotations

import asyncio
import logging
import os
import subprocess
import tempfile
import threading
import wave
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.request import Request, urlopen

import numpy as np

logger = logging.getLogger(__name__)


class LocalTTS:
    """Kokoro-first local TTS with Piper and Windows SAPI fallbacks."""

    KOKORO_MODEL_URL = (
        "https://github.com/thewh1teagle/kokoro-onnx/releases/download/"
        "model-files-v1.1/kokoro-v1.0.onnx"
    )
    KOKORO_VOICES_URL = (
        "https://github.com/thewh1teagle/kokoro-onnx/releases/download/"
        "model-files-v1.1/voices-v1.0.bin"
    )

    def __init__(self, config: Any):
        self.config = config
        self.engine = "kokoro"
        self.voice = str(getattr(config.voice, "tts_voice", "af_heart") or "af_heart")
        self.rate = int(getattr(config.voice, "tts_rate", 150))
        self._kokoro = None
        self._kokoro_lock = threading.Lock()
        self._speaking_lock = threading.Lock()
        self._speaking = False
        self._sapi_engine = None
        self._process: Optional[subprocess.Popen] = None
        self.last_error: Optional[str] = None

    async def speak(self, text: str) -> None:
        text = str(text or "").strip()
        if not text:
            return
        with self._speaking_lock:
            if self._speaking:
                logger.warning("TTS is already speaking; ignoring overlapping request")
                return
            self._speaking = True
        try:
            await asyncio.to_thread(self._speak_sync, text)
        finally:
            with self._speaking_lock:
                self._speaking = False

    def _speak_sync(self, text: str) -> None:
        failures: list[str] = []
        for engine_name, engine in (
            ("Kokoro", self._speak_kokoro),
            ("Piper", self._speak_piper_if_available),
            ("Windows SAPI", self._speak_sapi),
        ):
            try:
                engine(text)
                self.engine = engine_name.lower().replace(" ", "_")
                self.last_error = None
                return
            except Exception as exc:
                failures.append(f"{engine_name}: {exc}")
                logger.warning("%s TTS unavailable: %s", engine_name, exc, exc_info=True)

        self.last_error = "All local speech engines failed. " + " | ".join(failures)
        raise RuntimeError(self.last_error)

    @property
    def model_dir(self) -> Path:
        path = Path(self.config.data_dir).expanduser() / "voice" / "models"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _download_asset(self, url: str, destination: Path, minimum_size: int) -> Path:
        if destination.is_file() and destination.stat().st_size >= minimum_size:
            return destination

        temporary = destination.with_suffix(destination.suffix + ".part")
        request = Request(url, headers={"User-Agent": "ALICE-Desktop/1.0"})
        logger.info("Downloading local speech model asset: %s", destination.name)
        try:
            with urlopen(request, timeout=120) as response, temporary.open("wb") as output:
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    output.write(chunk)
            if temporary.stat().st_size < minimum_size:
                raise RuntimeError(
                    f"Downloaded {destination.name} is incomplete "
                    f"({temporary.stat().st_size} bytes)."
                )
            os.replace(temporary, destination)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise
        return destination

    def _kokoro_paths(self) -> tuple[Path, Path]:
        model_path = self.model_dir / "kokoro-v1.0.onnx"
        voices_path = self.model_dir / "voices-v1.0.bin"
        # The release contains a full-precision model plus a compact voice bank.
        # Download at first use rather than inflating the Windows installer.
        self._download_asset(self.KOKORO_MODEL_URL, model_path, 50_000_000)
        self._download_asset(self.KOKORO_VOICES_URL, voices_path, 1_000_000)
        return model_path, voices_path

    def _get_kokoro(self):
        with self._kokoro_lock:
            if self._kokoro is not None:
                return self._kokoro
            try:
                from kokoro_onnx import Kokoro
            except ImportError as exc:
                raise RuntimeError(
                    "Kokoro is not installed. Reinstall ALICE with kokoro-onnx."
                ) from exc

            model_path, voices_path = self._kokoro_paths()
            self._kokoro = Kokoro(str(model_path), str(voices_path))
            logger.info("Kokoro neural TTS model loaded")
            return self._kokoro

    def _speak_kokoro(self, text: str) -> None:
        import sounddevice as sd

        kokoro = self._get_kokoro()
        voice_name = str(
            getattr(self.config.voice, "tts_voice", "af_heart") or "af_heart"
        )
        language = str(
            getattr(self.config.voice, "tts_language", "en-us") or "en-us"
        )
        available = kokoro.get_voices()
        if voice_name not in available:
            raise ValueError(
                f"Kokoro voice '{voice_name}' is unavailable. "
                f"Available voices include: {', '.join(available[:8])}"
            )

        speed = max(0.5, min(2.0, float(self.config.voice.tts_rate) / 150.0))
        audio, sample_rate = kokoro.create(
            text,
            voice=voice_name,
            speed=speed,
            lang=language,
        )
        samples = np.asarray(audio, dtype=np.float32).reshape(-1)
        if samples.size == 0:
            raise RuntimeError("Kokoro returned empty audio.")
        # Keep the samples in memory; no temporary audio files are created.
        sd.play(samples, int(sample_rate), blocking=True)

    def _find_piper_model(self) -> Optional[Path]:
        configured = str(getattr(self.config.voice, "tts_model_path", "") or "").strip()
        candidates: list[Path] = []
        if configured:
            candidates.append(Path(os.path.expandvars(os.path.expanduser(configured))))
        for folder in (
            self.model_dir,
            Path(self.config.data_dir).expanduser() / "voice" / "voices",
            Path(self.config.data_dir).expanduser() / "voices",
        ):
            if folder.exists():
                candidates.extend(sorted(folder.glob("*.onnx")))

        for candidate in candidates:
            if candidate.is_file() and candidate.suffix.lower() == ".onnx":
                metadata = candidate.with_suffix(candidate.suffix + ".json")
                if metadata.is_file():
                    return candidate
                logger.warning("Ignoring Piper model without metadata sidecar: %s", candidate)
        return None

    def _speak_piper_if_available(self, text: str) -> None:
        model_path = self._find_piper_model()
        if model_path is None:
            raise RuntimeError(
                "No Piper voice is installed. Add a Piper .onnx model and its "
                "matching .onnx.json file under ALICE/voice/models."
            )
        self._speak_piper(text, model_path)

    def _speak_piper(self, text: str, model_path: Path) -> None:
        import sounddevice as sd
        from piper import PiperVoice

        voice = PiperVoice.load(str(model_path))
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
        try:
            import pyttsx3
        except ImportError as exc:
            raise RuntimeError("Windows SAPI fallback is unavailable (pyttsx3 missing).") from exc

        pythoncom = None
        engine = None
        try:
            if os.name == "nt":
                import pythoncom as _pythoncom
                pythoncom = _pythoncom
                pythoncom.CoInitialize()
            engine = pyttsx3.init()
            self._sapi_engine = engine
            engine.setProperty("rate", self.rate)
            engine.say(text)
            engine.runAndWait()
        finally:
            if engine is not None:
                try:
                    engine.stop()
                except Exception:
                    logger.debug("Could not dispose SAPI engine", exc_info=True)
            self._sapi_engine = None
            if pythoncom is not None:
                pythoncom.CoUninitialize()

    def stop(self) -> None:
        try:
            import sounddevice as sd
            sd.stop()
        except Exception:
            logger.debug("Could not stop sounddevice playback", exc_info=True)
        if self._sapi_engine is not None:
            try:
                self._sapi_engine.stop()
            except Exception:
                logger.debug("Could not stop Windows SAPI playback", exc_info=True)
        if self._process and self._process.poll() is None:
            self._process.terminate()
        self._process = None

    def get_voice_info(self) -> Dict[str, Any]:
        return {
            "engine": self.engine,
            "voice": str(getattr(self.config.voice, "tts_voice", "af_heart")),
            "language": str(getattr(self.config.voice, "tts_language", "en-us")),
            "rate": self.rate,
            "kokoro_model": str(self.model_dir / "kokoro-v1.0.onnx"),
            "kokoro_ready": self._kokoro is not None,
            "piper_model": str(self._find_piper_model() or ""),
            "fallback": "Piper, then Windows SAPI",
            "last_error": self.last_error,
        }


# Backwards-compatible import name used by older ALICE code.
PiperTTS = LocalTTS
