# audiostream-esp32

AUX 스피커용 무선 오디오 수신기. 첫 개발 대상은 보유 중인 **ESP32-S3 N16R8** 보드입니다.

현재 구현은 **AirPlay + Spotify Connect 수신 펌웨어**와 **DAC 없이 1–10초 PCM을 캡처해 Mac에서 WAV로 저장하는 경로**입니다. Spotify 검색·로그인·다운로드·Vorbis 디코딩·출력 및 AirPlay 우선 전환을 통합했습니다. 실제 기기와 계정으로 재생을 확인하는 검증은 남아 있습니다. S3에는 Bluetooth Classic이 없으므로 일반적인 Bluetooth 오디오 수신(A2DP)은 별도 하드웨어가 필요합니다.

## 첫 실행

빌드용 Python은 3.11을 사용합니다. ESP-IDF의 일부 의존성이 Python 3.14와 호환되지 않습니다.

외부 DAC나 AUX 모듈은 연결하지 않아도 됩니다. USB로 S3 보드를 연결하세요. 두 USB 포트 중 USB-UART 포트를 우선 사용합니다. 사진만으로 Flash/PSRAM 용량을 확정할 수 없으므로 부팅 로그에서 16MB Flash / 8MB PSRAM을 확인해야 합니다.

```sh
python3.11 -m venv .venv
.venv/bin/pip install platformio==6.2.0
export PLATFORMIO_CORE_DIR="$PWD/work/platformio"
.venv/bin/pio run -d firmware -e audiostream-s3-capture
.venv/bin/pio run -d firmware -e audiostream-s3-capture -t upload
.venv/bin/pio run -d firmware -e audiostream-s3-capture -t uploadfs
.venv/bin/pio device monitor -b 115200
```

첫 부팅 시 `ESP32-AirPlay-Setup` Wi-Fi에 연결하고 `http://192.168.4.1/`에서 집의 2.4GHz Wi-Fi를 설정합니다. Mac/iPhone도 같은 LAN에 연결하세요. 시리얼 로그나 공유기에서 보드의 IP 주소를 확인합니다. 게스트 네트워크의 기기 격리나 mDNS 차단은 기기 검색을 방해할 수 있습니다.

Spotify는 먼저 `http://<보드 IP>/spotify`에서 본인의 개발자 앱 Client ID / Secret을 설정하고 재부팅하세요. Premium 계정과 인터넷 연결이 필요합니다. [설정 및 통합 설명](docs/SPOTIFY.md)을 참고하세요.

Mac에서 아래 명령을 실행한 다음 AirPlay 출력 목록의 `ESP32 AirPlay`를 선택하고 음악을 재생합니다. 이미 재생 중이라면 다음 PCM부터 캡처합니다.

```sh
python3 tools/capture.py http://192.168.1.42 --seconds 3 -o capture.wav
open capture.wav
```

3초 캡처에 약 529KB PSRAM을 사용합니다. 기본 출력은 44.1kHz / stereo / PCM16입니다. PCM은 볼륨·채널 처리 후 I2S에 제출된 데이터를 복사합니다. I2S DMA는 DAC가 없어도 출력 속도를 유지하며, BCLK=GPIO11 / WS=GPIO13 / DATA=GPIO12 핀을 사용합니다. 해당 핀에는 다른 주변장치를 연결하지 마세요. 이 경로는 AUX 아날로그 출력 품질을 검증하지 않습니다.

`firmware/config/sdkconfig.defaults.capture`는 GPIO 전원 공급과 MCLK를 끕니다. 캡처는 초기 대기 무음을 건너뛰며, 첫 오디오 버퍼 이후의 수신 언더런 무음은 그대로 포함합니다. Spotify Connect로 재생한 PCM도 같은 명령으로 캡처합니다. 캡처 종료 후에만 WAV를 내려받아 재생 중 다운로드 부하를 피합니다. 명령의 기본 대기 제한은 120초입니다. 재실행하면 이전 캡처를 덮어씁니다. API는 인증 없이 동작하므로 신뢰하는 로컬 네트워크에서 사용하세요.

## 개발 순서

1. **AirPlay 2 + PCM 캡처 검증**: S3에서 실제 연결·페어링·재생을 확인하고 Mac의 WAV로 음질과 끊김을 확인합니다. 현재 여기에 필요한 코드가 추가됐으며 실기기 검증은 남아 있습니다.
2. **Spotify Connect 실기기 검증**: `cspot`을 이식하고 검색·인증·Vorbis 디코딩과 공통 출력, 세션 전환을 연결했습니다. 본인의 계정으로 서버 인증과 CDN 접근을 확인하고, 곡 넘김·탐색·연속 재생을 검증합니다.
3. **Bluetooth와 AUX 완성**: S3를 유지하면 Bluetooth Classic 모듈 또는 보유 WROOM을 보조 수신기로 사용해야 합니다. 한 칩으로 구성하려면 PSRAM이 있는 원래 ESP32 WROVER 대상으로 별도 프로필을 만듭니다. I2S DAC의 stereo line-out을 3.5mm AUX에 연결하고, 전원·노이즈·Wi-Fi/BT 공존을 검증합니다.

## 테스트

```sh
sh tools/test_host.sh
```

검증 상태: ESP32-S3 펌웨어 빌드와 SPIFFS 이미지 생성 성공, C/C++ 호스트 테스트 4종 및 Python 테스트 3개 통과. 통합 펌웨어는 약 2.04MB입니다. USB 보드가 연결되지 않아 플래시 및 실제 AirPlay·Spotify 재생은 아직 확인하지 않았습니다.

호스트 테스트는 소스 전환, PCM 버퍼·캡처 경계, 연결 폼 파싱, WAV 및 기존 파일 보존을 확인합니다. 네트워크 프로토콜 호환성, PSRAM 초기화와 I2S 동작은 실제 보드에서 확인해야 합니다.

기반 코드와 라이선스는 [UPSTREAM.md](docs/UPSTREAM.md)를 참고하세요.
