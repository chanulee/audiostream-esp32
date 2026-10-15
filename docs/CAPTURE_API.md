# PCM 캡처 API

빌드 옵션 `CONFIG_AUDIO_CAPTURE_ENABLED=y`에서만 등록됩니다. 기존 웹 서버와 같은 포트를 사용합니다. I2S로 나가는 AirPlay·Spotify·Bluetooth 출력을 캡처합니다. `lovelace-as-002-capture` 환경에서 켜집니다.

| 요청 | 결과 |
|---|---|
| `POST /api/capture/start?seconds=3` | 1–10 정수 초. 이전 캡처를 초기화하고 대기. JSON 상태 반환 |
| `GET /api/capture/status` | `state`, `frames`, `target_frames`, `sample_rate`, `channels`, `bits` |
| `GET /api/capture/wav` | 완료된 클립을 WAV로 chunk 전송. 미완료 시 HTTP 409 |

상태는 `idle → armed → recording → complete`입니다. 오디오 PCM이 도착하면 녹음이 시작됩니다. 완료 시 버퍼는 다음 start까지 고정됩니다. PSRAM 할당 실패는 503이며 이전 클립을 보존합니다. start는 진행 중인 녹음도 취소하고 새로 시작합니다. 기존 웹 서버는 단일 요청 태스크를 사용하므로 다운로드 동안 다른 API 처리는 대기합니다. 다운로드 실패 시 버퍼는 재다운로드할 수 있습니다.

WAV 데이터는 little-endian stereo PCM16입니다. 프레임은 4바이트이고 WAV 파일의 길이는 `44 + frames * 4`입니다. 시작 직후부터 재생 중인 경우 다음 버퍼부터 녹음합니다. 음원의 원본 sample rate 대신 출력 sample rate를 기록합니다. Bluetooth 48kHz 스트림은 48kHz WAV가 됩니다. 녹음 중 출력 주파수가 바뀌면 상태가 `rate_changed`가 되고 WAV는 409로 거절합니다.

인증·파일 지속 저장·실시간 스트리밍 기능은 없습니다. 캡처를 대기 상태로 두더라도 첫 PCM 이후에는 I2S 언더런 무음으로 지정 길이를 채웁니다. 이 도구는 수신/디코딩 결과를 확인하기 위한 개발 도구입니다.
