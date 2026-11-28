from types import SimpleNamespace

from alice.voice.wake_word import WakeWordDetector


def test_wake_phrase_matches_case_insensitively():
    config = SimpleNamespace(
        voice=SimpleNamespace(wake_word="alice"),
        data_dir=".",
    )
    detector = WakeWordDetector(config)
    assert detector._contains_phrase("Hey ALICE, open the dashboard", "alice")


def test_wake_phrase_requires_whole_word_match():
    assert not WakeWordDetector._contains_phrase("palice", "alice")


def test_multi_word_wake_phrase():
    assert WakeWordDetector._contains_phrase(
        "hello hey jarvis please listen", "hey jarvis"
    )
