from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import numpy as np

from alice.core.config import VoiceConfig
from alice.voice.tts import LocalTTS
from alice.voice.vad import SileroVAD


def test_voice_defaults_use_kokoro_and_silero_vad():
    voice = VoiceConfig()
    assert voice.tts_engine == "kokoro"
    assert voice.tts_voice == "af_heart"
    assert voice.tts_language == "en-us"
    assert voice.voice_activity_detection is True
    assert voice.stt_model == "small"


def test_silero_vad_returns_no_segments_for_silence():
    probs = [0.02] * 40
    assert SileroVAD._segments_from_probabilities(probs, 40 * 512) == []


def test_silero_vad_finds_and_pads_a_speech_segment():
    probs = [0.02] * 4 + [0.90] * 12 + [0.02] * 10
    segments = SileroVAD._segments_from_probabilities(probs, len(probs) * 512)
    assert len(segments) == 1
    start, end = segments[0]
    assert start < 4 * 512
    assert end > 16 * 512
    assert end <= len(probs) * 512


def test_silero_vad_keeps_long_pause_between_phrases():
    probs = (
        [0.02] * 3
        + [0.90] * 12
        + [0.02] * 10
        + [0.90] * 12
        + [0.02] * 8
    )
    segments = SileroVAD._segments_from_probabilities(probs, len(probs) * 512)
    assert len(segments) == 2
    assert segments[0][1] < segments[1][0]


def _make_tts(tmp_path: Path) -> LocalTTS:
    config = SimpleNamespace(
        data_dir=str(tmp_path),
        voice=VoiceConfig(),
    )
    return LocalTTS(config)


def test_tts_uses_piper_when_kokoro_fails(tmp_path):
    tts = _make_tts(tmp_path)
    calls = []

    def kokoro(_text):
        calls.append("kokoro")
        raise RuntimeError("model not downloaded")

    def piper(_text):
        calls.append("piper")

    def sapi(_text):
        calls.append("sapi")

    tts._speak_kokoro = kokoro
    tts._speak_piper_if_available = piper
    tts._speak_sapi = sapi

    tts._speak_sync("Hello from ALICE")

    assert calls == ["kokoro", "piper"]
    assert tts.engine == "piper"
    assert tts.last_error is None


def test_tts_uses_sapi_as_last_resort(tmp_path):
    tts = _make_tts(tmp_path)
    calls = []

    def unavailable(name):
        def fail(_text):
            calls.append(name)
            raise RuntimeError(name + " unavailable")
        return fail

    def sapi(_text):
        calls.append("sapi")

    tts._speak_kokoro = unavailable("kokoro")
    tts._speak_piper_if_available = unavailable("piper")
    tts._speak_sapi = sapi

    tts._speak_sync("Hello from ALICE")

    assert calls == ["kokoro", "piper", "sapi"]
    assert tts.engine == "windows_sapi"
