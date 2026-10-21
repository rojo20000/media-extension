"""Chrome native messaging framing: 4-byte little-endian length, then UTF-8 JSON."""
import json
import os
import struct
import sys


def binary_stdio():
    """Return (stdin, stdout) as binary streams, with Windows newline translation off."""
    if sys.platform == "win32":
        import msvcrt
        msvcrt.setmode(sys.stdin.fileno(), os.O_BINARY)
        msvcrt.setmode(sys.stdout.fileno(), os.O_BINARY)
    return sys.stdin.buffer, sys.stdout.buffer


def _read_exact(stream, n):
    data = b""
    while len(data) < n:
        chunk = stream.read(n - len(data))
        if not chunk:
            break
        data += chunk
    return data


def read_message(stream):
    header = _read_exact(stream, 4)
    if not header:
        return None
    if len(header) < 4:
        raise EOFError("truncated message header")
    (length,) = struct.unpack("<I", header)
    body = _read_exact(stream, length)
    if len(body) < length:
        raise EOFError("truncated message body")
    return json.loads(body.decode("utf-8"))


def encode_message(obj):
    body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
    return struct.pack("<I", len(body)) + body


def write_message(stream, obj, lock):
    data = encode_message(obj)
    with lock:
        stream.write(data)
        stream.flush()
