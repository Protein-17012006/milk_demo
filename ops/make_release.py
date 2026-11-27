"""Makes a release folder (operations-loop design 5.2): the model settings of the worker's env file, or a copy of
another release with some settings changed.

    python -m ops.make_release --root C:\\Users\\huyho\\Datagent\\releases --id long-store-v1-det+slide-v3 ^
        --kind baseline --from-env C:\\Users\\huyho\\Datagent\\worker.env
    python -m ops.make_release --root ... --id slide-conf35-20261128 --kind rules ^
        --from-release long-store-v1-det+slide-v3 --set MILK_SLIDE_CONF=0.35

A release is never overwritten: its id is the model_version on every capture it read. The very first release made
from the env file also becomes the live one (live.json), since it is what the worker runs already; after that,
making a release changes nothing about what is live: the job runner finds the folder, runs it beside the live
release, and a team admin decides on the Model page.
"""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime
from pathlib import Path

from milk import config, release


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Make a release folder for the counting worker.")
    parser.add_argument("--root", required=True, type=Path, help="the releases folder (MILK_RELEASES_DIR)")
    parser.add_argument("--id", required=True, help="the release's name: the model_version of its captures")
    parser.add_argument("--kind", required=True, choices=sorted(release.DEFAULT_CRITERIA))
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--from-env", type=Path, help="take the model settings of this env file")
    source.add_argument("--from-release", help="copy the settings of this release; it becomes the parent")
    parser.add_argument("--set", action="append", default=[], metavar="KEY=VALUE", help="a model setting to change")
    parser.add_argument("--criteria", help="JSON object: criteria that differ from the kind's defaults")
    args = parser.parse_args(argv)

    folder = args.root / args.id
    if folder.exists():
        parser.error(f"{folder} exists: a release is never overwritten; choose another id")
    if args.from_env:
        pairs = config.read_env_file(str(args.from_env))
        env = {k: v for k, v in pairs.items() if release.is_model_key(k) and k != "MILK_MODEL_VERSION"}
        parent = None
    else:
        try:
            base = release.load_release(args.root, args.from_release)
        except ValueError as exc:
            parser.error(str(exc))
        env, parent = dict(base.env), base.id
    for pair in args.set:
        key, sep, value = pair.partition("=")
        if not sep or not key.strip():
            parser.error(f"--set needs KEY=VALUE, not {pair!r}")
        env[key.strip()] = value.strip()
    try:
        criteria = {**release.DEFAULT_CRITERIA[args.kind], **(json.loads(args.criteria) if args.criteria else {})}
    except ValueError as exc:
        parser.error(f"--criteria is not JSON: {exc}")

    body = {
        "id": args.id,
        "parent": parent,
        "kind": args.kind,
        "env": env,
        "criteria": criteria,
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
    }
    folder.mkdir(parents=True)
    (folder / release.RELEASE_FILE).write_text(json.dumps(body, indent=1, ensure_ascii=False), encoding="utf-8")
    try:
        release.load_release(args.root, args.id)  # the worker's own reader must accept what was written
    except ValueError as exc:
        shutil.rmtree(folder)
        parser.error(str(exc))
    first = args.from_env and not (args.root / release.POINTER_FILE).exists()
    if first:
        release.write_pointer(args.root, release.Pointer(live=args.id))
    print(f"release {args.id} written to {folder}" + (" and set as the live release" if first else ""))


if __name__ == "__main__":
    main()
