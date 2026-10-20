# audiostream-esp32 — LOVELACE

AUX 스피커(3.5mm 라인 입력)에 꽂는 무선 오디오 수신기입니다. 한 개의 ESP32로 **AirPlay 2 · Spotify Connect · Bluetooth A2DP**를 모두 받고, 마지막으로 재생을 요청한 휴대폰이 출력을 가져갑니다.

| 항목 | 내용 |
|---|---|
| MCU | ESP32-WROVER-E-N8R8 (Flash 8MB, PSRAM 8MB, Wi-Fi + Bluetooth Classic) |
| DAC | PCM5102A, 3.5mm stereo line-out (2.1 Vrms) |
| 전원 | USB-C 5V → eFuse(OVP 5.8V, 전류 제한) → 3.3V buck / 저잡음 아날로그 LDO. 전원 스위치 없이 꽂으면 켜짐 |
| 보드 | LOVELACE / AS-008 rev A, 37 × 41mm 4층. USB-C와 AUX가 같은 변, 버튼 1개 |
| 수신 | AirPlay 2 (AAC/ALAC), Spotify Connect (cspot, Ogg Vorbis 320kbps), Bluetooth A2DP SBC + AVRCP |

S3 기반 이전 시제품(AS-001)은 Bluetooth Classic이 없어 A2DP를 받을 수 없으므로 WROVER로 전환했습니다. 첫 시제품부터 현재까지의 기록은 [hardware/archive](hardware/archive/README.md)에 있습니다.

## 빌드와 플래시

빌드용 Python은 3.11을 사용합니다. ESP-IDF 일부 의존성이 Python 3.14와 호환되지 않습니다.

```sh
python3.11 -m venv .venv
.venv/bin/pip install platformio==6.2.0
export PLATFORMIO_CORE_DIR="$PWD/work/platformio"
.venv/bin/pio run -d firmware -e lovelace-as-004 -t upload
.venv/bin/pio run -d firmware -e lovelace-as-004 -t uploadfs
.venv/bin/pio device monitor -b 115200
```

AS-003 이후 보드의 CH340N에는 DTR이 없어 자동 다운로드 모드 진입을 지원하지 않습니다. 업로드 전에 **버튼을 누른 채 USB를 꽂으세요.** 이후 펌웨어 업데이트는 웹 UI의 OTA로도 가능합니다.

버튼: 짧게 = 재생/일시정지, 두 번 = 다음 곡, 3초 = Bluetooth 페어링(연결된 폰을 끊고 새 폰 연결 대기).

| 환경 | 용도 |
|---|---|
| `lovelace-as-004` | 기본 펌웨어. AirPlay + Spotify + Bluetooth |
| `lovelace-as-004-capture` | 위 기능 + PCM 캡처 API (개발용, PSRAM 사용) |

## 첫 설정

1. 첫 부팅 시 `LOVELACE-Setup` Wi-Fi에 연결하고 `http://192.168.4.1/`에서 집의 2.4GHz Wi-Fi를 설정합니다.
2. Spotify: `http://<보드 IP>/spotify`에서 본인의 개발자 앱 Client ID / Secret을 입력하고 재부팅합니다. Premium 계정이 필요합니다. [설정 및 통합 설명](docs/SPOTIFY.md).
3. Bluetooth: 휴대폰의 Bluetooth 목록에서 `LOVELACE`를 선택합니다. 화면이 없으므로 Just Works 페어링을 사용하며, 구형 기기는 PIN `0000`을 사용합니다.

게스트 네트워크의 기기 격리나 mDNS 차단은 AirPlay·Spotify 검색을 방해합니다.

## 소스 전환 규칙

- 출력은 한 번에 하나의 소스만 사용합니다. 하나의 재생 태스크가 I2S를 쓰고, 소스는 `audio_source.c`의 출력 잠금 아래에서만 바뀝니다.
- **명시적 재생 요청이 출력을 가져옵니다.** AirPlay 재생, Spotify 재생/재개, Bluetooth AVRCP "playing" 보고가 해당합니다. 이전 소스는 일시정지 요청(Spotify yield, AVRCP pause)을 받고 대기 PCM은 버립니다.
- 다른 소스가 출력 중일 때 휴대폰 알림음이나 키보드 클릭처럼 A2DP 스트림만 열린 경우에는 출력을 가져오지 않습니다. 1.5초 이상 소리가 이어질 때만 재생으로 판단합니다.
- Bluetooth가 연결되어 있어도 AirPlay와 Spotify는 계속 검색됩니다. A2DP 48kHz 스트림은 I2S 클럭을 바꿔 리샘플링 없이 출력합니다.

## 테스트

```sh
sh tools/test_host.sh
```

호스트 테스트는 출력 소유권 전환(AirPlay/Spotify/Bluetooth), PCM FIFO 경계, 캡처 및 44.1/48kHz 전환, Spotify 연결 폼 파싱, WAV 저장을 확인합니다.

**검증 상태 (2026-10-16):** `lovelace-as-004` 펌웨어 0.3.1 빌드 성공, 호스트 테스트와 실크 편집기 테스트 전체 통과. **실기기 검증은 아직 없습니다.** 특히 Wi-Fi + Bluetooth + Spotify TLS를 동시에 켠 상태의 내부 RAM 여유, Wi-Fi/BT 공존 시의 끊김, 실제 계정의 Spotify 재생은 보드에서 측정해야 합니다.

### 캡처로 음질 확인

`lovelace-as-004-capture` 펌웨어에서 DAC 없이도 출력 PCM을 WAV로 받을 수 있습니다.

```sh
python3 tools/capture.py http://192.168.1.42 --seconds 3 -o capture.wav
```

[캡처 API](docs/CAPTURE_API.md)는 인증 없이 동작하므로 신뢰하는 로컬 네트워크에서만 사용하세요.

## 하드웨어

[LOVELACE / AS-008 rev A](hardware/lovelace-as-008/README.md)는 KiCad 10으로 스크립트 생성하며, [pcb-layout-skill](https://github.com/studio-edul/pcb-layout-skill)의 배치 검사기·계산기로 검증합니다. 제작 전 남은 항목은 [REVIEW.md](hardware/lovelace-as-008/REVIEW.md), 주문과 첫 보드 확인은 [BRINGUP.md](hardware/lovelace-as-008/BRINGUP.md)에 있습니다.

## 버전

| | 위치 | 버전 |
|---|---|---|
| 하드웨어 (현재) | `hardware/lovelace-as-008/` | AS-008 rev A (`plan_pcb.py`의 `BOARD_ID`, `BOARD_REV`) |
| 하드웨어 (이전) | `hardware/archive/NN-*/` | S3 rev A → AS-001 → AS-002 rev B → AS-002 rev C ([기록](hardware/archive/README.md)) |
| 펌웨어 | `firmware/version.txt` | 0.3.0 |

펌웨어 0.3.x는 AS-003부터 AS-008까지 전용입니다(AS-003–AS-006은 넷리스트가 같고, AS-007은 AUX 잭 단자 배정, AS-008은 USB via 크기와 eFuse ITIMER 미실장 패드만 다릅니다. 펌웨어와 무관합니다). 빌드 환경 이름은 `lovelace-as-004` 그대로 씁니다. DAC 뮤트(XSMT)를 GPIO22로 풀어야 소리가 나며, 0.2.x(ESP32-S3 / AS-001)는 이 보드들에서 동작하지 않습니다. 하드웨어 버전 규칙은 [archive/README.md](hardware/archive/README.md)에 있습니다.

## 문서

- [Spotify Connect 통합](docs/SPOTIFY.md)
- [연결 기능 조사: SDK, 다중 휴대폰, Bluetooth, Flash](docs/CONNECT_RESEARCH.md)
- [PCM 캡처 API](docs/CAPTURE_API.md)
- [기반 코드와 라이선스](docs/UPSTREAM.md). AirPlay 기반 코드는 비상업적 라이선스, cspot은 GPLv3입니다. 배포·판매 전에 권리 관계를 정리해야 합니다.
