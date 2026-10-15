# Spotify Connect 통합

현재 S3 프로필은 AirPlay와 Spotify Connect를 함께 빌드합니다. Spotify는 기기 검색 → 계정 연결 → Spotify 서버 인증 → 곡 메타데이터·오디오 키·CDN 주소 요청 → 다운로드·복호화·Vorbis 디코딩 → 공통 I2S 출력 경로까지 연결했습니다. 실제 계정과 보드로 재생을 확인하는 검증은 아직 남아 있습니다.

## 사용 조건과 설정

- ESP32-S3 N16R8, 2.4GHz Wi-Fi 및 인터넷 연결.
- Spotify Premium 계정. 초기 기기 연결에는 폰/Mac과 같은 LAN 및 mDNS 통신이 필요합니다.
- 본인의 Spotify 개발자 앱 Client ID / Client Secret. [Spotify Dashboard](https://developer.spotify.com/dashboard)에서 확인합니다. 이 구현은 사용자 OAuth 리다이렉트 서버를 사용하지 않습니다.

1. README의 명령으로 펌웨어와 SPIFFS를 업로드하고 집 Wi-Fi에 연결합니다.
2. 보드의 `http://<IP>/spotify`를 엽니다. 일반 설정 페이지에도 Spotify 링크가 표시됩니다.
3. Client ID / Client Secret을 저장하고 보드를 재부팅합니다. 값은 NVS에 저장되며 GET 응답이나 설정 화면으로 반환하지 않습니다. 계정 비밀번호는 입력하지 않습니다.
4. Spotify 앱의 기기 선택 목록에서 보드를 선택하고 재생합니다. 기본 기기 이름은 AirPlay와 같은 `ESP32 AirPlay`이며, 일반 설정에서 바꾸고 재부팅할 수 있습니다.
5. DAC 없이 확인하려면 `python3 tools/capture.py http://<IP> --seconds 3 -o spotify.wav`를 실행하고 Spotify 재생을 시작합니다. 명령 실행 전에 이미 재생 중이면 다음 PCM부터 캡처합니다.

Client Credentials 요청은 [Spotify의 문서](https://developer.spotify.com/documentation/web-api/tutorials/client-credentials-flow)에 맞춰 HTTPS POST로 처리합니다. 사용자 계정 인증은 별도의 Zeroconf 로그인 블롭과 Spotify AP 세션을 사용합니다. 이 두 인증 정보의 역할은 다릅니다. HTTPS 인증서와 호스트 이름을 검증하며, 인터넷 시간 동기화를 시작한 뒤 연결합니다.

Client Secret과 재사용 로그인은 이 개발용 보드의 NVS에 저장됩니다. 기본 NVS는 암호화되지 않으며 설정 페이지는 LAN HTTP입니다. 신뢰하는 개인 네트워크에서 사용하세요. 펌웨어 소스나 Git에는 본인의 Secret을 넣지 않습니다.

## 출력과 전환

- 두 소스 모두 같은 재생 태스크에서 I2S를 씁니다. 별도 태스크가 동시에 DAC를 쓰지 않습니다.
- Spotify PCM은 64KB PSRAM FIFO에 넣습니다. 버퍼가 차면 디코더에 backpressure를 적용합니다.
- AirPlay·Spotify·Bluetooth에 고정 우선순위는 없습니다. 새 재생/재개 요청이 출력을 가져옵니다. 이전 소스는 일시정지 요청(Spotify yield, AVRCP pause)을 받고 대기 PCM은 버립니다.
- 검색과 AirPlay 세션은 유지합니다. AirPlay 2의 원격 MRP pause는 구현하지 않았으므로 송신 앱이 일시정지 상태로 바뀌는 것까지 보장하지 않습니다. 비활성 Spotify/AirPlay 세션의 늦은 flush/end/LED 이벤트는 현재 선택된 출력에 영향을 주지 않도록 처리합니다.
- Spotify의 일시정지·다음·이전·탐색·볼륨을 처리하며, 기기의 재생 제어도 현재 소스에 전달합니다. 음소거는 볼륨 0과 이전 볼륨 복원으로 처리합니다.
- 볼륨은 별도로 관리하고 변경 후 NVS에 저장합니다. 출력의 볼륨 램프·채널 선택·WAV 캡처를 공유합니다.
- 현재 Spotify 요청 품질은 Ogg Vorbis 320kbps이며 실물 부하 검증은 남아 있습니다. 현재 지원 프로필은 I2S / 44.1kHz 출력입니다. 이식한 Vorbis 경로는 44.1kHz stereo 스트림을 받으며, 다른 포맷은 오류를 기록하고 재생하지 않습니다. LOVELACE 펌웨어는 Spotify와 Bluetooth를 함께 빌드합니다. 이 조합의 내부 RAM 여유와 Wi-Fi/BT 공존 상태의 끊김은 실기기에서 측정해야 합니다.

곡 시작 알림은 PCM이 출력 FIFO에서 빠지는 시점에 보냅니다. 실제 I2S 출력과는 DMA 지연만큼 차이가 있습니다. 이는 정밀한 멀티룸 동기화 기능을 제공하지 않습니다.

## API와 문제 확인

| 경로 | 기능 |
|---|---|
| `GET /spotify` | 설정 화면 |
| `GET /spotify_info?action=getInfo` | Spotify Zeroconf 기기 정보 |
| `POST /spotify_info` | Spotify 앱의 form-encoded `addUser` 요청 |
| `POST /api/spotify/config` | `client_id`, `client_secret` form 저장, 재부팅 후 적용 |
| `GET /api/spotify/status` | 상태, 계정 연결 여부, 곡 정보·볼륨. Secret은 반환하지 않음 |
| `POST /api/spotify/forget` | 계정 로그인만 삭제. 개발자 앱 설정은 유지 |

`needs_configuration`은 개발자 앱 설정이 없는 상태, `waiting_for_login`은 앱의 기기 연결 대기, `connecting`은 서버 인증 중, `connected`는 로그인 완료입니다. `playing`, `paused`, `connection_failed`도 표시합니다. 네트워크 오류는 재시도하며, 계정 인증 거절은 저장된 계정 정보를 지우고 다시 연결을 기다립니다. 다른 계정으로 바꾸려면 설정 화면의 계정 잊기를 먼저 실행하세요.

기기가 안 보이면 같은 LAN인지, 기기 격리와 mDNS 차단이 없는지 확인합니다. 기기는 보이지만 재생하지 못하면 UART 로그에서 인증·토큰·storage-resolve·Vorbis 오류를 확인합니다. 곡 다운로드 주소를 얻는 `storage-resolve`는 비공식 Spotify 내부 인터페이스라 서버 변경이나 개발자 앱 권한에 따라 실패할 수 있습니다. 유효한 Client ID / Secret만으로 실제 곡 재생을 보장할 수는 없습니다.

## 확인한 범위

- `lovelace-as-003` (WROVER) 펌웨어 빌드·링크.
- PCM FIFO 경계·랩어라운드·backpressure.
- AirPlay/Spotify/Bluetooth 출력 소유권 전환, 중단 후 재개, 일시정지 시 버퍼 유지, flush 시 이전 PCM 삭제, 볼륨 범위.
- 연결 폼의 percent encoding, `+`, 중복 키, 잘못된 입력 거절.
- WAV 헤더 및 Mac 다운로드의 파일 보존·잘린 데이터 검사.

실제 기기 검색, Premium 계정 로그인, Spotify 서버/CDN 접근, 연속 곡 재생 및 음질은 보드와 본인의 계정으로 확인해야 합니다. 소스 출처와 배포 관련 조건은 [UPSTREAM.md](UPSTREAM.md)를 참고하세요.

## 2026-10-14 기능 검토

[공식 SDK / Soloist / 오픈소스 / Reddit 조사와 다중 휴대폰·Bluetooth·Flash 검토](CONNECT_RESEARCH.md)를 참고하세요. 같은 Spotify 계정의 다른 휴대폰 제어는 cspot SPIRC user 채널 구조가 처리할 수 있지만 실제 두 기기 검증은 남아 있습니다. 다른 계정으로의 자동 소유권 전환은 아직 구현하지 않았습니다. Shuffle/Repeat 메시지는 현재 수신 후 notify만 수행하므로 동작 지원으로 표시하지 않습니다.
