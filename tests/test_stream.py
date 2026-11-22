import io

from milk.stream import _input_options, _read_exact, redact


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


class Trickle(io.RawIOBase):
    """Returns at most 3 bytes per read, like a pipe under load."""

    def __init__(self, data: bytes):
        self._data = io.BytesIO(data)

    def readable(self):
        return True

    def readinto(self, b):
        chunk = self._data.read(min(3, len(b)))
        b[:len(chunk)] = chunk
        return len(chunk)


def test_read_exact_collects_a_whole_frame_from_short_reads():
    pipe = Trickle(bytes(range(10)) * 2)
    assert bytes(_read_exact(pipe, 10)) == bytes(range(10))
    assert bytes(_read_exact(pipe, 10)) == bytes(range(10))
    assert _read_exact(pipe, 10) is None  # stream ended
