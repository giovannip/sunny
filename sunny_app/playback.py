from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path


def _play_win_mci(path: Path) -> None:
    from ctypes import create_unicode_buffer, windll

    mci = windll.winmm.mciSendStringW
    err = create_unicode_buffer(2048)
    alias = "sunny_mp3"
    p = str(path.resolve()).replace("\\", "/")
    open_cmd = f'open "{p}" type mpegvideo alias {alias}'
    if mci(open_cmd, err, len(err), None) != 0:
        raise RuntimeError(f"MCI open failed: {err.value.strip()}")
    try:
        play_cmd = f"play {alias} wait"
        if mci(play_cmd, err, len(err), None) != 0:
            raise RuntimeError(f"MCI play failed: {err.value.strip()}")
    finally:
        mci(f"close {alias}", err, len(err), None)


def _play_ffplay(path: Path, speed: float = 1.0) -> None:
    ff = shutil.which("ffplay")
    if not ff:
        raise FileNotFoundError("ffplay not found on PATH")
    cmd = [ff, "-nodisp", "-autoexit", "-loglevel", "quiet", str(path)]
    if abs(speed - 1.0) > 1e-6:
        cmd = [
            ff,
            "-nodisp",
            "-autoexit",
            "-loglevel",
            "quiet",
            "-af",
            f"atempo={speed}",
            str(path),
        ]
    subprocess.run(cmd, check=True)


def _play_mpv(path: Path, speed: float = 1.0) -> None:
    mpv = shutil.which("mpv")
    if not mpv:
        raise FileNotFoundError("mpv not found on PATH")
    cmd = [mpv, "--no-video", "--really-quiet", str(path)]
    if abs(speed - 1.0) > 1e-6:
        cmd = [mpv, "--no-video", "--really-quiet", f"--speed={speed}", str(path)]
    subprocess.run(cmd, check=True)


def _play_default(path: Path) -> None:
    if sys.platform == "win32":
        os.startfile(str(path))  # noqa: S606
        return
    opener = "open" if sys.platform == "darwin" else "xdg-open"
    subprocess.run([opener, str(path)], check=True)


def play_mp3_file(path: Path, prefer_ffplay: bool, playback_speed: float = 1.0) -> None:
    """Reproduz MP3. Velocidade ≠ 1 exige ffplay (atempo) ou mpv no PATH."""
    path = path.resolve()
    speed = float(playback_speed)
    if speed <= 0:
        speed = 1.0
    want_speed = abs(speed - 1.0) > 1e-6

    if want_speed:
        if shutil.which("ffplay"):
            _play_ffplay(path, speed)
            return
        if shutil.which("mpv"):
            _play_mpv(path, speed)
            return
        print(
            "Aviso: playback_speed != 1.0 requer ffplay ou mpv no PATH; tocando a 1.0x (MCI).",
            flush=True,
        )

    if prefer_ffplay and shutil.which("ffplay"):
        _play_ffplay(path, 1.0)
        return
    if sys.platform == "win32" and not prefer_ffplay:
        _play_win_mci(path)
        return
    if shutil.which("ffplay"):
        _play_ffplay(path, 1.0)
        return
    if shutil.which("mpv"):
        _play_mpv(path, 1.0)
        return
    if sys.platform == "win32":
        _play_win_mci(path)
        return
    _play_default(path)
