import os
import subprocess
import sys
from pathlib import Path

os.environ.setdefault(
    "PLAYWRIGHT_BROWSERS_PATH", str(Path(__file__).resolve().parent / ".browsers")
)
subprocess.run(
    [sys.executable, "-m", "playwright", "install", "chromium", *sys.argv[1:]],
    check=True,
)
