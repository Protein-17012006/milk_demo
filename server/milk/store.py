"""Writes captures to S3 (blurred frame, result JSON) and DynamoDB in a background thread, and a candidate
release's result for a capture as one more S3 file beside the capture's own.

The counting loop never waits on AWS: if the queue is full, the capture is dropped and
logged, and the dashboard keeps running.
"""

from __future__ import annotations

import json
import logging
import queue
import threading
import time

log = logging.getLogger(__name__)

RETENTION_DAYS = 30


class Persistence(threading.Thread):
    def __init__(self, region: str, bucket: str, table: str, maxsize: int = 20) -> None:
        super().__init__(daemon=True, name="persistence")
        import boto3

        self._s3 = boto3.client("s3", region_name=region)
        self._table = boto3.resource("dynamodb", region_name=region).Table(table)
        self._bucket = bucket
        self._queue: queue.Queue = queue.Queue(maxsize=maxsize)
        self.saved = 0
        self.dropped = 0
        self.last_error: str | None = None

    def submit(self, record: dict, jpeg: bytes | None) -> None:
        try:
            self._queue.put_nowait(("capture", record, jpeg))
        except queue.Full:
            self.dropped += 1
            log.warning("persistence queue full; dropped %s", record.get("capture_id"))

    def submit_candidate(self, payload: dict) -> None:
        """A candidate release's boxes for one capture. Same queue, same rule: full means dropped."""
        try:
            self._queue.put_nowait(("candidate", payload, None))
        except queue.Full:
            self.dropped += 1
            log.warning("persistence queue full; dropped the candidate result of %s", payload.get("capture_id"))

    def run(self) -> None:
        while True:
            kind, record, jpeg = self._queue.get()
            try:
                self._handle(kind, record, jpeg)
                self.last_error = None
            except Exception as exc:  # noqa: BLE001
                self.last_error = f"{type(exc).__name__}: {exc}"
                log.exception("could not save %s", record.get("capture_id"))

    def _handle(self, kind: str, record: dict, jpeg: bytes | None) -> None:
        if kind == "candidate":
            self._save_candidate(record)
        else:
            self._save(record, jpeg)
            self.saved += 1

    def _save_candidate(self, payload: dict) -> None:
        """One file and nothing else: the hub's own table and dashboard know only the live release."""
        self._s3.put_object(
            Bucket=self._bucket,
            Key=candidate_key(payload),
            Body=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            ContentType="application/json",
        )

    def _save(self, record: dict, jpeg: bytes | None) -> None:
        prefix = f"{record['camera_id']}/{record['capture_timestamp'][:10]}"
        image_key = ""
        if jpeg:
            image_key = f"frames/{prefix}/{record['image_filename']}"
            self._s3.put_object(Bucket=self._bucket, Key=image_key, Body=jpeg, ContentType="image/jpeg")
        body = json.dumps({**record, "image_key": image_key}, ensure_ascii=False).encode("utf-8")
        self._s3.put_object(
            Bucket=self._bucket,
            Key=f"results/{prefix}/{record['capture_id']}.json",
            Body=body,
            ContentType="application/json",
        )
        self._table.put_item(Item=table_item(record, image_key, int(time.time()) + RETENTION_DAYS * 86400))


def candidate_key(payload: dict) -> str:
    """Beside the capture's result file, under the same results/ prefix that is announced to the backend."""
    day = payload["capture_timestamp"][:10]
    return f"results/{payload['camera_id']}/{day}/{payload['capture_id']}.candidate.json"


def table_item(record: dict, image_key: str, expires_at: int) -> dict:
    """The DynamoDB row of one capture. The S3 result file holds the same record, so
    milk.reindex can rebuild the table from the bucket."""
    return {
        "camera_id": record["camera_id"],
        "capture_id": record["capture_id"],
        "capture_timestamp": record["capture_timestamp"],
        "store_id": record["store_id"],
        "image_key": image_key,
        "processing_time_ms": int(record["processing_time_ms"]),
        "latency_ms": int(record["latency_ms"]),
        "units_found": int(record["units_found"]),
        "flagged_rows": int(record["flagged_rows"]),
        "counts": {k: int(v) for k, v in record["counts"].items()},
        "rows_json": json.dumps(record["rows"], ensure_ascii=False),
        "log_json": json.dumps(record["log"], ensure_ascii=False),
        "expires_at": expires_at,
    }
