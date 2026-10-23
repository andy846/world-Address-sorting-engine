"""SQLite connections that always release the underlying file handle.

`with sqlite3.connect(path) as conn:` scopes only the transaction; the
connection object itself stays open and keeps the file locked. POSIX lets a
caller rename or delete a file that is still open, so the leak is invisible
there, but Windows refuses both and raises WinError 32. This project installs
reference databases with `os.replace`, so every connection is opened through
`open_db` to guarantee the handle is released before the file is moved.
"""

from contextlib import contextmanager
from pathlib import Path
import sqlite3
from typing import Iterator


@contextmanager
def open_db(path: Path | str) -> Iterator[sqlite3.Connection]:
    """Open a SQLite connection, commit on success, and always close it."""
    conn = sqlite3.connect(path)
    try:
        with conn:
            yield conn
    finally:
        conn.close()
