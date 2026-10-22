import io
import struct
import threading
import unittest

from mdl.framing import encode_message, read_message, write_message


class FramingTest(unittest.TestCase):
    def test_round_trip_with_non_ascii_title(self):
        msg = {"type": "done", "id": "1", "path": "C:\\Music\\media\\Café ☕.opus"}
        stream = io.BytesIO(encode_message(msg))
        self.assertEqual(read_message(stream), msg)

    def test_length_prefix_is_little_endian_byte_count(self):
        data = encode_message({"a": "é"})
        (length,) = struct.unpack("<I", data[:4])
        self.assertEqual(length, len(data) - 4)
        self.assertEqual(data[4:].decode("utf-8"), '{"a": "é"}')

    def test_eof_returns_none(self):
        self.assertIsNone(read_message(io.BytesIO(b"")))

    def test_truncated_body_raises(self):
        data = encode_message({"type": "ping"})[:-2]
        with self.assertRaises(EOFError):
            read_message(io.BytesIO(data))

    def test_write_message_writes_and_flushes(self):
        out = io.BytesIO()
        write_message(out, {"type": "pong"}, threading.Lock())
        out.seek(0)
        self.assertEqual(read_message(out), {"type": "pong"})


if __name__ == "__main__":
    unittest.main()
