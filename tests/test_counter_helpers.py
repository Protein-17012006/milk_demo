import numpy as np

from milk.counter import candidate_deadline, encode_jpeg, normalise, roi_pixels, status_payload
from milk.cvoutput import Detection


def test_no_roi_is_the_whole_frame():
    assert roi_pixels(None, 3840, 2160) == (0, 0, 3840, 2160)


def test_roi_fractions_become_pixels_and_stay_inside_the_frame():
    assert roi_pixels((0.25, 0.5, 0.5, 0.5), 3840, 2160) == (960, 1080, 1920, 1080)
    assert roi_pixels((0.9, 0.9, 0.5, 0.5), 1000, 1000) == (900, 900, 100, 100)


def test_normalise_converts_numpy_numbers_and_shifts_to_frame_coordinates():
    det = Detection("TMP-MLK-VNM-01", "x", np.float32(0.8125), tuple(np.array([10.4, 20.6, 30, 40], dtype=np.float32)))
    (out,) = normalise([det], dx=960, dy=1080)
    assert out.box == (970, 1101, 30, 40)
    assert all(type(v) is int for v in out.box)
    assert type(out.confidence) is float


def test_encode_jpeg_caps_the_width():
    image = np.zeros((2160, 3840, 3), dtype=np.uint8)
    jpeg, width, height = encode_jpeg(image, 80, max_width=1920)
    assert jpeg[:2] == b"\xff\xd8"
    assert (width, height) == (1920, 1080)


class OpenStream:
    connected = True
    last_error = None
    stream_info = {"codec": "h264", "width": 2560, "height": 1440}


SAMPLING = {"every_s": 300.0, "for_s": 30.0, "next_at": 900.0}


def test_status_between_windows_says_when_the_stream_opens_again():
    p = status_payload("CAM-S01-A", None, "long+slide", "cuda", "huyhoang-gpu", True, 0, SAMPLING)
    assert (p["connected"], p["stream"], p["last_error"]) == (False, {}, None)
    assert p["sampling"] == SAMPLING
    assert p["worker"] == "huyhoang-gpu" and p["frames_last_minute"] == 0


def test_status_in_a_window_comes_from_the_reader():
    p = status_payload("CAM-S01-A", OpenStream(), "long+slide", "cuda", "huyhoang-gpu", True, 42, SAMPLING)
    assert p["connected"] is True and p["stream"]["codec"] == "h264" and p["frames_last_minute"] == 42


def test_continuous_status_keeps_its_old_keys():
    p = status_payload("CAM-S01-A", OpenStream(), "long", "cuda", "huyhoang-gpu", False, 10, None)
    assert set(p) == {
        "camera_id",
        "connected",
        "last_error",
        "stream",
        "pipeline",
        "device",
        "worker",
        "blur",
        "frames_last_minute",
    }


def test_the_candidate_must_be_done_five_seconds_before_the_next_window():
    assert candidate_deadline(1000.0) == 995.0
