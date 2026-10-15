# LOVELACE 연결 기능 조사 — 2026-10-14

사용자 요구: AirPlay 고정 우선순위 없음. 인증 배지를 목표로 삼지 않고 가능한 범위에서 일반 Connect 기기와 유사한 경험 제공. 다른 휴대폰 제어, 일반 Bluetooth 음악 수신, Flash 8MB 검토. Bluetooth는 휴대폰 → LOVELACE A2DP 수신을 기준으로 조사했으며 Bluetooth 스피커로 송신하거나 두 폰 동시 재생하는 multipoint는 별도 범위다.

## 판단

ESP32 단독 / 기존 DAC / 가격을 유지하고 Bluetooth 수신이 필수라면 **ESP32-WROVER-E-N8R8(Flash 8MB, PSRAM 8MB)**을 우선 후보로 한다. S3/C5는 Bluetooth Classic A2DP 수신을 제공하지 않는다. 이 판단에 따라 WROVER로 전환했다(LOVELACE / AS-002 rev C, 37 × 41mm, [하드웨어 문서](../hardware/lovelace-as-002/README.md)). 이전 S3 AS-001은 [archive](../hardware/archive/)로 옮겼다. WROVER가 AirPlay 2 + Spotify 320kbps + A2DP를 이 프로젝트에서 모두 안정적으로 실행한다고 확인한 것은 아니다. 특히 내부 RAM 및 Wi-Fi/BT 공존이 실측 대상이다.

Flash 8MB 프로필을 사용한다. 구성은 3MiB OTA 앱 슬롯 2개와 약1.875MiB SPIFFS, NVS/OTA 메타데이터다. AirPlay + Spotify + Bluetooth 펌웨어는 2.30MB(슬롯의 73%), 웹 리소스는 약 32KB다. Flash와 재생 버퍼 PSRAM은 별개이므로 Flash를 줄여도 PSRAM은 유지한다. 이전 S3 계산 기록은 [archive](../hardware/archive/lovelace-as-001/reports/connect-software/)에 있다.

## 공식 플랫폼 / SDK

| 경로 | 확인한 내용 | 이 프로젝트와의 관계 |
|---|---|---|
| Spotify Embedded SDK | 상용 파트너 바이너리. 여러 CPU/OS 조합에 toolchain build request 방식이며 공개 문서만으로 특정 ESP32 지원을 확정할 수 없음. 권장 RAM1.4MB, TLS 추가heap약412KB. | 인증 없는 DIY에 공개 라이브러리처럼 바로 가져올 수 있는 SDK는 아님. 검색·소스전환·동기화 동작을 참고할 수 있음. |
| Spotify Soloist | **2026-08-13 공개된 공식 DIY Linux 클라이언트.** ARM32/ARM64/x86_64 Linux 다운로드. API key는 사용자별로 생성하며 바이너리 직접 재배포 금지. 문서는90일 build expiry/업데이트를 안내. 초기 Premium 설정 후 Free/Premium 연결, Jam·정규화·crossfade·24bit44.1kHz lossless 등의 기능을 발표. | ESP32 FreeRTOS에서 실행 불가. Raspberry Pi/소형Linux로 바꿀 경우 공식 선택지. MCU의 Flash 8MB와 비교하는 플랫폼이 아님. 앞선 “개인 DIY 공식 경로가 없다”는 설명은 이 새 경로를 빠뜨린 것. |
| Web API / Web Playback SDK | Web API는 재생 장치 제어·메타데이터 API이고 Web Playback SDK는 브라우저 안의 플레이어. | ESP32 오디오 수신 엔진 대체가 아님. |

출처: [eSDK 기술 요구](https://developer.spotify.com/documentation/commercial-hardware/implementation/requirements/technical), [Soloist 개요](https://developer.spotify.com/documentation/soloist), [출시 발표](https://developer.spotify.com/blog/2026-08-13-introducing-spotify-soloist), [다운로드 CPU](https://developer.spotify.com/documentation/soloist/reference/downloads-and-updates), [Web Playback SDK](https://developer.spotify.com/documentation/web-playback-sdk).

## 오픈소스 비교

| 프로젝트 | 장점 / 적용 | 제약 |
|---|---|---|
| [cspot](https://github.com/feelfreelinux/cspot) | C++ embedded Spotify Connect, ESP32/PCM5102 경로, Zeroconf 발견 및 SPIRC 제어. 현재 프로젝트의 Spotify engine 기반. | 오래된 문서와 현재 서버 인증의 차이. 현재 vendored port는 별도 Client ID/Secret을 필요로 함. |
| [squeezelite-esp32](https://github.com/sle118/squeezelite-esp32) | ESP32/WROVER용 Spotify(cspot), Bluetooth, AirPlay 통합의 가장 가까운 참고. 유지보수자는 standalone add-on 사용의 한계도 명시. | AirPlay는 **1**이라고 명시. 이 프로젝트의 AirPlay2 구현을 통째로 대체하는 것으로 간주할 수 없음. |
| [librespot](https://github.com/librespot-org/librespot) | Rust Connect receiver. 검색·세션·계정·원격 제어의 기준 구현. Premium 요구. | 일반 Linux/desktop 경로이며 현재 ESP32에 바로 링크하는 대체품이 아님. [lossless 미지원 이슈](https://github.com/librespot-org/librespot/issues/1583)는 계속 한계로 봐야 함. |
| [go-librespot](https://github.com/devgianlu/go-librespot) | Go 기반. Zeroconf/OAuth/device-auth, 원격 제어, normalization/crossfade/Jam 등의 현재 README 기능은 사용자 경험 참고에 유용. | Linux/desktop 실행 및 오디오 라이브러리 의존. 기능을 ESP32에 무료로 그대로 이식할 수 있는 구조는 아님. |
| [cspot-waveshare-esp32s3](https://github.com/VitaliBorys/cspot-waveshare-esp32s3/blob/main/spotify_connect_flow.md) | IDF6 port가 최근 인증·storage-resolve 변경과 Client Credentials 필요를 설명. 우리 인증 문제와 가까운 참고. | 별도 앱 키 설정이 남아 있으므로 “키 없이 정상 상용 동작”의 근거로 쓰면 안 됨. |

## Reddit 사용 경험

Reddit은 개별 경험이며 호환성/안정성 시험 결과로 대체하지 않았다.

- [ESP32에서 Spotify 수신 질문](https://www.reddit.com/r/esp32/comments/1h4ladg/): cspot/WROVER/S3 및 squeezelite를 추천하는 의견과 개발 중 sink 문제 언급. 검색 결과 본문은 확인했으나 전체 페이지는 접근 오류여서 모든 댓글·최신 상황을 확인하지 못함.
- [Pi Zero2W+HiFiBerry 사용기, 2025-05](https://www.reddit.com/r/raspberry_pi/comments/1kv6wlo/pi_hifiberry_used_as_a_spotify_connect_client/): 작성자는 Raspotify 자동 부팅 및 약3개월 연속 사용에 만족했다고 보고. 긍정적 실제 사용 사례지만 특정 환경의 경험.
- [Moode Spotify 중단, 2025-08](https://www.reddit.com/r/raspberry_pi/comments/1mkxan6/spotify_stopped_working_on_my_raspberry_pi_with/): 여러 사용자가 재설치로도 해결 안 된 문제를 보고하고 librespot 업데이트 후 해결을 보고. 서버 변화에 대응하는 OTA/업데이트가 중요하다는 설계 근거.
- [Soloist 기반 Encore, 2026-10 검색 결과](https://www.reddit.com/r/raspberry_pi/comments/1x3hu0d/encore_a_headless_spotify_connect_player_using/): DIY UI/WebSocket 통합에 새 공식 클라이언트를 이용하는 사례. 검색 결과는 확인했으나 전체 페이지 접근 오류. Linux 대안의 등장 근거이며 ESP32 성공 사례는 아님.

## 다른 휴대폰으로 제어

**같은 계정**: 폰A로 LOVELACE를 선택하고 폰B도 같은 Spotify 계정으로 로그인하여 재생/일시정지·다음·탐색·볼륨을 제어하는 경험을 목표로 한다. 폰A가 꺼져도 보드가 직접 음악을 받으므로 지속 재생해야 한다. 현재 cspot은 `hm://remote/user/<username>/` 채널 구독, 원격 play/pause/seek/volume/load/replace, 상태 notify를 구현한다. 같은 계정의 addUser는 허용한다. 구조상 가능하지만 실제 두 폰+실계정 검증은 안 됐다.

**다른 계정**: 같은 LAN에서 검색되는 것과 기존 계정의 음악 제어 권한은 다르다. 현재 다른 계정의 addUser는409로 거절하고 `/spotify`의 계정 잊기를 요구한다. 사용자 친화적 계정 인계, 저장된 계정 교체, 실패 시 복구를 추가해야 한다. 현재 Jam 구현 없음. Family 요금제의 개별 계정도 서로 다른 계정이다.

**AirPlay**: 폰B가 새로운 송신기로 선택해서 재생을 가져오는 것과 폰B가 폰A의 앱을 원격 제어하는 것은 별개. 현재 RTSP는 새 송신 연결로 교체하는 구조지만 AirPlay2 MRP 원격 제어는 없다. DACP는 헤더를 보내는 AirPlay1 송신기에 한정됨.

**Bluetooth**: 같은 계정 개념 없이 연결된 폰에서 오디오를 수신한다. A2DP/AVRCP 필요. 다른 폰으로 바꾸는 것은 연결 전환이며 multipoint 또는 두 폰의 동시 재생을 보장하지 않는다.

## 구현 현황과 상용 유사 동작 목표

| 기능 | 현재 확인 | 남은 작업/시험 |
|---|---|---|
| Wi-Fi 설정/저장, 항상 발견 | AP/웹설정·NVS, AirPlay/Spotify mDNS 등록 | 두 폰/공유기 재연결·게스트LAN 시험 |
| 마지막 재생 요청이 출력 선택 | 이번에 AirPlay 고정 우선권 제거, 양방향 play/resume 테스트 | 동시 이벤트, 빠른 연속 전환 실물 시험; AirPlay2 송신 앱 원격 pause는 미구현 |
| 재생/일시정지/다음/이전/탐색/볼륨 | SPIRC 처리+상태notify 있음 | 두 폰 UI 상태, 재접속, 곡 끝/큐 변경 시험 |
| 320kbps | 이번에 요청 설정 변경, 16bit44.1kHz 출력 유지 | 실제 파일선택/다운로드/CPU underrun 시험 |
| 계정/세션 복구 | 재사용 로그인NVS, retry, same-user addUser | 자동 다른 계정 인계는 현재409, 사용자 경험 수정 필요 |
| Shuffle / Repeat | 메시지는 수신하지만 notify만 함 | 큐/상태 처리 구현 필요. 현재 지원이라고 광고하지 말 것 |
| Crossfade / normalization / gapless | 완전한 지원 증거 없음 | 메모리·디코더·큐 구현 및 측정 필요 |
| Podcast/Audiobook/DJ/Jam | Spotify 앱에서 track와 비슷하게 보이는 것만으로 지원 아님 | 포맷·진행상태·서버기능 별도 구현; 현 단계 미지원/미확인 |
| Lossless | cspot 현재 Vorbis 경로로 안 됨 | DAC 사양으로 약속 불가. 공식 Soloist Linux 대안에서는 별도 지원 |
| A2DP+Spotify+AirPlay2 | WROVER 펌웨어에서 세 경로를 하나의 출력 소유권(`audio_source.c`)으로 통합. A2DP 48kHz는 I2S 클럭 전환, 알림음은 출력 획득 안 함. 빌드·호스트 테스트 통과 | 실기기에서 Wi-Fi/BT 공존 끊김, 내부 heap 최저치, 페어링/AVRCP, 스마트폰 전환 측정 |
| 업데이트 | OTA 파티션·웹 리소스 존재 | 네트워크실패·롤백·서버프로토콜 변경 대응 시험 |

상용 UX 참고 요구: 검색 계속 유지, 계정 제어는 Spotify 앱, 마지막 사용자 요청으로 소스 선택, 볼륨 상태 전달. 이를 구현하는 데 제품 인증 자체를 선행 조건으로 삼지 않는다. 공식 eSDK는 공개 호환 SDK로 대체할 수 없고, OSS server compatibility와 아직 없는 feature는 별도로 명시한다.

## 검증 순서

1. Spotify 실계정으로 검색→첫 선택→곡 재생→다음/이전/탐색/볼륨→재부팅 로그인 복구.
2. 같은 계정 폰A 시작→폰B 제어→A 종료/전원OFF→재생 유지→B에서 phone/보드로 출력 전환.
3. 다른 계정 인계 구현 후 폰B 선택→소유권 교체→A 상태 반영 및 기존 로그인 잔류 없음 확인.
4. AirPlay↔Spotify 양방향 및 빠른 반복 전환, 이전 세션 종료가 현재 출력을 끊지 않는지 확인.
5. (코드 통합 완료) 실기기에서 pairing/AVRCP/스마트폰 전환 및 Wi-Fi/BT 공존 peak heap/underrun 확인.
6. 320kbps·긴 재생·Wi-Fi 재연결·OTA rollback 시험 후 메모리/생산부품 확정.

이 문서는 조사와 현재 코드 감사 결과다. 테스트 없는 항목을 구현 완료나 실제 지원 기능으로 표시하지 않는다.
