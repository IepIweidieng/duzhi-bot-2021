""" file
    Utility functions for handling file contents.
"""

import errno
import os
import tempfile
from typing import Iterator


def mkdir(dir: str) -> None:
    """ Create a (nested) directory `dir` if it does not exist. """
    try:
        os.makedirs(dir)
    except OSError as e:
        if e.errno != errno.EEXIST or not os.path.isdir(dir):
            raise


def save_tmp_file(dir: str, ext: str, chunk_iter: Iterator[bytes]) -> str:
    """ Save a file to `dir` with extension `ext` and return its path. """
    with tempfile.NamedTemporaryFile(dir=dir, prefix=f"{ext}-", delete=False) as f:
        for chunk in chunk_iter:
            f.write(chunk)
        raw_path = f.name

    res = f"{raw_path}.{ext}"
    os.rename(raw_path, res)  # Ready to serve
    return res
