"""
Phase D0.6 — bundled `mongod` lifecycle wrapper.

Owns the subprocess so UBOS's offline mode is "start local mongod, point
Motor at it, and shut it down cleanly on app exit". This is the file that
the Electron main process will call into (via the FastAPI startup event)
once we ship the desktop bundle in D4.

Environment:
    UBOS_MONGOD_BIN         — absolute path to the `mongod` binary.
                              Falls back to `mongod` on PATH so dev machines
                              can run bundled mode without staging binaries.
    UBOS_OFFLINE_DATA_DIR   — dbpath (default ~/.ubos/data)
    UBOS_MONGOD_LOG_DIR     — logpath dir (default: sibling of data dir)
    UBOS_MONGOD_PORT        — explicit port (default: pick a free random one)

The launcher is deliberately conservative:
- Binds only to 127.0.0.1 (never listens on external interfaces).
- No auth on the socket — the OS user boundary is our security perimeter
  in single-user desktop mode.
- --nojournal for faster startup on small offline workloads.
- SIGTERM (10s grace) → SIGKILL fallback on stop.
- Health-checks via a Motor `ping` command with tight timeouts.
"""
from __future__ import annotations

import atexit
import logging
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

log = logging.getLogger("ubos.mongod_launcher")


def _pick_free_port() -> int:
    """Ask the OS for a free localhost port. Race: something else could
    grab it between here and mongod's bind — mongod will exit fast on
    conflict, and `wait_until_ready` will surface it in <2s."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class MongodLauncherError(RuntimeError):
    pass


class MongodLauncher:
    """Manages a single `mongod` subprocess for offline mode.

    Lifecycle:
        launcher = MongodLauncher(data_dir=…)
        launcher.start()              # spawns mongod
        launcher.wait_until_ready()   # blocks until pingable, <30s
        …use Motor pointed at launcher.uri…
        launcher.stop()               # SIGTERM → SIGKILL
    """

    def __init__(
        self,
        *,
        binary: str | None = None,
        data_dir: str | Path | None = None,
        log_dir: str | Path | None = None,
        port: int | None = None,
    ):
        self.binary = binary or os.environ.get("UBOS_MONGOD_BIN") or shutil.which("mongod")
        if not self.binary:
            raise MongodLauncherError(
                "mongod binary not found. Set UBOS_MONGOD_BIN or put mongod on PATH.",
            )
        self.data_dir = Path(
            data_dir or os.environ.get("UBOS_OFFLINE_DATA_DIR", "~/.ubos/data")
        ).expanduser()
        self.log_dir = Path(
            log_dir or os.environ.get("UBOS_MONGOD_LOG_DIR")
            or (self.data_dir.parent / "logs")
        ).expanduser()
        self.port = port or int(os.environ.get("UBOS_MONGOD_PORT") or _pick_free_port())
        self.proc: subprocess.Popen | None = None
        self._is_windows = sys.platform.startswith("win")

    # ── properties ──
    @property
    def uri(self) -> str:
        return f"mongodb://127.0.0.1:{self.port}"

    @property
    def log_path(self) -> Path:
        return self.log_dir / "mongod.log"

    # ── lifecycle ──
    def start(self) -> None:
        if self.proc is not None and self.is_alive():
            log.warning("mongod already running on port %d", self.port)
            return
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.log_dir.mkdir(parents=True, exist_ok=True)

        # `--nojournal` is deprecated in mongod 6.x+ (default WiredTiger
        # handles journaling internally). Do NOT pass it on newer builds
        # — check version first.
        args = [
            self.binary,
            "--bind_ip", "127.0.0.1",
            "--port", str(self.port),
            "--dbpath", str(self.data_dir),
            "--logpath", str(self.log_path),
            "--logappend",
        ]
        # Older builds (≤5.0) accept --nojournal; skip for 6.0+ to avoid
        # startup rejection.
        if self._binary_version_major() <= 5:
            args.append("--nojournal")

        log.info("Launching mongod: %s", " ".join(args))
        # On Windows use CREATE_NEW_PROCESS_GROUP so we can send Ctrl-Break
        # equivalent signals cleanly.
        popen_kwargs = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
        if self._is_windows:
            popen_kwargs["creationflags"] = 0x00000200  # CREATE_NEW_PROCESS_GROUP
        self.proc = subprocess.Popen(args, **popen_kwargs)
        # Auto-cleanup on interpreter exit
        atexit.register(self._atexit_stop)

    def _binary_version_major(self) -> int:
        """Best-effort major version detection. Fails-safe to 6 (skip
        --nojournal) so newer builds work by default."""
        try:
            out = subprocess.check_output(
                [self.binary, "--version"], stderr=subprocess.STDOUT, timeout=5,
            ).decode(errors="ignore")
            for line in out.splitlines():
                if "db version" in line.lower():
                    # e.g. "db version v7.0.37"
                    return int(line.split("v", 1)[-1].split(".")[0])
        except Exception:  # noqa: BLE001
            pass
        return 6

    def is_alive(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def wait_until_ready(self, timeout: float = 30.0) -> None:
        """Poll the port until mongod accepts connections, up to `timeout`."""
        started = time.monotonic()
        while time.monotonic() - started < timeout:
            if not self.is_alive():
                raise MongodLauncherError(
                    f"mongod exited during startup — see {self.log_path}",
                )
            try:
                # Cheap TCP probe first
                with socket.create_connection(("127.0.0.1", self.port), timeout=0.5):
                    pass
                # Then verify server is actually answering commands
                if self._ping():
                    log.info("mongod ready on %s after %.2fs",
                             self.uri, time.monotonic() - started)
                    return
            except OSError:
                pass
            time.sleep(0.1)
        raise MongodLauncherError(
            f"mongod did not become ready within {timeout}s. "
            f"See log at {self.log_path}",
        )

    def _ping(self) -> bool:
        """Synchronous ping using pymongo (which is a transitive dep of
        motor, so always available in our tree)."""
        try:
            import pymongo
            c = pymongo.MongoClient(
                self.uri, serverSelectionTimeoutMS=500, connectTimeoutMS=500,
            )
            c.admin.command("ping")
            c.close()
            return True
        except Exception:  # noqa: BLE001
            return False

    def stop(self, timeout: float = 10.0) -> None:
        if self.proc is None:
            return
        if self.proc.poll() is not None:
            log.debug("mongod already exited (rc=%s)", self.proc.returncode)
            self.proc = None
            return
        if self._is_windows:
            # No SIGTERM on Windows — use taskkill with tree so mongod cleans up.
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(self.proc.pid)],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        else:
            self.proc.send_signal(signal.SIGTERM)
        try:
            self.proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            log.warning("mongod did not exit within %.0fs of SIGTERM, escalating to SIGKILL", timeout)
            self.proc.kill()
            self.proc.wait(timeout=5)
        log.info("mongod stopped (rc=%s)", self.proc.returncode)
        self.proc = None

    def _atexit_stop(self) -> None:
        try:
            self.stop()
        except Exception as e:  # noqa: BLE001
            log.error("mongod atexit stop failed: %s", e)


# ══════════════════════════════════════════════════════════════════════
# Factory helper for the DatabaseAdapter (UBOS_DB_MODE=bundled)
# ══════════════════════════════════════════════════════════════════════
_LAUNCHER_SINGLETON: MongodLauncher | None = None


def get_or_start_bundled_mongod() -> MongodLauncher:
    """Idempotent — first call starts mongod, subsequent calls return the
    same instance. Used by `db_adapter.get_database_adapter()` when
    `UBOS_DB_MODE=bundled`."""
    global _LAUNCHER_SINGLETON
    if _LAUNCHER_SINGLETON is not None and _LAUNCHER_SINGLETON.is_alive():
        return _LAUNCHER_SINGLETON
    launcher = MongodLauncher()
    launcher.start()
    launcher.wait_until_ready(timeout=30)
    _LAUNCHER_SINGLETON = launcher
    return launcher


def reset_bundled_launcher_for_tests() -> None:
    """Test helper — stops the singleton and clears it so the next call
    starts a fresh mongod on a fresh port."""
    global _LAUNCHER_SINGLETON
    if _LAUNCHER_SINGLETON is not None:
        _LAUNCHER_SINGLETON.stop()
        _LAUNCHER_SINGLETON = None
