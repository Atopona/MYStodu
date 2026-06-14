"""Cinematic Console — one-command launcher.

Starts the FastAPI backend (which also serves the built frontend) on
http://127.0.0.1:7860 and opens the default browser.
"""
import os
import sys
import threading
import time
import webbrowser

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

HOST = os.environ.get("CC_HOST", "127.0.0.1")
PORT = int(os.environ.get("CC_PORT", "7860"))


def _open_browser() -> None:
    time.sleep(1.2)
    try:
        webbrowser.open(f"http://{HOST}:{PORT}")
    except Exception:
        pass


def main() -> None:
    import uvicorn

    if os.environ.get("CC_NO_BROWSER", "") != "1":
        threading.Thread(target=_open_browser, daemon=True).start()

    uvicorn.run(
        "backend.main:app",
        host=HOST,
        port=PORT,
        log_level="info",
        access_log=False,
    )


if __name__ == "__main__":
    main()
