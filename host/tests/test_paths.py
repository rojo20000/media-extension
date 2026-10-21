import tempfile
import unittest
from pathlib import Path

from mdl.paths import music_dir, unique_destination


class MusicDirTest(unittest.TestCase):
    def test_uses_known_folder_result(self):
        self.assertEqual(music_dir(known_folder=lambda: "D:\\OneDrive\\Music"),
                         Path("D:\\OneDrive\\Music"))

    def test_falls_back_to_home_music(self):
        self.assertEqual(music_dir(known_folder=lambda: None), Path.home() / "Music")


class UniqueDestinationTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_free_name_is_kept(self):
        self.assertEqual(unique_destination(self.dir, "Song.opus", "abc"), self.dir / "Song.opus")

    def test_existing_name_gets_id(self):
        (self.dir / "Song.opus").touch()
        self.assertEqual(unique_destination(self.dir, "Song.opus", "abc"), self.dir / "Song [abc].opus")

    def test_existing_id_name_gets_counter(self):
        (self.dir / "Song.opus").touch()
        (self.dir / "Song [abc].opus").touch()
        self.assertEqual(unique_destination(self.dir, "Song.opus", "abc"),
                         self.dir / "Song [abc] (2).opus")


if __name__ == "__main__":
    unittest.main()
