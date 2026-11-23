"""Build the website's product thumbnails, one square PNG per SKU, named as image_url in backend/common.py.

Sources, both on HUYHOANG:
  * 12 milk cartons: the printed label face of each carton model in Datagent/extracted/model_milk/*.glb. Each face
    is a photo of the real carton; the milk model was trained on renders of the same models.
  * 4 Slide cans: Lotte Mart's product photos in sku3d/_web, the photos the Slide labels in sku3d/slide/labels
    were made from for training.

usage: python scripts/make_product_thumbnails.py MODEL_MILK_DIR SLIDE_WEB_DIR frontend/public/images/products
"""

from __future__ import annotations

import argparse
import io
import json
import struct
from pathlib import Path

from PIL import Image

SIZE = 176  # 4x the 44 px thumbnail on the Products page
FIT = 160  # longest side of the product inside the square

# file stem -> (carton model, material that carries the printed label), as CLASSES in cctv_dataset/build_dataset.py
MILK = {
    "th-true-milk-fresh-milk-sweetened-180ml": ("TH_CD_Milk", "front"),
    "th-true-milk-fresh-milk-low-sugar-180ml": ("TH_ID_Milk", "left"),
    "vinamilk-100-fresh-milk-unsweetened-180ml": ("EST_Milk", "front"),
    "vinamilk-100-fresh-milk-low-sugar-180ml": ("Blue_Milk", "front"),
    "vinamilk-100-fresh-milk-sweetened-180ml": ("Green_Milk", "front"),
    "vinamilk-100-skimmed-chocolate-milk-180ml": ("chocolate_Milk", "front"),
    "vinamilk-100-low-fat-banana-milk-180ml": ("Bannana_Milk", "front"),
    "vinamilk-100-skimmed-melon-milk-180ml": ("Orange_Milk", "front"),
    "vinamilk-high-calcium-soy-milk-low-sugar-180ml": ("Bean_Milk", "front"),
    "vinamilk-almond-soy-milk-low-sugar-180ml": ("HN_Milk", "front"),
    "vinamilk-black-sesame-soy-milk-low-sugar-180ml": ("Grey_Milk", "front"),
    "vinamilk-9-nuts-milk-low-sugar-180ml": ("Seed9_Milk", "front"),
}

# file stem -> photo in sku3d/_web (the one named in sku3d/slide/labels/<flavour>_label.json)
SLIDE = {
    "slide-original-145g": "lottemart_original145/8934680011198-1.jpg.webp",
    "slide-sour-cream-onion-150g": "lottemart_scm/img.webp",
    "slide-cheese-145g": "lottemart_cheese145/8934680011709-1.jpg.webp",
    "slide-hot-spicy-160g": "lottemart_hot160/8934680011228-tet-1.jpg.webp",
}


def glb_face(path: Path, material: str) -> Image.Image:
    """Base-colour texture of the named material in a binary glTF file."""
    data = path.read_bytes()
    _magic, _version, length = struct.unpack_from("<4sII", data, 0)
    offset, doc, blob = 12, {}, b""
    while offset < length:
        size, kind = struct.unpack_from("<II", data, offset)
        chunk = data[offset + 8 : offset + 8 + size]
        if kind == 0x4E4F534A:  # JSON chunk
            doc = json.loads(chunk)
        elif kind == 0x004E4942:  # BIN chunk
            blob = chunk
        offset += 8 + size
    mat = next(m for m in doc["materials"] if m.get("name", "").lower() == material)
    texture = doc["textures"][mat["pbrMetallicRoughness"]["baseColorTexture"]["index"]]
    view = doc["bufferViews"][doc["images"][texture["source"]]["bufferView"]]
    start = view.get("byteOffset", 0)
    return Image.open(io.BytesIO(blob[start : start + view["byteLength"]]))


def on_white(im: Image.Image) -> Image.Image:
    im = im.convert("RGBA")
    out = Image.new("RGB", im.size, "white")
    out.paste(im, mask=im.getchannel("A"))
    return out


def product_box(im: Image.Image) -> tuple[int, int, int, int]:
    """Box around the product: pixels clearly darker or more colourful than the white backdrop.

    The retailer's light-grey watermark stays under both limits, so it does not widen the box."""
    dark = im.convert("L").point(lambda v: 255 if v < 200 else 0)
    colourful = im.convert("HSV").getchannel("S").point(lambda s: 255 if s > 60 else 0)
    return Image.composite(dark, colourful, dark).getbbox() or (0, 0, im.width, im.height)


def thumbnail(im: Image.Image) -> Image.Image:
    im = on_white(im)
    im = im.crop(product_box(im))
    im.thumbnail((FIT, FIT), Image.Resampling.LANCZOS)
    out = Image.new("RGB", (SIZE, SIZE), "white")
    out.paste(im, ((SIZE - im.width) // 2, (SIZE - im.height) // 2))
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("model_milk", type=Path, help="Datagent/extracted/model_milk")
    ap.add_argument("slide_web", type=Path, help="sku3d/_web")
    ap.add_argument("out", type=Path, help="frontend/public/images/products")
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    sources = {stem: glb_face(args.model_milk / f"{model}.glb", face) for stem, (model, face) in MILK.items()}
    sources |= {stem: Image.open(args.slide_web / rel) for stem, rel in SLIDE.items()}
    for stem, im in sources.items():
        path = args.out / f"{stem}.png"
        thumbnail(im).save(path, optimize=True)
        print(f"{path}  {path.stat().st_size} B")


if __name__ == "__main__":
    main()
