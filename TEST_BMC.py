#!/usr/bin/env python3
from __future__ import annotations

import struct
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
BMC = ROOT / "GAMES.BMC"
COM = ROOT / "BWPLAY.COM"

raw = BMC.read_bytes()
signature, rate, payload_bytes, valid_last, initial, small, large, sample_count = struct.unpack(
    "<4sHHBBBBI", raw[:16]
)
assert signature == b"BWA4"
assert rate == 2500
assert payload_bytes == len(raw) - 16
assert 1 <= valid_last <= 4
assert initial == 128
assert (small, large) == (6, 34)

payload = np.frombuffer(raw[16:], dtype=np.uint8)
codes = np.empty(payload.size * 4, dtype=np.uint8)
codes[0::4] = payload >> 6
codes[1::4] = (payload >> 4) & 3
codes[2::4] = (payload >> 2) & 3
codes[3::4] = payload & 3
codes = codes[:sample_count]

ramps = np.array([
    [-8, -9, -8, -9],
    [-1, -2, -1, -2],
    [ 1,  2,  1,  2],
    [ 8,  9,  8,  9],
], dtype=np.int16)
level = initial
minimum = maximum = level
for code in codes:
    for increment in ramps[int(code)]:
        level += int(increment)
        minimum = min(minimum, level)
        maximum = max(maximum, level)
        assert 0 <= level <= 255

# Cycle estimate for the supplied fixed-cycle 4 MHz playback loop.
# Three of the four inter-output intervals are exactly 400 T-states; the
# fourth carries decoding and byte-loop overhead.  This computes the exact
# average for this code stream from the known branch paths.
dispatch_cycles = np.array([40, 35, 45, 40], dtype=np.int64)
frequency = np.bincount(codes, minlength=4)
full_bytes = payload_bytes
# Per byte: load packed byte 20; four common sample bodies 4*1547;
# alternate byte counter and JP 32; plus the code-dependent dispatch branches.
cycles = (
    full_bytes * (20 + 4 * 1547 + 32)
    + int((frequency * dispatch_cycles).sum())
)
seconds = cycles / 4_000_000.0

assert COM.stat().st_size < 2048
assert 62.9 < seconds < 63.5

print(f"BMC bytes: {len(raw)}")
print(f"COM bytes: {COM.stat().st_size}")
print(f"Samples: {sample_count}")
print(f"DAC writes: {sample_count * 4}")
print(f"Level range: {minimum}..{maximum}")
print(f"Nominal duration: {sample_count / rate:.3f} s")
print(f"Estimated 4 MHz player duration: {seconds:.3f} s")
print(f"Code frequencies: {frequency.tolist()}")
print("All checks passed")
