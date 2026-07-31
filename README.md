# Bondwell_12_14_CPM_Audio_Player

BONDWELL 12/14 SMOOTH MC1408 BMC PLAYER
========================================

This package replaces the earlier one-bit BWDM/DMC player and waveform with a
new BWA4/BMC format designed to sound less rattly and squeaky on the Bondwell
12/14 MC1408 DAC.

COPY TO THE SAME CP/M DISK
-------------------------
BWPLAY.COM
GAMES.BMC

RUN
---
A>BWPLAY
Bondwell 12/14 MC1408 smooth 10 kHz BMC player - port 50H
File to play (.BMC assumed): GAMES

The following filename forms are accepted:

GAMES
GAMES.BMC
B:GAMES.BMC

BMC is added when the extension is omitted.

IMPORTANT
---------
GAMES.BMC uses the new BWA4 format and requires the BWPLAY.COM supplied in
this package.  The earlier DMC player will not play this file.

WHAT CHANGED
------------
The earlier format used one bit per sample at 2000 samples per second and a
fixed step of 13 DAC counts.  Every sample had to move either up or down, even
when the wanted waveform was nearly stationary.  This produced granular
rattle and a strong audible sampling image around the DAC update rate.

The new format uses:

* 2500 source samples per second
* 2-bit differential codes
* small changes of +/-6 DAC counts
* large changes of +/-34 DAC counts for steep waveform sections
* four interpolated DAC writes for every source sample
* approximately 10000 MC1408 writes per second

The four smaller DAC movements form a ramp between reconstructed samples.
This moves the first major stair-step image from about 2 kHz to about 10 kHz
and reduces the large fixed-step chatter of the original encoder.

GAMES.BMC DETAILS
-----------------
Source duration:              63.192 seconds
Source sample rate:           2500 samples/second
DAC update rate:              10000 writes/second
Source samples:               157980
DAC writes:                   631920
Payload size:                 39495 bytes
Total BMC size:               39511 bytes
Reconstructed DAC range:      20 to 232
DAC I/O port:                 50H
Expected playback at 4 MHz:   63.192 seconds

The complete BMC file is loaded before playback to avoid floppy or Gotek
access gaps.  The player checks the CP/M BDOS address before each 128-byte
read and reports an error if a selected file will not fit in available TPA.
Interrupts and keyboard input remain disabled while audio is playing.

FILES
-----
BWPLAY.COM
    Compiled CP/M player.

BWPLAY.ASM
    Documented Z80 source.

GAMES.BMC
    Newly converted BWA4 audio.

GAMES_SMOOTH10K_PREVIEW.wav
    Computer-playable preview of the reconstructed 10 kHz DAC stream.

MAKE_BMC.PY
    WAV/MP3-to-BMC conversion utility. Requires Python, NumPy and FFmpeg.

BUILD_BWPLAY.py
    Byte-exact builder used to generate BWPLAY.COM.

TEST_BMC.py
    Host-side format, range and timing validation.

BMC_FORMAT.TXT
    BWA4 file layout and code mapping.

SHA256.TXT
    File checksums.
