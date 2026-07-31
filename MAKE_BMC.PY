#!/usr/bin/env python3
"""Create smooth BWA4/BMC audio for the Bondwell 12/14 MC1408 DAC.

The format stores four 2-bit differential samples in each byte.  The player
reconstructs each source sample with four quarter-steps, giving 10 kHz DAC updates
from a 2.5 kHz source stream.  This is designed to reduce the granular noise
and strong sample-rate images of the earlier 1-bit BWDM format.
"""
from __future__ import annotations

import argparse
import math
import struct
import subprocess
from pathlib import Path

import numpy as np

RATE = 2500
INITIAL = 128
SMALL_DELTA = 6      # total reconstructed change per source sample
LARGE_DELTA = 34
NORMALISED_PEAK = 80.0


def decode_source(source: Path) -> np.ndarray:
    command = [
        "ffmpeg", "-hide_banner", "-loglevel", "error",
        "-i", str(source),
        "-ac", "1",
        "-af", "highpass=f=35,lowpass=f=1100",
        "-ar", str(RATE),
        "-f", "f32le", "pipe:1",
    ]
    return np.frombuffer(subprocess.check_output(command), dtype="<f4").copy()


def normalise(samples: np.ndarray) -> np.ndarray:
    work = samples.astype(np.float64)
    work -= float(np.mean(work))
    reference = float(np.percentile(np.abs(work), 99.8))
    if reference > 0.0:
        work *= NORMALISED_PEAK / reference
    return np.clip(np.rint(128.0 + work), 0, 255).astype(np.uint8)


def encode(samples: np.ndarray) -> tuple[np.ndarray, np.ndarray, int, int, int]:
    """Return codes, 10 kHz interpolated DAC output, min and max levels."""
    predictor = INITIAL
    codes = np.empty(len(samples), dtype=np.uint8)
    dac = np.empty(len(samples) * 4, dtype=np.uint8)
    min_predictor = predictor
    max_predictor = predictor

    # Codes map to total source-sample deltas:
    #   00 = -34, 01 = -6, 10 = +6, 11 = +34
    # Each delta is split into four small DAC movements to suppress images.
    ramps = (
        (-8, -9, -8, -9),
        (-1, -2, -1, -2),
        ( 1,  2,  1,  2),
        ( 8,  9,  8,  9),
    )

    out_index = 0
    threshold = (LARGE_DELTA + SMALL_DELTA) // 2   # 20
    for index, sample in enumerate(samples):
        error = int(sample) - predictor
        if error < -threshold:
            code = 0
        elif error < 0:
            code = 1
        elif error < threshold:
            code = 2
        else:
            code = 3

        for increment in ramps[code]:
            predictor += increment
            dac[out_index] = predictor
            out_index += 1
        codes[index] = code
        min_predictor = min(min_predictor, predictor)
        max_predictor = max(max_predictor, predictor)

    if not (0 <= min_predictor and max_predictor <= 255):
        raise RuntimeError(
            f"reconstructed DAC level would wrap: min={min_predictor}, max={max_predictor}"
        )

    return codes, dac, min_predictor, max_predictor, len(ramps)


def pack_codes(codes: np.ndarray) -> tuple[bytes, int]:
    valid_last = len(codes) % 4 or 4
    padded_count = math.ceil(len(codes) / 4) * 4
    if padded_count != len(codes):
        # Alternate small down/up codes to avoid a large final transient.
        pad = np.resize(np.array([1, 2], dtype=np.uint8), padded_count - len(codes))
        codes = np.concatenate((codes, pad))
    groups = codes.reshape(-1, 4)
    packed = (
        (groups[:, 0] << 6)
        | (groups[:, 1] << 4)
        | (groups[:, 2] << 2)
        | groups[:, 3]
    ).astype(np.uint8)
    return packed.tobytes(), valid_last


def write_preview(path: Path, dac_samples: np.ndarray) -> None:
    temporary = path.with_suffix(".tmp.u8")
    temporary.write_bytes(dac_samples.tobytes())
    try:
        subprocess.run([
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-f", "u8", "-ar", str(RATE * 4), "-ac", "1",
            "-i", str(temporary),
            "-ar", "44100", "-ac", "1", str(path),
        ], check=True)
    finally:
        temporary.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Create Bondwell BWA4/BMC smooth audio")
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--preview", type=Path)
    args = parser.parse_args()

    source = normalise(decode_source(args.source))
    codes, dac, minimum, maximum, _ = encode(source)
    payload, valid_last = pack_codes(codes)

    if len(payload) > 0xFFFF:
        raise SystemExit("BMC payload exceeds the 65535-byte BWA4 format limit")

    header = struct.pack(
        "<4sHHBBBBI",
        b"BWA4",
        RATE,
        len(payload),
        valid_last,
        INITIAL,
        SMALL_DELTA,
        LARGE_DELTA,
        len(source),
    )
    args.output.write_bytes(header + payload)

    if args.preview:
        write_preview(args.preview, dac)

    print(f"source={args.source}")
    print(f"output={args.output}")
    print(f"duration_seconds={len(source) / RATE:.3f}")
    print(f"source_samples={len(source)}")
    print(f"dac_updates={len(dac)}")
    print(f"payload_bytes={len(payload)}")
    print(f"total_bytes={len(header) + len(payload)}")
    print(f"source_rate={RATE}")
    print(f"dac_update_rate={RATE * 4}")
    print(f"small_delta={SMALL_DELTA}")
    print(f"large_delta={LARGE_DELTA}")
    print(f"reconstructed_range={minimum}..{maximum}")


if __name__ == "__main__":
    main()
