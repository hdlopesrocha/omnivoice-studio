#!/usr/bin/env python3
"""Submit a batch synthesis job and download the resulting ZIP."""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path


def request_json(url: str, payload: dict | None = None) -> dict:
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(
        url,
        data=data,
        headers=headers,
        method="POST" if payload is not None else "GET",
    )
    with urllib.request.urlopen(request, timeout=3600) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Batch synthesis with OmniVoice Studio")
    parser.add_argument("--api", default="http://127.0.0.1:8000/api")
    parser.add_argument("--file", required=True, help="Text file with batch items")
    parser.add_argument("--voice-id", default="")
    parser.add_argument("--mode", choices=["voice", "design", "auto"], default="auto")
    parser.add_argument("--instruct", default="")
    parser.add_argument("--language", default="")
    parser.add_argument("--format", choices=["wav", "mp3", "flac"], default="wav")
    parser.add_argument("--num-step", type=int, default=32)
    parser.add_argument("--split", choices=["blank", "line"], default="blank")
    parser.add_argument("--out", default="batch.zip")
    args = parser.parse_args()

    if args.mode == "voice" and not args.voice_id:
        parser.error("--voice-id is required when --mode is voice")
    if args.mode == "design" and not args.instruct:
        parser.error("--instruct is required when --mode is design")

    language = args.language
    language_variant = None
    if language in {"pt-PT", "pt-BR"}:
        if args.mode != "voice" or not args.voice_id:
            parser.error(
                "Portuguese variants require --mode voice and a matching --voice-id"
            )
        language_variant = language
        language = "pt"

    raw = Path(args.file).read_text(encoding="utf-8")
    parts = (
        raw.split("\n\n")
        if args.split == "blank"
        else raw.splitlines()
    )
    texts = [part.strip() for part in parts if part.strip()]
    if not texts:
        parser.error("No batch items found")

    payload = {
        "texts": texts,
        "mode": args.mode,
        "num_step": args.num_step,
        "response_format": args.format,
    }
    if args.voice_id:
        payload["voice_id"] = args.voice_id
    if args.instruct:
        payload["instruct"] = args.instruct
    if language:
        payload["language"] = language
    if language_variant:
        payload["language_variant"] = language_variant

    api = args.api.rstrip("/")
    try:
        job = request_json(f"{api}/jobs/batch", payload)
    except urllib.error.HTTPError as exc:
        print(
            f"Could not queue batch ({exc.code}): "
            f"{exc.read().decode('utf-8', errors='replace')}",
            file=sys.stderr,
        )
        return 1
    except urllib.error.URLError as exc:
        print(f"Could not reach {api}: {exc.reason}", file=sys.stderr)
        return 1

    job_id = job["id"]
    print(f"Queued batch job {job_id} with {len(texts)} item(s)")
    while True:
        try:
            job = request_json(f"{api}/jobs/{job_id}")
        except urllib.error.HTTPError as exc:
            print(f"Could not read job: {exc}", file=sys.stderr)
            return 1
        status = job.get("status")
        print(
            f"  {status:10s} {job.get('progress', 0) * 100:5.1f}% "
            f"{job.get('message', '')}"
        )
        if status in {"completed", "failed", "cancelled"}:
            break
        time.sleep(2)

    if status != "completed":
        print(f"Batch ended with {status}: {job.get('error')}", file=sys.stderr)
        return 1

    try:
        with urllib.request.urlopen(
            f"{api}/jobs/{job_id}/zip", timeout=3600
        ) as response:
            data = response.read()
    except urllib.error.HTTPError as exc:
        print(f"Could not download ZIP: {exc}", file=sys.stderr)
        return 1

    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(data)
    print(f"Wrote {output} ({len(data)} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
