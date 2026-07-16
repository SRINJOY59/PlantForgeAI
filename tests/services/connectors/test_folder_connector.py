import os
import time

from connectors.folder import FolderConnector


def write(dirpath, name, content, mtime=None):
    p = dirpath / name
    p.write_bytes(content)
    if mtime:
        os.utime(p, (mtime, mtime))
    return p


def test_fetches_all_on_first_sync(tmp_path):
    write(tmp_path, "a.csv", b"1", mtime=100)
    write(tmp_path, "b.md", b"2", mtime=200)

    items = list(FolderConnector("c", str(tmp_path)).fetch("0"))

    assert [i.filename for i in items] == ["a.csv", "b.md"]   # ascending mtime
    assert items[0].data == b"1"
    assert items[-1].marker == "200.000000"


def test_only_returns_files_newer_than_cursor(tmp_path):
    write(tmp_path, "old.csv", b"o", mtime=100)
    write(tmp_path, "new.csv", b"n", mtime=300)

    items = list(FolderConnector("c", str(tmp_path)).fetch("200.000000"))

    assert [i.filename for i in items] == ["new.csv"]


def test_skips_dotfiles_and_dirs(tmp_path):
    write(tmp_path, ".hidden", b"x", mtime=100)
    (tmp_path / "sub").mkdir()
    write(tmp_path, "real.txt", b"y", mtime=100)

    names = [i.filename for i in FolderConnector("c", str(tmp_path)).fetch("0")]
    assert names == ["real.txt"]


def test_recursive_walk(tmp_path):
    (tmp_path / "unit100").mkdir()
    write(tmp_path / "unit100", "wo.csv", b"z", mtime=100)

    names = [i.filename for i in FolderConnector("c", str(tmp_path)).fetch("0")]
    assert names == ["wo.csv"]
