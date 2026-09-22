import sys
from concurrent.futures import Future

import pytest
import scripts_transcript as transcript


def test_terminal_transcripts_remain_in_input_order(monkeypatch, capsys):
    class Executor:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def submit(self, fn, index, url):
            future = Future()
            future.set_result((index, url))
            return future

    monkeypatch.setattr(sys, "argv", ["transcript", "--terminal", "first", "second"])
    monkeypatch.setattr(transcript, "ThreadPoolExecutor", Executor)
    monkeypatch.setattr(transcript, "as_completed", lambda futures: reversed(list(futures)))
    transcript.main()
    output = capsys.readouterr()
    assert output.out == "first\nsecond\n"
    assert "Processing" in output.err


def test_invalid_workers_fail_before_network_access(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["transcript", "--workers", "0", "a-url"])
    with pytest.raises(SystemExit) as exc:
        transcript.main()
    assert exc.value.code == 2
