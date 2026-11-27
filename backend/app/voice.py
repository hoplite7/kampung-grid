"""Voice notes: speech to text with Whisper, running on the laptop. (Person 1 owns this.)

Claude reads text, not audio, so a voice note is first turned into text by Whisper
(a free, open-source speech-to-text model), then read like any typed report.

Whisper is OPTIONAL because it's a large download. To turn voice notes on:
    backend/.venv/bin/pip install faster-whisper
The first voice note then downloads the model (a few hundred MB, needs internet once).
Model size: KG_WHISPER_MODEL=small (default), or medium for better Singlish.
"""

import os
import tempfile

_model = None


class VoiceUnavailable(Exception):
    pass


def transcribe(audio: bytes, suffix: str = ".webm") -> str:
    global _model
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise VoiceUnavailable(
            "Voice notes need Whisper. In the terminal run: backend/.venv/bin/pip install faster-whisper"
        ) from exc
    if _model is None:
        _model = WhisperModel(os.getenv("KG_WHISPER_MODEL", "small"), device="cpu", compute_type="int8")
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
        f.write(audio)
        path = f.name
    try:
        segments, _info = _model.transcribe(path, beam_size=1)
        return " ".join(seg.text.strip() for seg in segments).strip()
    finally:
        os.unlink(path)
