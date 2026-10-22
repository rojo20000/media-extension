import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from mdl.paths import move_unique, music_dir


class MusicDirTest(unittest.TestCase):
    def test_uses_known_folder_result(self):
        self.assertEqual(music_dir(known_folder=lambda: "D:\\OneDrive\\Music"),
                         Path("D:\\OneDrive\\Music"))

    def test_falls_back_to_home_music(self):
        self.assertEqual(music_dir(known_folder=lambda: None), Path.home() / "Music")


class MoveUniqueTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name) / "media"
        self.stage = Path(self.tmp.name) / "stage"
        self.dir.mkdir()
        self.stage.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def staged(self, text="new", name="Song.opus"):
        path = self.stage / text / name
        path.parent.mkdir()
        path.write_text(text)
        return path

    def test_free_name_is_kept(self):
        dest = move_unique(self.staged(), self.dir, "abc")
        self.assertEqual(dest, self.dir / "Song.opus")
        self.assertEqual(dest.read_text(), "new")
        self.assertEqual(list(self.stage.rglob("*.opus")), [])

    def test_existing_name_gets_id(self):
        (self.dir / "Song.opus").write_text("old")
        self.assertEqual(move_unique(self.staged(), self.dir, "abc"), self.dir / "Song [abc].opus")
        self.assertEqual((self.dir / "Song.opus").read_text(), "old")

    def test_existing_id_name_gets_counter(self):
        (self.dir / "Song.opus").touch()
        (self.dir / "Song [abc].opus").touch()
        self.assertEqual(move_unique(self.staged(), self.dir, "abc"), self.dir / "Song [abc] (2).opus")

    def test_file_appearing_after_the_check_is_not_overwritten(self):
        # Simulates another job saving the same name between "is it free?" and the move.
        (self.dir / "Song.opus").write_text("old")
        with mock.patch.object(Path, "exists", return_value=False):
            dest = move_unique(self.staged(), self.dir, "abc")
        self.assertEqual(dest, self.dir / "Song [abc].opus")
        self.assertEqual((self.dir / "Song.opus").read_text(), "old")

    def test_concurrent_moves_keep_every_file(self):
        sources = [self.staged(str(i)) for i in range(8)]
        barrier = threading.Barrier(len(sources))
        results = []

        def move(src):
            barrier.wait()
            results.append(move_unique(src, self.dir, "abc"))

        threads = [threading.Thread(target=move, args=(src,)) for src in sources]
        for t in threads:
            t.start()
        for t in threads:
            t.join(10)
        self.assertEqual(len(set(results)), 8)
        self.assertEqual(sorted(p.read_text() for p in self.dir.iterdir()), sorted(str(i) for i in range(8)))


if __name__ == "__main__":
    unittest.main()
