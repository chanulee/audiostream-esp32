# LOVELACE firmware

ESP-IDF firmware for the LOVELACE / AS-004 board (AS-003 has the same netlist; firmware 0.3.x, see `version.txt`): AirPlay 2, Spotify Connect and Bluetooth A2DP on an ESP32-WROVER-E with a PCM5102A line-out. Build, flash and usage are described in the [project README](../README.md).

This tree is a trimmed fork of [rbouteiller/airplay-esp32](https://github.com/rbouteiller/airplay-esp32) at commit `811d5f8af750096683dcec7c95d1cbc08c2f7601`. Support for other boards, TAS57xx/TAS58xx/ES8311 DACs, displays, W5500 Ethernet and USB/S/PDIF output was removed; use the upstream project for those. The upstream [license](LICENSE) (non-commercial) still applies. Changes are listed in [docs/UPSTREAM.md](../docs/UPSTREAM.md).
