# LOVELACE / AS-002 rev C (보관, 버전 기록 04)

ESP32-WROVER-E-N8R8 + PCM5102A, **37 × 41 mm, 4층**, FreeRouting 배선. rev B보다 면적을 13% 줄였고, 전원 스위치와 RESET 버튼을 없앴습니다(USB를 꽂으면 켜짐). AUX 잭은 SMD PJ-320D로 바꿨습니다. 주문하지 않았습니다.

`lovelace-as-002.kicad_pcb`는 2026-10-15 검토를 시작할 때의 보드 파일 그대로입니다. KiCad로 열 수 있고, 풋프린트는 파일 안에 들어 있습니다. 생성 스크립트는 같은 폴더에서 AS-003으로 이어져, 따로 보관하지 않았습니다. `renders/`는 `render_board.py`로 이 파일에서 다시 그린 것입니다.

이 버전에서 발견해 **AS-003에서 고친 문제**는 다음과 같습니다.

- AUX 잭 Tip/Ring 배정 오류: Tip(L)이 접지되고 R이 슬리브와 쇼트됨.
- PCM5102A XSMT가 3.3V에 고정되어, 부팅·전원 차단 때 팝을 막을 수단이 없음.
- CPL에 KiCad 회전을 그대로 써서, JLC에서 U2·U4·U5·U7이 돌아가고 C25 극성이 뒤집힐 상황.
- 고정 홀 없음.

다음 버전: [AS-003](../../lovelace-as-003/README.md). 전체 기록: [archive/README.md](../README.md).

`renders/earlier/`에는 이전 세션에서 이 버전을 렌더한 이미지와 3D 모델(`.glb`)을 함께 보관했습니다.

`renders/earlier/`에는 이전 세션에서 이 버전을 렌더한 이미지와 3D 모델(`.glb`)을 함께 보관했습니다.
