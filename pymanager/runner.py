"""Exécution d'un processus avec capture de la sortie en direct (utilisé par la console intégrée)."""
from __future__ import annotations

import codecs
import os
import queue
import signal
import subprocess
import threading
import time

from .paths import IS_WINDOWS, NO_WINDOW


class Run:
    """Un processus en cours. Les événements arrivent dans ``events`` :

    ("out", texte) / ("err", texte) / ("exit", code, durée en secondes)
    """

    def __init__(self, cmd, cwd, env):
        self.cmd = list(cmd)
        self.cwd = cwd
        self.env = env
        self.events: queue.Queue = queue.Queue()
        self.proc = None
        self.started = time.monotonic()
        self.exit_code = None
        self.duration = None
        self.start_error = None

    # -- cycle de vie -------------------------------------------------------
    def start(self) -> bool:
        flags = NO_WINDOW
        kwargs = {}
        if IS_WINDOWS:
            flags |= subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            kwargs["start_new_session"] = True
        try:
            self.proc = subprocess.Popen(
                self.cmd, cwd=self.cwd, env=self.env,
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                bufsize=0, creationflags=flags, **kwargs,
            )
        except OSError as exc:
            self.start_error = str(exc)
            self.exit_code = -1
            self.duration = 0.0
            self.events.put(("err", f"Impossible de lancer le processus : {exc}\n"))
            self.events.put(("exit", -1, 0.0))
            return False
        self.started = time.monotonic()
        readers = [
            threading.Thread(target=self._read, args=(self.proc.stdout, "out"), daemon=True),
            threading.Thread(target=self._read, args=(self.proc.stderr, "err"), daemon=True),
        ]
        for t in readers:
            t.start()
        threading.Thread(target=self._watch, args=(readers,), daemon=True).start()
        return True

    def _read(self, pipe, stream):
        decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        while True:
            try:
                chunk = pipe.read(8192)
            except (OSError, ValueError):
                break
            if not chunk:
                break
            text = decoder.decode(chunk)
            if text:
                self.events.put((stream, text))
        tail = decoder.decode(b"", final=True)
        if tail:
            self.events.put((stream, tail))

    def _watch(self, readers):
        code = self.proc.wait()
        for t in readers:
            t.join(timeout=2.0)
        self.exit_code = code
        self.duration = time.monotonic() - self.started
        self.events.put(("exit", code, self.duration))

    # -- état et actions ------------------------------------------------------
    @property
    def alive(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    @property
    def elapsed(self) -> float:
        return self.duration if self.duration is not None else time.monotonic() - self.started

    def write(self, text: str) -> None:
        if not self.alive or self.proc.stdin is None:
            return
        try:
            self.proc.stdin.write(text.encode("utf-8"))
            self.proc.stdin.flush()
        except (OSError, ValueError):
            pass

    def interrupt(self) -> None:
        """Équivalent d'un Ctrl+C."""
        if not self.alive:
            return
        try:
            if IS_WINDOWS:
                self.proc.send_signal(signal.CTRL_BREAK_EVENT)
            else:
                os.killpg(os.getpgid(self.proc.pid), signal.SIGINT)
        except (OSError, ValueError):
            pass

    def stop(self) -> None:
        """Arrête le processus et tous ses enfants."""
        if not self.alive:
            return
        try:
            if IS_WINDOWS:
                subprocess.run(
                    ["taskkill", "/PID", str(self.proc.pid), "/T", "/F"],
                    capture_output=True, stdin=subprocess.DEVNULL, creationflags=NO_WINDOW, timeout=15,
                )
            else:
                os.killpg(os.getpgid(self.proc.pid), signal.SIGKILL)
        except (OSError, ValueError, subprocess.SubprocessError):
            try:
                self.proc.kill()
            except OSError:
                pass


def format_duration(seconds: float) -> str:
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds} s"
    minutes, sec = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes} min {sec:02d} s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours} h {minutes:02d} min"
