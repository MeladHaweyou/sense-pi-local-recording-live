# File: sonify/utils/audio.py
from __future__ import annotations

import numpy as np
import wave
from pathlib import Path


def write_wav(path: str | Path, sample_rate: int, audio: np.ndarray) -> None:
    """
    Write mono float audio in [-1,1] to 16-bit PCM WAV.
    """
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    a = np.asarray(audio, dtype=float)
    a = np.clip(a, -1.0, 1.0)
    pcm = (a * 32767.0).astype(np.int16)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(int(sample_rate))
        wf.writeframes(pcm.tobytes())
