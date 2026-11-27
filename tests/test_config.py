import os

import pytest
from test_release import write_release

from milk import config, release


def test_env_file_fills_missing_settings_but_never_overrides(tmp_path, monkeypatch):
    env = tmp_path / "worker.env"
    env.write_text(
        "# comment line\nMILK_TEST_A=from-file\nMILK_TEST_B = 'quoted value'\nMILK_TEST_C=from-file\nnot a setting\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("MILK_TEST_C", "from-environment")
    for key in ("MILK_TEST_A", "MILK_TEST_B"):
        monkeypatch.delenv(key, raising=False)
    config.load_env_file(str(env))
    assert os.environ["MILK_TEST_A"] == "from-file"
    assert os.environ["MILK_TEST_B"] == "quoted value"
    assert os.environ["MILK_TEST_C"] == "from-environment"
    for key in ("MILK_TEST_A", "MILK_TEST_B"):
        monkeypatch.delenv(key, raising=False)


def test_hub_url_falls_back_to_the_old_name(monkeypatch):
    monkeypatch.delenv("MILK_HUB_URL", raising=False)
    monkeypatch.setenv("MILK_WEB_INTERNAL_URL", "http://127.0.0.1:8080")
    assert config.load().hub_url == "http://127.0.0.1:8080"
    monkeypatch.setenv("MILK_HUB_URL", "https://example.cloudfront.net")
    assert config.load().hub_url == "https://example.cloudfront.net"


@pytest.mark.parametrize("raw", ["0.1,0.2,0.8", "1.2,0,0.5,0.5", "0,0,0,0.5"])
def test_bad_roi_is_rejected(monkeypatch, raw):
    monkeypatch.setenv("MILK_ROI", raw)
    with pytest.raises(ValueError):
        config.load()


def test_model_version_comes_from_the_env(monkeypatch):
    monkeypatch.setenv("MILK_MODEL_VERSION", "long-2026-10-13+slide-v3")
    assert config.load().model_version == "long-2026-10-13+slide-v3"


def test_model_version_defaults_to_pipeline_and_slide_run(monkeypatch):
    monkeypatch.delenv("MILK_MODEL_VERSION", raising=False)
    assert (
        config.default_model_version("long+slide", "~/Desktop/Datagent/slide_pilot/runs_v3/best.pt")
        == "long+slide:runs_v3"
    )
    assert config.default_model_version("long", "") == "long"
    monkeypatch.setenv("MILK_PIPELINE", "long+slide")
    monkeypatch.setenv("MILK_SLIDE_WEIGHTS", "/home/long/Desktop/Datagent/slide_pilot/runs_v3/best.pt")
    assert config.load().model_version == "long+slide:runs_v3"


@pytest.mark.parametrize(
    ("raw", "expected"), [(None, True), ("true", True), ("false", False), ("0", False), ("OFF", False)]
)
def test_cookie_secure_flag(monkeypatch, raw, expected):
    if raw is None:
        monkeypatch.delenv("MILK_COOKIE_SECURE", raising=False)
    else:
        monkeypatch.setenv("MILK_COOKIE_SECURE", raw)
    assert config.load().cookie_secure is expected


def test_environment_and_version_come_from_the_pipeline(monkeypatch):
    monkeypatch.setenv("MILK_ENVIRONMENT", "staging")
    monkeypatch.setenv("MILK_VERSION", "1d58130")
    s = config.load()
    assert (s.environment, s.version) == ("staging", "1d58130")


def test_sampling_defaults_to_continuous(monkeypatch):
    monkeypatch.delenv("MILK_SAMPLE_EVERY_S", raising=False)
    monkeypatch.delenv("MILK_SAMPLE_FOR_S", raising=False)
    s = config.load()
    assert (s.sample_every_s, s.sample_for_s) == (0.0, 30.0)


def test_sampling_settings_from_env(monkeypatch):
    monkeypatch.setenv("MILK_SAMPLE_EVERY_S", "300")
    monkeypatch.setenv("MILK_SAMPLE_FOR_S", "30")
    s = config.load()
    assert (s.sample_every_s, s.sample_for_s) == (300.0, 30.0)


@pytest.mark.parametrize("every, window", [("300", "300"), ("300", "0"), ("60", "90")])
def test_sampling_window_must_fit_the_period(monkeypatch, every, window):
    monkeypatch.setenv("MILK_SAMPLE_EVERY_S", every)
    monkeypatch.setenv("MILK_SAMPLE_FOR_S", window)
    with pytest.raises(ValueError, match="MILK_SAMPLE_FOR_S"):
        config.load()


def test_stream_certificate_settings(monkeypatch):
    monkeypatch.delenv("MILK_STREAM_CA_FILE", raising=False)
    monkeypatch.delenv("MILK_STREAM_TLS_NAME", raising=False)
    s = config.load()
    assert (s.stream_ca_file, s.stream_tls_name) == (None, None)
    monkeypatch.setenv("MILK_STREAM_CA_FILE", "C:/Users/huyho/Datagent/hub-ingest.crt")
    monkeypatch.setenv("MILK_STREAM_TLS_NAME", "milk-demo-ingest")
    s = config.load()
    assert (s.stream_ca_file, s.stream_tls_name) == ("C:/Users/huyho/Datagent/hub-ingest.crt", "milk-demo-ingest")


def test_display_settings_default_off(monkeypatch):
    for key in ("MILK_DISPLAY_ZONE", "MILK_DISPLAY_MIN", "MILK_DISPLAY_REFS"):
        monkeypatch.delenv(key, raising=False)
    s = config.load()
    assert s.display_zone is None and s.display_min == 0.6 and s.display_refs is None


def test_display_settings_from_env(monkeypatch):
    monkeypatch.setenv("MILK_DISPLAY_ZONE", "0.336,0.083,0.242,0.361")
    monkeypatch.setenv("MILK_DISPLAY_MIN", "0.7")
    monkeypatch.setenv("MILK_DISPLAY_REFS", "C:/refs/display.npz")
    s = config.load()
    assert s.display_zone == (0.336, 0.083, 0.242, 0.361)
    assert s.display_min == 0.7 and s.display_refs == "C:/refs/display.npz"


def test_bad_display_zone_is_rejected(monkeypatch):
    monkeypatch.setenv("MILK_DISPLAY_ZONE", "0.1,0.2,0.8")
    with pytest.raises(ValueError, match="MILK_DISPLAY_ZONE"):
        config.load()


def test_load_takes_the_live_release(tmp_path, monkeypatch):
    write_release(tmp_path, "v1", env={"MILK_PIPELINE": "null"})
    release.write_pointer(tmp_path, release.Pointer(live="v1", previous=None, candidate=None))
    monkeypatch.setenv("MILK_RELEASES_DIR", str(tmp_path))
    monkeypatch.setenv("MILK_PIPELINE", "long+slide")
    monkeypatch.setenv("MILK_SLIDE_WEIGHTS", "stale.pt")
    monkeypatch.setenv("MILK_MODEL_VERSION", "by-hand")
    settings = config.load()
    assert (settings.pipeline, settings.model_version) == ("null", "v1")
    assert "MILK_SLIDE_WEIGHTS" not in os.environ


def test_load_stops_when_the_live_release_is_missing(tmp_path, monkeypatch):
    release.write_pointer(tmp_path, release.Pointer(live="gone", previous=None, candidate=None))
    monkeypatch.setenv("MILK_RELEASES_DIR", str(tmp_path))
    with pytest.raises(ValueError, match="gone"):
        config.load()


def test_load_without_releases_dir_is_unchanged(monkeypatch):
    monkeypatch.delenv("MILK_RELEASES_DIR", raising=False)
    monkeypatch.setenv("MILK_PIPELINE", "null")
    monkeypatch.setenv("MILK_MODEL_VERSION", "by-hand")
    assert config.load().model_version == "by-hand"


def test_read_env_file_gives_the_pairs_and_leaves_the_environment_alone(tmp_path, monkeypatch):
    env = tmp_path / "worker.env"
    env.write_text("# comment\nMILK_TEST_A=1\nMILK_TEST_B = 'two'\nnot a setting\n", encoding="utf-8")
    monkeypatch.delenv("MILK_TEST_A", raising=False)
    assert config.read_env_file(str(env)) == {"MILK_TEST_A": "1", "MILK_TEST_B": "two"}
    assert "MILK_TEST_A" not in os.environ
