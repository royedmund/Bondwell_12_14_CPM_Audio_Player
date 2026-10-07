# Bondwell 12/14 CP/M audio player

A smooth BWA4/BMC audio player for the Bondwell 12/14 MC1408 DAC at I/O port `50H`. This replaces the earlier one-bit BWDM/DMC player and format.

[Playback demonstration](https://youtu.be/Tx1pKgOmVMg)

## Play the supplied sample

Copy [BWPLAY.COM](BWPLAY.COM) and [GAMES.BMC](GAMES.BMC) to the same CP/M disk, then run:

```text
A>BWPLAY
Bondwell 12/14 MC1408 smooth 10 kHz BMC player - port 50H
File to play (.BMC assumed): GAMES
```

Accepted filenames include `GAMES`, `GAMES.BMC` and `B:GAMES.BMC`. The `.BMC` extension is added when omitted. The supplied BWA4 file requires this version of `BWPLAY.COM`; the earlier DMC player is incompatible.

The player loads the entire file before playback to avoid floppy/Gotek gaps. It checks available TPA before each 128-byte read. Interrupts and keyboard input remain disabled while audio plays.

## Format and timing

The earlier format used one bit per sample at 2000 samples/s and a fixed 13-count DAC step. The new format uses four 2-bit differential codes per byte, with total changes of ±6 or ±34 DAC counts per source sample. Four interpolated writes per sample reduce fixed-step chatter and move the main stair-step image toward 10 kHz.

| Supplied sample property | Value |
| --- | --- |
| Format | BWA4, described in [BMC_FORMAT.TXT](BMC_FORMAT.TXT) |
| Source sample rate | 2500 samples/s |
| Nominal DAC update rate | 10000 writes/s |
| Source samples / DAC writes | 157980 / 631920 |
| Nominal duration at 4 MHz | 63.192 s |
| Payload / total file size | 39495 / 39511 bytes |
| Reconstructed DAC range | 20–232 |

These timing values assume the intended 4 MHz CPU. Host-side validation estimates timing; it does not replace a hardware playback test.

## Host tools

Use Python 3.9 or newer. The converter and format checks require NumPy; conversion and preview generation also require FFmpeg on `PATH`.

From the repository root:

```bash
python3 TEST_BMC.py
python3 BUILD_BWPLAY.py
sha256sum -c SHA256.TXT
```

The builder writes `BWPLAY.COM` and `BWPLAY.MAP` beside the script, replacing those generated files. Commit intentional rebuilds only after checking the differences.

To convert your own WAV/MP3 source:

```bash
python3 MAKE_BMC.PY input.wav OUTPUT.BMC --preview OUTPUT_PREVIEW.wav
```

The BWA4 payload limit is 65535 bytes, but the CP/M system's available TPA may impose a lower limit. Keep converted filenames compatible with CP/M's 8.3 convention.

## Repository layout

| File | Purpose |
| --- | --- |
| [BWPLAY.ASM](BWPLAY.ASM) | Documented Z80 assembly source |
| `BWPLAY.COM` / `BWPLAY.MAP` | Supplied executable and symbol map |
| [BUILD_BWPLAY.py](BUILD_BWPLAY.py) | Byte-exact Python builder; no external assembler required |
| [MAKE_BMC.PY](MAKE_BMC.PY) | WAV/MP3-to-BMC conversion utility |
| [TEST_BMC.py](TEST_BMC.py) | Host checks for the supplied file's format, range and estimated timing |
| `GAMES.BMC` / `GAMES_SMOOTH10K_PREVIEW.wav` | Sample audio and computer-playable reconstruction |
| [RECORDING_ANALYSIS.TXT](RECORDING_ANALYSIS.TXT) | Recording notes |
| [SHA256.TXT](SHA256.TXT) | Checksums for the listed source, documentation and sample files |

The flat layout deliberately keeps the CP/M files together and matches the host test paths. Supplied `.COM`, `.BMC` and preview files are intentional distribution assets. No standalone licence file is currently included.
