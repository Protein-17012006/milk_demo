"""The job runner on the counting machine (operations-loop design 5.2).

Every minute it reads live.json, the release folders, the worker's notes about its candidate and this camera's rows
of the model-versions table, asks ops.decide.next_steps what to do, and does it: registers a new release folder,
puts a waiting release beside the live one, takes a candidate out when it stopped itself or draws boxes at night,
and carries out what a team admin asked on the Model page (put live, discard, roll back) by rewriting live.json and
restarting the worker. A switch counts as done when the worker's own start record names the release.

It never decides that a release is better: that is people's answers and the team admin's request. It never rolls
back on its own either: a worker that does not come up with a release is reported on the Model page.

    python -m ops.runner --root C:\\Users\\huyho\\Datagent --camera CAM-S01-A --store-code S01

Runs as the scheduled task milk-ops (worker/windows/run-ops.ps1) with the machine's AWS profile.
"""

from __future__ import annotations

import argparse
import json
import logging
import subprocess
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from boto3.dynamodb.conditions import Attr, Key
from botocore.exceptions import ClientError
from model_versions import STATE_ID

from milk import release
from ops.decide import next_steps, night_rate

log = logging.getLogger("ops.runner")
ICT = timezone(timedelta(hours=7))
NIGHT_EVERY_S = 30 * 60  # the night rule reads many capture rows: twice an hour is enough
NightReader = Callable[[str, str | None], list[dict]]


def _plain(value):
    """DynamoDB's numbers as Python's."""
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, dict):
        return {k: _plain(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_plain(v) for v in value]
    return value


def _for_table(value):
    return json.loads(json.dumps(value), parse_float=Decimal)


class Runner:
    def __init__(
        self,
        root: Path,
        camera_id: str,
        table,
        restart: Callable[[], None],
        night_reader: NightReader | None = None,
        confirm_timeout_s: float = 600.0,
        poll_s: float = 2.0,
        clock: Callable[[], float] = time.time,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.root = Path(root)
        self.camera_id = camera_id
        self.table = table
        self._restart_worker_now = restart
        self._night_reader = night_reader
        self._confirm_timeout_s = confirm_timeout_s
        self._poll_s = poll_s
        self._clock = clock
        self._sleep = sleep
        self._asked_at: datetime | None = None
        self._night_at = 0.0
        self._night_value: float | None = None
        self._night_of: str | None = None

    # --- reading ------------------------------------------------------------------------------------------------

    def _key(self, version_id: str) -> dict:
        return {"camera_id": self.camera_id, "version_id": version_id}

    def _rows(self) -> dict[str, dict]:
        cond = Key("camera_id").eq(self.camera_id)
        resp = self.table.query(KeyConditionExpression=cond)
        items = resp.get("Items", [])
        while "LastEvaluatedKey" in resp:
            resp = self.table.query(KeyConditionExpression=cond, ExclusiveStartKey=resp["LastEvaluatedKey"])
            items.extend(resp.get("Items", []))
        return {item["version_id"]: _plain(item) for item in items}

    def _state(self) -> dict:
        return _plain(self.table.get_item(Key=self._key(STATE_ID)).get("Item") or {})

    def _candidate_status(self) -> dict | None:
        try:
            return json.loads((self.root / release.CANDIDATE_STATUS_FILE).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def _night(self, state: dict, rows: dict[str, dict]) -> float | None:
        candidate = state.get("candidate")
        row = rows.get(candidate or "") or {}
        if not self._night_reader or not candidate or row.get("status") != "parallel":
            return None
        if self._night_of != candidate or self._clock() - self._night_at >= NIGHT_EVERY_S:
            self._night_value = night_rate(self._night_reader(candidate, row.get("parallel_started_at")), candidate)
            self._night_of, self._night_at = candidate, self._clock()
        return self._night_value

    # --- one turn -----------------------------------------------------------------------------------------------

    def tick(self) -> list[tuple]:
        """Reads everything once and carries out the steps it calls for. Returns the steps done. A step that fails
        ends the turn; the next turn reads again and goes on from there."""
        try:
            pointer = release.read_pointer(self.root)
        except ValueError as exc:
            log.warning("nothing done: %s", exc)
            return []
        rows = self._rows()
        state = {k: v for k, v in rows.pop(STATE_ID, {}).items() if k not in ("camera_id", "version_id")}
        steps = next_steps(
            pointer,
            state,
            rows,
            release.release_ids(self.root),
            self._candidate_status(),
            self._night(state, rows),
        )
        done: list[tuple] = []
        for step in steps:
            try:
                getattr(self, "_do_" + step[0])(*step[1:])
            except Exception:  # noqa: BLE001 - the next turn reads the state again and goes on
                log.exception("step %s failed", step)
                break
            log.info("done: %s", step)
            done.append(step)
        self._heartbeat()
        return done

    def _heartbeat(self) -> None:
        try:
            self._set(STATE_ID, {"runner_seen_at": self._now()}, must_exist=True)
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") != "ConditionalCheckFailedException":
                raise

    # --- writing ------------------------------------------------------------------------------------------------

    @staticmethod
    def _now() -> str:
        return datetime.now(ICT).isoformat(timespec="seconds")

    def _set(self, version_id: str, values: dict, remove: tuple[str, ...] = (), must_exist: bool = False) -> None:
        names = {f"#{i}": k for i, k in enumerate([*values, *remove])}
        placeholders = {v: k for k, v in names.items()}
        parts = []
        if values:
            parts.append("SET " + ", ".join(f"{placeholders[k]} = :{placeholders[k][1:]}" for k in values))
        if remove:
            parts.append("REMOVE " + ", ".join(placeholders[k] for k in remove))
        kwargs = {
            "Key": self._key(version_id),
            "UpdateExpression": " ".join(parts),
            "ExpressionAttributeNames": names,
        }
        if values:
            kwargs["ExpressionAttributeValues"] = {f":{placeholders[k][1:]}": _for_table(v) for k, v in values.items()}
        if must_exist:
            kwargs["ConditionExpression"] = "attribute_exists(version_id)"
        self.table.update_item(**kwargs)

    def _put_new(self, version_id: str, item: dict) -> None:
        try:
            self.table.put_item(
                Item={**self._key(version_id), **_for_table(item)},
                ConditionExpression="attribute_not_exists(version_id)",
            )
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") != "ConditionalCheckFailedException":
                raise

    def _answer(self, request_id: str, ok: bool, message: str) -> None:
        result = {"request_id": request_id, "ok": ok, "message": message, "at": self._now()}
        self._set(STATE_ID, {"last_result": result})

    def _restart(self) -> None:
        self._asked_at = datetime.now(UTC).replace(microsecond=0)  # the start record has whole seconds
        self._restart_worker_now()

    # --- the steps of ops.decide.next_steps ------------------------------------------------------------------------

    def _do_init_state(self, pointer: release.Pointer) -> None:
        item = {"live": pointer.live}
        if pointer.previous:
            item["previous"] = pointer.previous
        if pointer.candidate:
            item["candidate"] = pointer.candidate
        self._put_new(STATE_ID, item)

    def _do_register(self, release_id: str) -> None:
        try:
            found = release.load_release(self.root, release_id)
        except ValueError as exc:  # shown on the Model page as it is; not read again every minute
            self._put_new(
                release_id, {"status": "stopped", "stopped_reason": str(exc)[:300], "created_at": self._now()}
            )
            return
        live = release.read_pointer(self.root).live
        item = {
            "kind": found.kind,
            "status": "live" if release_id == live else "candidate",
            "criteria": found.criteria,
            "created_at": found.created_at or self._now(),
        }
        if found.parent:
            item["parent"] = found.parent
        self._put_new(release_id, item)

    def _do_adopt(self, pointer: release.Pointer) -> None:
        """live.json was changed by hand: the table follows what the worker will load."""
        old_live = self._state().get("live")
        values = {"live": pointer.live}
        remove = []
        for name in ("previous", "candidate"):
            if getattr(pointer, name):
                values[name] = getattr(pointer, name)
            else:
                remove.append(name)
        self._set(STATE_ID, values, tuple(remove))
        if old_live != pointer.live:
            self._set(pointer.live, {"status": "live"})
            if old_live:
                self._set(old_live, {"status": "replaced"})

    def _do_start_parallel(self, release_id: str) -> None:
        pointer = release.read_pointer(self.root)
        release.write_pointer(self.root, release.Pointer(pointer.live, pointer.previous, release_id))
        self._set(release_id, {"status": "parallel", "parallel_started_at": self._now()})
        self._set(STATE_ID, {"candidate": release_id})
        self._restart()

    def _do_stop(self, release_id: str, reason: str) -> None:
        pointer = release.read_pointer(self.root)
        if pointer.candidate == release_id:
            release.write_pointer(self.root, release.Pointer(pointer.live, pointer.previous, None))
        self._set(release_id, {"status": "stopped", "stopped_reason": reason})
        self._set(STATE_ID, {}, remove=("candidate",))
        self._restart()

    def _do_fail(self, request_id: str, message: str) -> None:
        self._answer(request_id, False, message)

    def _do_point(self, pointer: release.Pointer) -> None:
        release.write_pointer(self.root, pointer)

    def _do_restart_worker(self) -> None:
        self._restart()

    def _do_sync_status(self, release_id: str, numbers: dict) -> None:
        self._set(release_id, {"worker": numbers})

    def _do_confirm(self, request_id: str, version: str) -> None:
        """Waits for the worker's start record to name `version` (and the pointer's candidate), then writes what the
        request changed and answers it. A worker that does not get there in time is reported; nothing is undone."""
        wanted = release.read_pointer(self.root)
        asked_at = self._asked_at or datetime.now(UTC).replace(microsecond=0)
        deadline = self._clock() + self._confirm_timeout_s
        seen = None
        while True:
            seen = release.read_worker_status(self.root)
            if (
                seen
                and datetime.fromisoformat(seen["started_at"]) >= asked_at
                and seen.get("live") == version
                and (seen.get("candidate") or None) == wanted.candidate
            ):
                break
            if self._clock() >= deadline:
                said = f"its last start was with {seen.get('live')}" if seen else "it has written no start record"
                self._answer(request_id, False, f"The worker did not start with {version}: {said}.")
                return
            self._sleep(self._poll_s)
        state = self._state()
        request = state.get("request") or {}
        old_live, action = state.get("live"), request.get("action")
        decided = {"decided_by": request.get("by", ""), "decided_at": request.get("at", "")}
        if action == "put_live":
            self._set(version, {"status": "live", **decided})
            if old_live and old_live != version:
                self._set(old_live, {"status": "replaced"})
            self._set(STATE_ID, {"live": version, "previous": old_live}, remove=("candidate",))
        elif action == "rollback":
            self._set(version, {"status": "live"})
            if old_live and old_live != version:
                self._set(old_live, {"status": "replaced"})
            self._set(STATE_ID, {"live": version, "previous": old_live}, remove=("candidate",))
        elif action == "discard":
            self._set(request["version_id"], {"status": "discarded", **decided})
            self._set(STATE_ID, {}, remove=("candidate",))
        self._answer(request_id, True, "")


def restart_worker_task() -> None:
    """Stops and starts the scheduled task that keeps the counting worker running."""
    command = "Stop-ScheduledTask -TaskName milk-worker; Start-ScheduledTask -TaskName milk-worker"
    subprocess.run(["powershell", "-NoProfile", "-Command", command], check=True, timeout=180)


def night_reader_for(captures_table, camera_id: str, store_code: str) -> NightReader:
    """Reads, from the backend's captures table, the captures of this camera taken with the display away that a
    candidate has read since its parallel run started (capture ids are CAP-<store code>-<YYYYMMDD>-<HHMMSS>)."""

    def read(version: str, since: str | None) -> list[dict]:
        day = (since or "")[:10].replace("-", "")
        low, high = f"CAP-{store_code}-{day}", f"CAP-{store_code}-~"
        kwargs = {
            "KeyConditionExpression": Key("camera_id").eq(camera_id) & Key("capture_id").between(low, high),
            "FilterExpression": Attr("candidate_version").eq(version) & Attr("display_visible").eq(False),
            "ProjectionExpression": "display_visible, candidate_version, candidate_detections_json",
        }
        resp = captures_table.query(**kwargs)
        items = resp.get("Items", [])
        while "LastEvaluatedKey" in resp:
            resp = captures_table.query(ExclusiveStartKey=resp["LastEvaluatedKey"], **kwargs)
            items.extend(resp.get("Items", []))
        return [_plain(item) for item in items]

    return read


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Carry out the Model page's requests on the counting machine.")
    parser.add_argument(
        "--root", required=True, type=Path, help="the counting machine's folder; releases are in <root>/releases"
    )
    parser.add_argument("--camera", required=True, help="camera id, e.g. CAM-S01-A")
    parser.add_argument("--store-code", required=True, help="store code in capture ids, e.g. S01")
    parser.add_argument("--env", default="development", help="backend environment in the table names")
    parser.add_argument("--region", default="ap-southeast-1")
    parser.add_argument("--interval", type=float, default=60.0, help="seconds between turns")
    parser.add_argument("--once", action="store_true", help="one turn, then exit")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    import boto3

    dynamodb = boto3.resource("dynamodb", region_name=args.region)
    captures = dynamodb.Table(f"milk-backend-{args.env}-captures")
    runner = Runner(
        args.root / "releases",
        args.camera,
        dynamodb.Table(f"milk-backend-{args.env}-model-versions"),
        restart=restart_worker_task,
        night_reader=night_reader_for(captures, args.camera, args.store_code),
    )
    while True:
        try:
            runner.tick()
        except Exception:  # noqa: BLE001 - AWS or the disk may be away for a while; try again next turn
            log.exception("turn failed")
        if args.once:
            return
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
