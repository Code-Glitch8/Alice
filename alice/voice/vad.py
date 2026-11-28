"""Silero VAD inference using ONNX Runtime only (no PyTorch dependency).

The small official Silero ONNX model is bundled in Windows builds. Source runs
download the same pinned model into ALICE's local data directory on first use.
"""
from __future__ import annotations

import logging
import os
import sys
import urllib.request
from pathlib import Path
from typing import Iterable

import numpy as np

logger = logging.getLogger(__name__)


class SileroVAD:
    """Stateful Silero VAD wrapper for 16 kHz mono float32 microphone audio."""

    SAMPLE_RATE = 16000
    WINDOW_SAMPLES = 512  # Silero's 16 kHz window is 32 ms.
    CONTEXT_SAMPLES = 64
    MODEL_REVISION = "446da2ad95fc90d67a3b12e12ea3f5410b9b3ec4"
    MODEL_URL = (
        "https://raw.githubusercontent.com/snakers4/silero-vad/"
        + MODEL_REVISION
        + "/src/silero_vad/data/silero_vad.onnx"
    )

    def __init__(self, config):
        self.config = config
        self._session = None
        self._model_path: Path | None = None

    def _target_model_path(self) -> Path:
        root = Path(getattr(self.config, "data_dir", Path.home() / ".alice")).expanduser()
        model_dir = root / "voice" / "models"
        model_dir.mkdir(parents=True, exist_ok=True)
        return model_dir / "silero_vad.onnx"

    @staticmethod
    def _bundled_model_path() -> Path | None:
        bundle_root = getattr(sys, "_MEIPASS", None)
        if bundle_root:
            candidate = Path(bundle_root) / "voice_models" / "silero_vad.onnx"
            if candidate.is_file():
                return candidate
        source_candidate = Path(__file__).resolve().parent / "models" / "silero_vad.onnx"
        return source_candidate if source_candidate.is_file() else None

    def _ensure_model(self) -> Path:
        target = self._target_model_path()
        if target.is_file() and target.stat().st_size > 100_000:
            return target

        bundled = self._bundled_model_path()
        if bundled:
            import shutil
            shutil.copy2(bundled, target)
            return target

        temporary = target.with_suffix(".onnx.download")
        logger.info("Downloading the official Silero VAD model to %s", target)
        request = urllib.request.Request(
            self.MODEL_URL,
            headers={"User-Agent": "ALICE-Desktop/1.0"},
        )
        try:
            with urllib.request.urlopen(request, timeout=90) as response:
                with temporary.open("wb") as output:
                    while True:
                        chunk = response.read(1024 * 1024)
                        if not chunk:
                            break
                        output.write(chunk)
            if temporary.stat().st_size < 100_000:
                raise RuntimeError("Downloaded Silero VAD model is unexpectedly small.")
            os.replace(temporary, target)
        except Exception:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
            raise
        return target

    def _load(self):
        if self._session is not None:
            return self._session
        try:
            import onnxruntime as ort
        except ImportError as exc:
            raise RuntimeError(
                "Silero VAD needs onnxruntime. Reinstall ALICE's voice dependencies."
            ) from exc

        options = ort.SessionOptions()
        options.inter_op_num_threads = 1
        options.intra_op_num_threads = 1
        options.enable_cpu_mem_arena = True
        path = self._ensure_model()
        self._session = ort.InferenceSession(
            str(path),
            sess_options=options,
            providers=["CPUExecutionProvider"],
        )
        self._model_path = path
        logger.info("Silero VAD ready (%s)", path)
        return self._session

    @classmethod
    def _segments_from_probabilities(
        cls,
        probabilities: Iterable[float],
        audio_length: int,
        threshold: float = 0.5,
        min_silence_ms: int = 220,
        min_speech_ms: int = 250,
        padding_ms: int = 80,
    ) -> list[tuple[int, int]]:
        """Convert 32 ms speech probabilities into padded sample intervals."""
        probs = list(probabilities)
        if not probs or audio_length <= 0:
            return []

        frame = cls.WINDOW_SAMPLES
        negative_threshold = max(0.05, threshold - 0.15)
        min_silence_frames = max(
            1, int(np.ceil(min_silence_ms * cls.SAMPLE_RATE / 1000 / frame))
        )
        min_speech_samples = int(min_speech_ms * cls.SAMPLE_RATE / 1000)
        padding = int(padding_ms * cls.SAMPLE_RATE / 1000)

        raw: list[tuple[int, int]] = []
        active = False
        speech_start = 0
        silence_start: int | None = None

        for index, probability in enumerate(probs):
            if not active:
                if probability >= threshold:
                    active = True
                    speech_start = index
                    silence_start = None
                continue

            if probability < negative_threshold:
                if silence_start is None:
                    silence_start = index
                if index - silence_start + 1 >= min_silence_frames:
                    raw.append((speech_start * frame, silence_start * frame))
                    active = False
                    silence_start = None
            else:
                silence_start = None

        if active:
            raw.append((speech_start * frame, len(probs) * frame))

        padded: list[tuple[int, int]] = []
        for start, end in raw:
            start = max(0, start - padding)
            end = min(audio_length, end + padding)
            if end - start < min_speech_samples:
                continue
            if padded and start - padded[-1][1] <= int(0.04 * cls.SAMPLE_RATE):
                padded[-1] = (padded[-1][0], max(padded[-1][1], end))
            else:
                padded.append((start, end))
        return padded

    def split_audio(self, audio: np.ndarray) -> list[np.ndarray]:
        """Return speech-only, padded audio chunks. State is reset for each recording."""
        samples = np.asarray(audio, dtype=np.float32).reshape(-1)
        if samples.size == 0:
            return []

        session = self._load()
        state = np.zeros((2, 1, 128), dtype=np.float32)
        context = np.zeros((1, self.CONTEXT_SAMPLES), dtype=np.float32)
        probabilities: list[float] = []

        for offset in range(0, samples.size, self.WINDOW_SAMPLES):
            chunk = np.zeros((1, self.WINDOW_SAMPLES), dtype=np.float32)
            current = samples[offset:offset + self.WINDOW_SAMPLES]
            chunk[0, :current.size] = current
            model_input = np.concatenate((context, chunk), axis=1)
            outputs = session.run(
                None,
                {
                    "input": model_input,
                    "state": state,
                    "sr": np.asarray(self.SAMPLE_RATE, dtype=np.int64),
                },
            )
            probabilities.append(float(np.asarray(outputs[0]).reshape(-1)[0]))
            state = np.asarray(outputs[1], dtype=np.float32)
            context = model_input[:, -self.CONTEXT_SAMPLES:]

        voice = getattr(self.config, "voice", None)
        threshold = float(getattr(voice, "vad_threshold", 0.5))
        min_silence_ms = int(getattr(voice, "vad_min_silence_ms", 220))
        intervals = self._segments_from_probabilities(
            probabilities,
            int(samples.size),
            threshold=threshold,
            min_silence_ms=min_silence_ms,
        )
        return [samples[start:end].copy() for start, end in intervals if end > start]
