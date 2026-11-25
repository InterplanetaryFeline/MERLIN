"""A temporary folder for a test file's output, made when something is written to it.

A folder made at import sits empty until its tests run, over an hour later on a slow machine, and was once deleted in
between: 29 tests failed on files that could not be created.
"""
import atexit
import pathlib
import shutil
import tempfile


class Scratch:
    """`scratch / "name"` is a path in the folder, which exists from then on, again if something has deleted it."""

    def __init__(self, prefix):
        self.prefix, self.path = prefix, None

    def __truediv__(self, name):
        if self.path is None:
            self.path = pathlib.Path(tempfile.mkdtemp(prefix=self.prefix))
            atexit.register(shutil.rmtree, self.path, True)
        self.path.mkdir(parents=True, exist_ok=True)
        return self.path / name
