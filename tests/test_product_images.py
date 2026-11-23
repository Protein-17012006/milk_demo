"""Product photos: every SKU in the seed names its own photo, and that photo ships with the website."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

import common  # noqa: E402

PUBLIC = ROOT / "frontend" / "public"


def test_each_seeded_sku_names_a_photo_that_ships_with_the_website():
    for alias, meta in common.DEFAULT_ALIAS_MAP.items():
        url = meta.get("image_url")
        assert url and url.startswith("/images/products/"), alias
        assert (PUBLIC / url.removeprefix("/")).is_file(), (alias, url)


def test_no_two_skus_share_a_photo():
    # 24/11: all Vinamilk rows showed one shared photo, and three nut milks showed another product's photo
    urls = [meta["image_url"] for meta in common.DEFAULT_ALIAS_MAP.values()]
    assert len(set(urls)) == len(urls)
