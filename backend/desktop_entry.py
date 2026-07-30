"""Frozen entry point for the desktop backend (PyInstaller target).

The Electron shell launches this exe as:
    ubos-backend.exe --host 127.0.0.1 --port <port>
All desktop configuration (MONGO_URL, JWT_SECRET, UBOS_DESKTOP, FRONTEND_DIR,
license paths, …) is supplied via environment variables by the shell.
"""
from __future__ import annotations

import argparse
import multiprocessing


def main() -> None:
    import uvicorn
    from server import app

    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8001)
    args = ap.parse_args()
    # log_config=None avoids uvicorn's dictConfig, which can misbehave in a
    # frozen bundle; basic logging still reaches stdout.
    uvicorn.run(app, host=args.host, port=args.port, log_level="info", log_config=None)


if __name__ == "__main__":
    # Required for PyInstaller-frozen apps: without this, spawned child
    # processes (multiprocessing/spawn on Windows & macOS) re-run this entry
    # point and the server never binds.
    multiprocessing.freeze_support()
    main()
