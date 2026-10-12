#!/usr/bin/env python3
"""Preserve SS2K UDP log datagrams; timestamps describe host receipt, not BLE arrival."""
import argparse
import base64
import ipaddress
import json
from pathlib import Path
import re
import socket
import time

PREFIX = re.compile(r"\[\s*(\d+)\]\[[A-Z ]\]\(([^)]+)\):")
STATUS = re.compile(r"W=(-?\d+) C=(-?\d+) H=(-?\d+) G=(-?\d+) R=(-?\d+) P=(-?\d+)->(-?\d+)")


def record_datagram(payload, elapsed_ns, sequence):
    text = payload.decode("utf-8", errors="replace")
    prefix = PREFIX.search(text)
    kind = "other_log"
    if STATUS.search(text):
        kind = "status_snapshot"
    elif "<- " in text and " PW(" in text:
        kind = "sensor_processing"
    elif "ERG Mode Target:" in text:
        kind = "target_processing"
    return {"type": "datagram", "sequence": sequence,
            "host_receive_elapsed_ns": elapsed_ns,
            "firmware_log_ms": int(prefix[1]) if prefix else None,
            "kind": kind, "payload_base64": base64.b64encode(payload).decode("ascii"),
            "text": text}


def inspect(path):
    counts = {}
    backward = 0
    long_status_gaps = 0
    last = last_status = None
    total = 0
    with Path(path).open(encoding="utf-8") as stream:
        for line in stream:
            entry = json.loads(line)
            if entry.get("type") != "datagram":
                continue
            # Validate base64 syntax; this is not an integrity checksum.
            base64.b64decode(entry["payload_base64"], validate=True)
            total += 1
            kind = entry["kind"]
            counts[kind] = counts.get(kind, 0) + 1
            stamp = entry["firmware_log_ms"]
            if stamp is not None:
                backward += int(last is not None and stamp < last)
                last = stamp
                if kind == "status_snapshot":
                    long_status_gaps += int(last_status is not None and stamp - last_status > 2500)
                    last_status = stamp
    return {"datagrams": total, "counts": counts, "backward_firmware_times": backward,
            "status_gaps_over_2500ms": long_status_gaps,
            "warning": "No sequence counter at source: loss/completeness and BLE arrival timing cannot be established."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    capture = commands.add_parser("capture")
    capture.add_argument("output", type=Path)
    capture.add_argument("--device-ip", type=ipaddress.IPv4Address, required=True)
    capture.add_argument("--firmware-sha", required=True, help="User-recorded full SHA of installed firmware; not verified by listener")
    capture.add_argument("--port", type=int, default=10000)
    capture.add_argument("--duration", type=float, help="Seconds; omit to stop with Ctrl-C")
    check = commands.add_parser("inspect")
    check.add_argument("input", type=Path)
    args = parser.parse_args()
    if args.command == "inspect":
        print(json.dumps(inspect(args.input), indent=2))
        return
    if not re.fullmatch(r"[0-9a-fA-F]{40}", args.firmware_sha):
        parser.error("--firmware-sha must be a full 40-character commit; capture unknown builds using the serial/web procedure instead")
    if not 1 <= args.port <= 65535 or (args.duration is not None and not (0 < args.duration < float('inf'))):
        parser.error("port must be 1..65535 and duration finite and positive")
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.bind(("", args.port))
        sock.settimeout(0.25)
        # Exclusive creation protects previous recordings. Output directory must already exist.
        with args.output.open("x", encoding="utf-8") as output:
            output.write(json.dumps({"type": "capture_metadata", "schema_version": 1,
                "transport": "UDP", "firmware_sha_user_reported": args.firmware_sha,
                "time_semantics": "host elapsed receipt; firmware log emission; neither is BLE callback arrival",
                "source_filter": "single IPv4 address (omitted for privacy)", "port": args.port}) + "\n")
            output.flush()
            start = time.monotonic_ns()
            sequence = 0
            print("Listening. All selected-device datagrams, including duplicates, are preserved. Ctrl-C stops.", flush=True)
            try:
                while args.duration is None or (time.monotonic_ns() - start) / 1e9 < args.duration:
                    try:
                        payload, peer = sock.recvfrom(65535)
                    except socket.timeout:
                        continue
                    received = time.monotonic_ns()
                    if peer[0] != str(args.device_ip):
                        continue
                    entry = record_datagram(payload, received - start, sequence)
                    output.write(json.dumps(entry) + "\n")
                    output.flush()
                    sequence += 1
            except KeyboardInterrupt:
                pass
    print(json.dumps(inspect(args.output), indent=2))


if __name__ == "__main__":
    main()
