# CLAUDE.md

LOVELACE: AUX wireless audio receiver. One ESP32-WROVER-E-N8R8 receives AirPlay 2, Spotify Connect (cspot) and Bluetooth A2DP and plays through a PCM5102A line-out. Firmware is a trimmed fork of rbouteiller/airplay-esp32 (see docs/UPSTREAM.md); the board is generated with KiCad 10 scripts.

## Layout

```
firmware/                 ESP-IDF 5.5 project (PlatformIO espressif32 6.13.0)
  config/                 sdkconfig layers: defaults -> bt -> flash8 -> lovelace-wrover [-> lovelace-capture]
  main/audio/
    audio_output.c        the single I2S writer task; reads the selected source
    audio_source.c        output ownership (set/release source, output lock)
    a2dp_sink.c           Bluetooth A2DP/AVRCP sink -> PSRAM FIFO
    spotify_audio.c       cspot PCM -> PSRAM FIFO
    audio_receiver.c ...  AirPlay 1/2 receive, decode, timing
    pcm_fifo.c, pcm_capture.c   host-testable buffers
  main/rtsp, hap, plist   AirPlay protocol
  main/network            Wi-Fi (AP+STA), mDNS, web UI/API, OTA, captive DNS
  components/boards/esp32-generic   LOVELACE board hooks (name kept for Kconfig)
  components/spotify      cspot + bell (vendored, GPLv3)
  data/www                web UI, flashed to SPIFFS
hardware/lovelace-as-004  make_board.sh: plan_pcb.py -> [autoplace.py] -> build_pcb.py -> jlc_check.py -> KiCadRoutingTools -> finish_pcb.py -> DRC/ERC -> audit_pcb.py -> release/ -> render_board.py
hardware/archive          earlier versions, one folder each: 01 S3 rev A, 02 AS-001, 03 AS-002 rev B, 04 AS-002 rev C, 05 AS-003 rev A
hardware/versions.json    version list behind the render / archive history pages
tests/, tools/            host tests (C, C++, Python) and the WAV capture CLI
```

## Commands

```sh
export PLATFORMIO_CORE_DIR="$PWD/work/platformio"
.venv/bin/pio run -d firmware -e lovelace-as-004            # build
.venv/bin/pio run -d firmware -e lovelace-as-004 -t upload  # hold the button while plugging USB in (CH340N has no DTR)
.venv/bin/pio run -d firmware -e lovelace-as-004 -t uploadfs
sh tools/test_host.sh                                       # all host tests
```

KiCad scripts run with KiCad's Python, e.g.
`/Volumes/KiCad/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3 hardware/lovelace-as-004/plan_pcb.py`.
Placement must pass the pcb-layout-skill checker (`placement_check.py placement.json`) with ERROR 0 before coordinates change in the board.

## Rules that are easy to break

- **One writer.** Only `playback_task` in audio_output.c writes I2S and changes its clock. Sources fill FIFOs; they never call `audio_output_write`.
- **Lock order:** output lock (`playback_control_lock_output`) first, then a source FIFO lock. Never call `playback_control_set_source` while holding a source lock or from the playback task.
- **Source switching** happens only on an explicit play request (AirPlay PLAYING, Spotify play/resume, AVRCP playing, or 1.5 s of audible A2DP while another source owns the output). Connections alone never take the output.
- PCM5102A has no hardware volume: every gain, including AirPlay local mute, is applied in software in `source_gain_q15()`.
- I2S pins are fixed by the PCB (rev C): BCK GPIO21, DIN GPIO19, LRCK GPIO18, DAC soft mute (XSMT, low = muted, pulled down) GPIO22, status LED GPIO23, single button GPIO0 (also the download strap). GPIO16/17 belong to the WROVER PSRAM.
- The DAC stays muted until `audio_output.c` releases GPIO22; anything that stops or changes the I2S clock mutes first (`i2s_restart_muted`).
- `cpl.csv` comes from `jlc_check.py` (JLC rotation/origin), not from KiCad: never hand-edit rotations.
- Task stacks stay in internal RAM (`spiram_task.h`): NVS/flash writes disable the cache.
- Style: LLVM, 2-space, 80 columns (`.clang-format`). Project-added C files keep the same style.
- Versions: board ID and rev live only in `plan_pcb.py` (`BOARD_ID`, `BOARD_REV`); before ordering, any copper change (netlist, outline or routing) gets a new AS-number; after ordering, a new rev. The silkscreen version text lives in `silkscreen.json` (audit_pcb.py checks it matches). Starting a new version: copy the current folder to `hardware/archive/NN-<name>/`, rename the folder, bump the ID, add a `hardware/versions.json` entry. Firmware version is `firmware/version.txt` (0.3.x = AS-003 / AS-004, same netlist).
- No hardware has been tested yet. Do not describe a feature as working on the board unless it was measured.
