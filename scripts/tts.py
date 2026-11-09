#!/usr/bin/env python3
"""Small dependency-free CLI used by `make say`."""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Synthesize speech with OmniVoice Studio")
    parser.add_argument("--api", default="http://127.0.0.1:8000/api")
    parser.add_argument("--text", required=True)
    parser.add_argument("--mode", choices=["voice", "design", "auto"], default="auto")
    parser.add_argument("--voice-id", default="")
    parser.add_argument("--instruct", default="")
    parser.add_argument("--language", default="")
    parser.add_argument("--format", choices=["wav", "mp3", "flac"], default="wav")
    parser.add_argument("--speed", type=float, default=None)
    parser.add_argument("--out", default="out.wav")
    args = parser.parse_args()

    if args.mode == "voice" and not args.voice_id:
        parser.error("--voice-id is required when --mode is voice")
    if args.mode == "design" and not args.instruct:
        parser.error("--instruct is required when --mode is design")

    language = args.language
    language_variant = None
    if language in {"pt-PT", "pt-BR"}:
        # OmniVoice has one `pt` model language. The variant is enforced by
        # the app and the reference clip controls the accent.
        if args.mode != "voice" or not args.voice_id:
            parser.error(
                "Portuguese variants require --mode voice and a matching "
                "--voice-id trained from a Portugal/Brazil reference clip"
            )
        language_variant = language
        language = "pt"

    payload = {
        "text": args.text,
        "mode": args.mode,
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
    if args.speed is not None:
        payload["speed"] = args.speed

    endpoint = args.api.rstrip("/") + "/tts"
    request = urllib.request.Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=3600) as response:
            body = response.read()
            headers = response.headers
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        print(f"Request failed ({exc.code}): {detail}", file=sys.stderr)
        return 1
    except urllib.error.URLError as exc:
        print(f"Could not reach {endpoint}: {exc.reason}", file=sys.stderr)
        return 1

    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(body)

    duration = headers.get("X-Audio-Duration", "?")
    rtf = headers.get("X-RTF", "?")
    output_id = headers.get("X-Output-Id", "?")
    print(
        f"Wrote {output} ({len(body)} bytes, {duration}s audio, RTF {rtf}, id {output_id})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
