"""The scratch folder the other test files write to."""
import shutil

from scratch import Scratch


def test_a_deleted_folder_comes_back_at_the_next_use():
    tmp = Scratch("lv_scratch_")
    assert tmp.path is None
    (tmp / "a.txt").write_text("a")
    shutil.rmtree(tmp.path)
    p = tmp / "b.txt"
    p.write_text("b")
    assert p.read_text() == "b"
