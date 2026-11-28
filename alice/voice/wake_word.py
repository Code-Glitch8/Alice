#!/usr/bin/env python3
"""Offline wake-phrase detector.

This uses the bundled Faster-Whisper dependency with a small local model. It is
less power-efficient than a purpose-trained wake-word model, but it supports a
user-configured phrase such as "alice" without a cloud service or training step.
"""
from __future__ import annotations

import asyncio
import logging
import queue
import re
import threading
from pathlib import Path
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


class WakeWordDetector:
    """Listen locally for a configured phrase and invoke a callback once detected."""

    def __init__(self, config: Any):
        self.config = config
        self.listening = False
        self.wake_word = str(getattr(config.voice, "wake_word", "alice") or "alice")
        self._callback: Optional[Callable] = None
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._audio_queue: queue.Queue = queue.Queue(maxsize=80)
        self._model = None
        self._model_lock = threading.Lock()
        self.last_error: str | None = None
        self._stream = None

    def set_callback(self, callback: Callable) -> None:
        self._callback = callback

    def _get_model(self):
        with self._model_lock:
            if self._model is None:
                from faster_whisper import WhisperModel
                model_dir = Path(self.config.data_dir).expanduser() / "voice" / "models"
                model_dir.mkdir(parents=True, exist_ok=True)
                self._model = WhisperModel(
                    "tiny.en",
                    device="cpu",
                    compute_type="int8",
                    download_root=str(model_dir),
                    cpu_threads=2,
                )
            return self._model

    @staticmethod
    def _contains_phrase(transcript: str, phrase: str) -> bool:
        words = re.findall(r"[a-z0-9]+", transcript.casefold())
        target = re.findall(r"[a-z0-9]+", phrase.casefold())
        if not target:
            return False
        width = len(target)
        return any(words[index:index + width] == target for index in range(len(words) - width + 1))

    def start(self) -> bool:
        if self.listening:
            return True
        try:
            import sounddevice as sd  # Verify audio support before starting.
            del sd
        except ImportError as exc:
            self.last_error = "sounddevice is not installed."
            raise RuntimeError(self.last_error) from exc

        self._stop_event.clear()
        while not self._audio_queue.empty():
            try:
                self._audio_queue.get_nowait()
            except queue.Empty:
                break
        self.last_error = None
        self.listening = True
        self._thread = threading.Thread(
            target=self._monitor_loop, name="ALICE-WakeWord", daemon=True
        )
        self._thread.start()
        return True

    async def start_async(self) -> bool:
        return self.start()

    def stop(self) -> bool:
        self._stop_event.set()
        self.listening = False
        thread = self._thread
        if thread and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=15)
            if thread.is_alive():
                self.last_error = "Wake-word microphone did not stop in time."
                return False
        self._thread = None
        return True

    async def stop_async(self) -> bool:
        stopped = await asyncio.to_thread(self.stop)
        if not stopped:
            raise RuntimeError(self.last_error or "Could not release wake-word microphone.")
        return True

    def _audio_callback(self, indata, frames, time_info, status) -> None:
        if status:
            logger.debug("Wake-word microphone status: %s", status)
        try:
            self._audio_queue.put_nowait(indata.copy())
        except queue.Full:
            try:
                self._audio_queue.get_nowait()
                self._audio_queue.put_nowait(indata.copy())
            except queue.Empty:
                pass

    def _transcribe_chunk(self, audio) -> str:
        model = self._get_model()
        segments, _info = model.transcribe(
            audio,
            language="en",
            beam_size=1,
            vad_filter=True,
            condition_on_previous_text=False,
        )
        return " ".join(segment.text.strip() for segment in segments).strip()

    def _monitor_loop(self) -> None:
        import numpy as np
        import sounddevice as sd

        frames = []
        try:
            with sd.InputStream(
                device=self.config.voice.microphone_device,
                samplerate=16000,
                channels=1,
                dtype="float32",
                blocksize=1280,
                callback=self._audio_callback,
            ) as stream:
                self._stream = stream
                while not self._stop_event.is_set():
                    try:
                        frames.append(self._audio_queue.get(timeout=0.5))
                    except queue.Empty:
                        continue
                    # 32 x 80 ms = about 2.56 seconds, with a short overlap.
                    if len(frames) < 32:
                        continue
                    audio = np.concatenate(frames, axis=0).reshape(-1)
                    frames = frames[-12:]
                    if float(np.max(np.abs(audio))) < 0.004:
                        continue
                    transcript = self._transcribe_chunk(audio)
                    if self._contains_phrase(transcript, self.wake_word):
                        logger.info("ALICE wake phrase detected")
                        self._stop_event.set()
                        self.listening = False
                        callback = self._callback
                        if callback:
                            callback()
                        break
        except Exception as exc:
            self.last_error = str(exc)
            self.listening = False
            logger.exception("Wake-word monitor stopped")
        finally:
            self._stream = None
            self.listening = False

    def detect_wake_word(self, audio_data: Any) -> bool:
        """Transcribe a supplied audio array and check for the configured phrase."""
        try:
            transcript = self._transcribe_chunk(audio_data)
            return self._contains_phrase(transcript, self.wake_word)
        except Exception as exc:
            self.last_error = str(exc)
            logger.exception("Could not evaluate wake phrase")
            return False

    def get_status(self) -> dict[str, Any]:
        return {
            "listening": self.listening,
            "wake_word": self.wake_word,
            "last_error": self.last_error,
        }
