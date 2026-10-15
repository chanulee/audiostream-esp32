# 기반 코드

`firmware/`는 [rbouteiller/airplay-esp32](https://github.com/rbouteiller/airplay-esp32)의 커밋 `811d5f8af750096683dcec7c95d1cbc08c2f7601`에서 가져온 소스 스냅샷입니다. `.git` 디렉터리는 포함하지 않았습니다. 원본 README와 [라이선스](../firmware/LICENSE)를 보존했습니다. 해당 라이선스는 비상업적 사용만 허용하므로 상용 제품으로 판매하려면 저작권자의 별도 허가가 필요합니다.

이 프로젝트에서 추가·변경한 내용:

- LOVELACE / AS-002 전용 PlatformIO 환경(`lovelace-as-002`, `lovelace-as-002-capture`)과 WROVER-E N8R8 설정. Flash 8MB 파티션(3MiB OTA 슬롯 2개 + SPIFFS).
- 다른 보드, TAS57xx/TAS58xx/ES8311 DAC 드라이버와 EQ, 디스플레이(u8g2/LVGL), W5500 Ethernet, USB/S/PDIF 출력, 원본 문서 사이트를 제거했습니다. 원본 커밋에서 모두 복원할 수 있습니다.
- 출력 소유권(`audio_source.c`): 하나의 재생 태스크가 AirPlay·Spotify·Bluetooth FIFO 중 선택된 소스를 읽습니다. 원본의 "BT 연결 시 AirPlay 중지"와 BT 라디오 suspend를 제거하고, 명시적 재생 요청이 출력을 가져가도록 바꿨습니다.
- A2DP: PSRAM FIFO + prefill, AVRCP 재생 보고 또는 1.5초 이상 들리는 오디오만 출력 획득, 48kHz 스트림은 I2S 클럭 전환, 비활성 소스의 메타데이터 차단, 소프트웨어 볼륨.
- PCM5102A처럼 하드웨어 볼륨이 없는 DAC에서 AirPlay 로컬 음소거가 동작하지 않던 문제 수정.
- 선택적으로 빌드되는 `audio_capture` HTTP API와 호스트 테스트 가능한 `pcm_capture`/`pcm_fifo`, Mac용 WAV CLI.
- Generic 보드의 비활성 mute GPIO(-1)가 음수 시프트로 컴파일되지 않도록 수정.

원본 PlatformIO 설정의 사용자별 `user_platformio.ini` 참조는 제거했습니다. PlatformIO espressif32 6.13.0 / ESP-IDF 5.5.3으로 고정했습니다.

## Spotify 엔진

`firmware/components/spotify/cspot/`는 [squeezelite-esp32](https://github.com/sle118/squeezelite-esp32)의 커밋 `af2e157f3d0d9cca57c1267393c6a6846278945b`에 포함된 `components/spotify/cspot`에서 가져왔습니다. 엔진의 원래 출처는 [cspot](https://github.com/feelfreelinux/cspot), Bell은 [bell](https://github.com/feelfreelinux/bell)입니다. Squeezelite의 Shim과 sink는 가져오지 않고 우리 펌웨어용 연결 계층을 작성했습니다.

nanopb와 Tremor만 유지하고 사용하지 않는 Bell 외부 라이브러리는 제외했습니다. protobuf C 파일은 포함된 nanopb 0.4.6-dev 생성기로 생성하여 일반 펌웨어 빌드에 protoc 설치가 필요하지 않도록 했습니다. 재생성 시 `grpcio-tools==1.60.1`, `protobuf==4.25.8`, `setuptools==75.6.0`을 사용합니다.

이식 과정에서 TLS 인증서 검증·HTTP 토큰 요청, base64/블롭/문자열 길이 검사, 입력 폼 처리, 태스크 우선순위·할당 실패 검사, 안정적인 MAC 기반 기기 ID와 Vorbis 열기 오류 처리를 수정했습니다. ESP-IDF 빌드에 맞춰 누락된 C++ include와 사용하지 않는 Vorbis 라벨도 정리했습니다.

cspot의 원본 [GPLv3 라이선스](../firmware/components/spotify/cspot/LICENSE.md)를 추가로 보존했습니다. nanopb와 Tremor 라이선스도 각 디렉터리에 있습니다. Bell 원본 저장소에는 별도 최상위 라이선스 파일이 확인되지 않아 원소스의 고지를 보존했습니다.

AirPlay 기반 코드의 비상업적 라이선스와 cspot의 GPLv3 조건을 모두 포함하므로 이 결합본을 배포하거나 상용화하기 전에 권리자 허가와 라이선스 호환성을 정리해야 합니다. 현재 작업은 개인 보드에서 검증하는 개발 프로토타입입니다.
