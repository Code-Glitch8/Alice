#!/usr/bin/env python3
"""Offline-capable microphone capture and speech recognition for ALICE.

Audio is held in memory only. No recording is written to disk.
"""
from __future__ import annotations

import logging
import threading
import asyncio
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class VoicePipeline:
    """Capture microphone audio and transcribe it locally with faster-whisper."""

    SAMPLE_RATE = 16000

    def __init__(self, config: Any):
        self.config = config
        self.listening = False
        self.speaking = False
        self.wake_word_active = False
        self.mic_muted = bool(config.voice.mute) if config else False
        self._stream = None
        self._frames: list[Any] = []
        self._audio_lock = threading.Lock()
        self._model = None
        self._model_lock = threading.Lock()
        self._tts_engine = None
        self._tts = None
        self._tts_lock = threading.Lock()
        self.last_error: Optional[str] = None

    def _audio_callback(self, indata, frames, time_info, status) -> None:
        if status:
            logger.debug("Microphone stream status: %s", status)
        with self._audio_lock:
            self._frames.append(indata.copy())

    def start_listening(self) -> bool:
        """Open the selected microphone and begin buffering 16 kHz mono audio."""
        if self.mic_muted:
            raise RuntimeError("Microphone is muted. Unmute it in ALICE Settings.")
        if self.listening:
            return True
        try:
            import sounddevice as sd
        except ImportError as exc:
            raise RuntimeError("Microphone support is missing. Reinstall ALICE dependencies.") from exc

        with self._audio_lock:
            self._frames.clear()
        try:
            self._stream = sd.InputStream(
                device=self.config.voice.microphone_device,
                samplerate=self.SAMPLE_RATE,
                channels=1,
                dtype="float32",
                callback=self._audio_callback,
                blocksize=0,
            )
            self._stream.start()
            self.listening = True
            self.last_error = None
            logger.info("Microphone capture started")
            return True
        except Exception as exc:
            self._stream = None
            self.last_error = str(exc)
            logger.exception("Could not start microphone capture")
            raise RuntimeError(f"Could not open microphone: {exc}") from exc

    def stop_listening(self) -> bool:
        """Stop microphone capture and retain the in-memory audio for transcription."""
        stream, self._stream = self._stream, None
        self.listening = False
        if stream is not None:
            try:
                stream.stop()
            finally:
                stream.close()
        logger.info("Microphone capture stopped")
        return True

    def _get_model(self):
        with self._model_lock:
            if self._model is None:
                try:
                    from faster_whisper import WhisperModel
                except ImportError as exc:
                    raise RuntimeError(
                        "Speech recognition is not installed. Reinstall ALICE with its voice dependencies."
                    ) from exc
                voice_dir = Path(self.config.data_dir).expanduser() / "voice" / "models"
                voice_dir.mkdir(parents=True, exist_ok=True)
                model_name = str(getattr(self.config.voice, "stt_model", "base") or "base")
                # CPU INT8 is the most compatible mode for packaged Windows builds.
                self._model = WhisperModel(
                    model_name,
                    device="cpu",
                    compute_type="int8",
                    download_root=str(voice_dir),
                    cpu_threads=4,
                )
            return self._model

    def recognize(self) -> str:
        """Transcribe the last recording using the local Faster-Whisper model."""
        if self.listening:
            raise RuntimeError("Stop the microphone recording before transcribing.")
        import numpy as np

        with self._audio_lock:
            frames = list(self._frames)
            self._frames.clear()
        if not frames:
            return ""
        audio = np.concatenate(frames, axis=0).reshape(-1).astype(np.float32, copy=False)
        if audio.size < int(self.SAMPLE_RATE * 0.35):
            return ""
        if float(np.max(np.abs(audio))) < 0.004:
            return ""

        model = self._get_model()
        segments, _info = model.transcribe(
            audio,
            beam_size=1,
            vad_filter=True,
            condition_on_previous_text=False,
        )
        transcript = " ".join(segment.text.strip() for segment in segments).strip()
        logger.info("Speech recognition completed (%d characters)", len(transcript))
        return transcript

    def speak(self, text: str) -> None:
        """Speak locally with Piper when configured, otherwise Windows SAPI."""
        text = str(text or "").strip()
        if not text:
            return
        with self._tts_lock:
            if self.speaking:
                logger.debug("Ignoring overlapping speech request")
                return
            self.speaking = True
        try:
            from alice.voice.tts import PiperTTS
            if self._tts is None:
                self._tts = PiperTTS(self.config)
            asyncio.run(self._tts.speak(text))
        except Exception as exc:
            self.last_error = str(exc)
            logger.exception("Text-to-speech failed")
        finally:
            self.speaking = False

    def stop_speaking(self) -> None:
        if self._tts is not None:
            self._tts.stop()
        self.speaking = False

    def set_wake_word(self, wake_word: str) -> bool:
        self.config.voice.wake_word = str(wake_word).strip()
        self.wake_word_active = bool(self.config.voice.wake_word)
        return self.wake_word_active

    def toggle_mute(self) -> bool:
        self.mic_muted = not self.mic_muted
        if self.mic_muted and self.listening:
            self.stop_listening()
        return not self.mic_muted

    def get_status(self) -> Dict[str, Any]:
        return {
            "listening": self.listening,
            "speaking": self.speaking,
            "mic_muted": self.mic_muted,
            "wake_word_active": self.wake_word_active,
            "last_error": self.last_error,
            "buffered_audio": bool(self._frames),
        }
