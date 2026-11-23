import os

import pytest

from milk import config


def test_env_file_fills_missing_settings_but_never_overrides(tmp_path, monkeypatch):
    env = tmp_path / "worker.env"
    env.write_text(
        "# comment line\n"
        "MILK_TEST_A=from-file\n"
        "MILK_TEST_B = 'quoted value'\n"
        "MILK_TEST_C=from-file\n"
        "not a setting\n",
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
    assert config.default_model_version("long+slide", "~/Desktop/Datagent/slide_pilot/runs_v3/best.pt") == "long+slide:runs_v3"
    assert config.default_model_version("long", "") == "long"
    monkeypatch.setenv("MILK_PIPELINE", "long+slide")
    monkeypatch.setenv("MILK_SLIDE_WEIGHTS", "/home/long/Desktop/Datagent/slide_pilot/runs_v3/best.pt")
    assert config.load().model_version == "long+slide:runs_v3"
