from milk.sampling import Sampler


class FakeReader:
    def __init__(self):
        self.started = 0
        self.stopped = 0

    def start(self):
        self.started += 1

    def stop(self):
        self.stopped += 1


def make(every=300, window=30):
    made = []

    def open_reader():
        made.append(FakeReader())
        return made[-1]

    return Sampler(every, window, open_reader), made


def test_windows_follow_the_clock():
    s, _ = make()
    assert s.in_window(600) and s.in_window(629.9)
    assert not s.in_window(630) and not s.in_window(899)


def test_next_window_starts_on_the_next_multiple():
    s, _ = make()
    assert s.next_start(630) == 900
    assert s.next_start(600) == 900


def test_one_reader_per_window_closed_once_at_its_end():
    s, made = make()
    r1, opened = s.reader_at(600)
    assert opened and r1 is made[0] and r1.started == 1
    assert s.reader_at(615) == (r1, False)
    assert s.reader_at(630) == (None, False)
    assert s.reader_at(700) == (None, False)
    assert r1.stopped == 1
    r2, opened = s.reader_at(900)
    assert opened and r2 is made[1] and len(made) == 2


def test_a_new_window_replaces_a_reader_left_open():
    s, made = make()
    s.reader_at(600)
    r2, opened = s.reader_at(905)  # the loop never saw the gap between the windows
    assert opened and r2 is made[1] and made[0].stopped == 1


def test_continuous_keeps_one_reader_open():
    s, made = make(every=0)
    r, opened = s.reader_at(1)
    assert opened and s.continuous
    assert s.reader_at(10_000) == (r, False)
    assert len(made) == 1 and r.stopped == 0
    assert s.describe(10_000) is None


def test_describe_tells_when_the_next_window_opens():
    s, _ = make()
    d = s.describe(630)
    assert (d["every_s"], d["for_s"], d["next_at"]) == (300, 30, 900)


def test_describe_says_whether_a_window_is_open():
    # the hub must tell "between windows" (fine) from "in a window but no stream" (an outage)
    s, _ = make()
    s.reader_at(600)
    assert s.describe(600)["open"] is True
    s.reader_at(630)
    assert s.describe(630)["open"] is False


def test_frames_of_the_last_window_are_reported():
    s, _ = make()
    assert s.describe(100)["last_window_frames"] is None  # no window has ended yet
    s.reader_at(600)
    for _ in range(3):
        s.note_frame()
    assert s.frames_in_window == 3
    s.reader_at(630)  # the window ends
    assert s.describe(631)["last_window_frames"] == 3
    s.reader_at(900)
    assert s.frames_in_window == 0
    s.reader_at(930)  # a window that got no frame: the camera or the hub is down
    assert s.describe(931)["last_window_frames"] == 0


def test_close_stops_the_open_reader_once():
    s, made = make()
    s.reader_at(600)
    s.close()
    s.close()
    assert made[0].stopped == 1
