import io
import logging
import threading
import time
import types

from milk import stream
from milk.stream import LatestFrameReader, _input_options, _read_exact, redact

HUB = "rtsps://u:p@203.0.113.7:8322/cam-s01-a"


def test_error_messages_hide_the_login_in_stream_urls():
    # ffmpeg puts the whole input URL in its errors; the reader logs them and sends them to the hub
    msg = "RuntimeError: rtsps://wrk123:s3cret@203.0.113.7:8322/cam-replay: Connection timed out"
    assert redact(msg) == "RuntimeError: rtsps://***@203.0.113.7:8322/cam-replay: Connection timed out"
    srt = "srt://203.0.113.7:8890?streamid=read:cam-s01-a:USER:PASS&passphrase=abc: I/O error"
    assert "PASS" not in redact(srt) and "abc" not in redact(srt)
    assert redact("stream ended") == "stream ended"


def test_rtsp_and_rtsps_use_tcp_with_a_socket_timeout():
    for url in ("rtsp://127.0.0.1:8554/cam-s01-a", "rtsps://u:p@203.0.113.7:8322/cam-s01-a"):
        opts = _input_options(url)
        assert opts[:2] == ["-rtsp_transport", "tcp"]
        assert "-timeout" in opts


def test_srt_has_no_rtsp_options():
    assert _input_options("srt://203.0.113.7:8890?streamid=read:cam-s01-a") == []


def test_rtsps_checks_the_hub_certificate_when_one_is_given():
    # the hub's certificate is self-signed and names milk-demo-ingest, while the URL holds the hub's IP address
    opts = _input_options(HUB, ca_file="C:/Datagent/hub-ingest.crt", tls_name="milk-demo-ingest")
    assert opts[:2] == ["-rtsp_transport", "tcp"]
    assert opts[opts.index("-tls_verify") + 1] == "1"
    assert opts[opts.index("-ca_file") + 1] == "C:/Datagent/hub-ingest.crt"
    assert opts[opts.index("-verifyhost") + 1] == "milk-demo-ingest"


def test_without_a_certificate_ffmpeg_keeps_its_own_tls_defaults():
    assert not {"-tls_verify", "-ca_file", "-verifyhost"} & set(_input_options(HUB))


def test_plain_rtsp_has_no_tls_options():
    opts = _input_options("rtsp://127.0.0.1:8554/cam-s01-a", ca_file="hub.crt", tls_name="milk-demo-ingest")
    assert not {"-tls_verify", "-ca_file", "-verifyhost"} & set(opts)


def test_reader_gives_the_certificate_to_ffprobe_and_ffmpeg(monkeypatch):
    reader = LatestFrameReader(HUB, ca_file="hub.crt", tls_name="milk-demo-ingest")
    commands = []

    class EndedStream:
        stdout, stderr = io.BytesIO(), io.BytesIO()

        def kill(self):
            pass

        def wait(self):
            pass

    def fake_run(cmd, **_):
        commands.append(cmd)
        probe = b'{"streams": [{"width": 2, "height": 2, "codec_name": "h264"}]}'
        return types.SimpleNamespace(returncode=0, stdout=probe, stderr=b"")

    def fake_popen(cmd, **_):
        commands.append(cmd)
        reader.stop()  # one pass through the loop is enough
        return EndedStream()

    monkeypatch.setattr(stream.subprocess, "run", fake_run)
    monkeypatch.setattr(stream.subprocess, "Popen", fake_popen)
    reader.run()
    assert len(commands) == 2  # ffprobe, then ffmpeg
    for cmd in commands:
        assert cmd[cmd.index("-ca_file") + 1] == "hub.crt"
        assert cmd[cmd.index("-verifyhost") + 1] == "milk-demo-ingest"
        assert cmd.index("-ca_file") < cmd.index(HUB)  # an input option, so before the URL


def test_stop_ends_ffmpeg_at_once_without_a_warning(monkeypatch, caplog):
    # a sampling window ends while ffmpeg waits for the next frame: the worker must not hang until the socket
    # timeout, and closing the stream on purpose is not "stream unavailable"
    killed = threading.Event()

    class Silent(io.RawIOBase):
        def readable(self):
            return True

        def readinto(self, b):
            killed.wait(5)  # no frame comes until ffmpeg is killed
            return 0

    class Ffmpeg:
        def __init__(self):
            self.stdout, self.stderr = Silent(), io.BytesIO()

        def kill(self):
            killed.set()

        def wait(self):
            pass

    probe = b'{"streams": [{"width": 2, "height": 2, "codec_name": "h264"}]}'
    monkeypatch.setattr(stream.subprocess, "run", lambda cmd, **_: types.SimpleNamespace(returncode=0, stdout=probe))
    monkeypatch.setattr(stream.subprocess, "Popen", lambda cmd, **_: Ffmpeg())
    caplog.set_level(logging.WARNING)
    reader = LatestFrameReader(HUB)
    thread = threading.Thread(target=reader.run)
    thread.start()
    deadline = time.time() + 2
    while not reader.connected and time.time() < deadline:
        time.sleep(0.01)
    reader.stop()
    thread.join(2)
    assert not thread.is_alive()
    assert killed.is_set()
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]


class Trickle(io.RawIOBase):
    """Returns at most 3 bytes per read, like a pipe under load."""

    def __init__(self, data: bytes):
        self._data = io.BytesIO(data)

    def readable(self):
        return True

    def readinto(self, b):
        chunk = self._data.read(min(3, len(b)))
        b[: len(chunk)] = chunk
        return len(chunk)


def test_read_exact_collects_a_whole_frame_from_short_reads():
    pipe = Trickle(bytes(range(10)) * 2)
    assert bytes(_read_exact(pipe, 10)) == bytes(range(10))
    assert bytes(_read_exact(pipe, 10)) == bytes(range(10))
    assert _read_exact(pipe, 10) is None  # stream ended
