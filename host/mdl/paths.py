"""Where downloads go: a "media" folder inside the user's real Music folder."""
import sys
from pathlib import Path

FOLDERID_MUSIC = "{4BD8D571-6D19-48D3-BE97-422220080E43}"


def _windows_known_music():
    if sys.platform != "win32":
        return None
    import ctypes
    from ctypes import wintypes

    class GUID(ctypes.Structure):
        _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD),
                    ("Data3", wintypes.WORD), ("Data4", ctypes.c_ubyte * 8)]

    guid = GUID()
    ctypes.oledll.ole32.CLSIDFromString(ctypes.c_wchar_p(FOLDERID_MUSIC), ctypes.byref(guid))
    path_ptr = ctypes.c_wchar_p()
    try:
        ctypes.windll.shell32.SHGetKnownFolderPath(ctypes.byref(guid), 0, None, ctypes.byref(path_ptr))
        return path_ptr.value
    except OSError:
        return None
    finally:
        ctypes.windll.ole32.CoTaskMemFree(path_ptr)


def music_dir(known_folder=None):
    found = (known_folder or _windows_known_music)()
    return Path(found) if found else Path.home() / "Music"


def media_dir():
    path = music_dir() / "media"
    path.mkdir(parents=True, exist_ok=True)
    return path


def unique_destination(directory, filename, media_id):
    """A path in `directory` for `filename` that doesn't overwrite anything."""
    directory = Path(directory)
    candidate = directory / filename
    if not candidate.exists():
        return candidate
    stem, suffix = Path(filename).stem, Path(filename).suffix
    candidate = directory / f"{stem} [{media_id}]{suffix}"
    n = 2
    while candidate.exists():
        candidate = directory / f"{stem} [{media_id}] ({n}){suffix}"
        n += 1
    return candidate
