"""Chrome native messaging host for the Media Downloader extension."""
import logging
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from mdl.framing import binary_stdio, read_message, write_message  # noqa: E402
from mdl.jobs import JobRunner  # noqa: E402
from mdl.paths import media_dir  # noqa: E402
from mdl.ytdlp import load_tools  # noqa: E402

HERE = Path(__file__).resolve().parent
log = logging.getLogger("media_host")


def setup_logging(path):
    """Log this session to `path`. Returns why that isn't possible, or None."""
    try:
        handler = logging.FileHandler(path, mode="w", encoding="utf-8")
    except OSError as e:
        return f"Couldn't open the log file: {e}"
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logging.root.addHandler(handler)
    logging.root.setLevel(logging.INFO)
    return None


def main(stdin=None, stdout=None, tools=None, media=None, startup_error=None):
    if stdin is None:
        stdin, stdout = binary_stdio()
    tools = tools or load_tools(HERE / "config.json")
    lock = threading.Lock()

    def send(msg):
        log.info("-> %s %s", msg.get("type"), msg.get("id"))
        write_message(stdout, msg, lock)

    # A helper that can't start answers with the reason, so the popup can show it;
    # exiting would only give Chrome's "Native host has exited."
    problems = [startup_error] if startup_error else []
    runner = None
    try:
        runner = JobRunner(tools, Path(media) if media else media_dir(), send)
    except OSError as e:
        log.exception("couldn't prepare the media folder")
        problems.append(f"Couldn't create the media folder: {e}")
    threads = []
    while True:
        msg = read_message(stdin)
        if msg is None:
            break
        id_, kind = msg.get("id"), msg.get("type")
        log.info("<- %s %s %s", kind, id_, msg.get("url", ""))
        try:
            if problems and (kind == "ping" or runner is None):
                send({"type": "error", "id": id_, "message": " ".join(problems)})
            elif kind == "ping":
                runner.ping(id_)
            elif kind == "probe":
                threads.append(runner.probe(id_, msg["url"], msg.get("site", "generic")))
            elif kind == "download":
                threads.append(runner.download(id_, msg))
            elif kind == "cancel":
                runner.cancel(id_)
            else:
                send({"type": "error", "id": id_, "message": f"Unknown message type: {kind}"})
        except Exception as e:
            log.exception("failed handling %s", kind)
            send({"type": "error", "id": id_, "message": f"{type(e).__name__}: {e}"})
    # Chrome closed the connection: let running downloads finish saving.
    for t in threads:
        t.join()


if __name__ == "__main__":
    main(startup_error=setup_logging(HERE / "media_host.log"))
