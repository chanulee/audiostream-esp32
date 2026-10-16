# LOVELACE / AS-006 rev A (보관, 버전 기록 08)

ESP32-WROVER-E-N8R8 + PCM5102A, **37 × 41 mm, 4층**, KiCadRoutingTools 배선. AUX 잭(J2) 패드를 Shou Han 도면 위치(축에서 3.85mm)로 옮기고, J2 CPL을 위치 결정 핀 기준으로 바꾼 판입니다. J1·J2·U1에 LCSC/EasyEDA 3D 모델을 연결했습니다. 주문하지 않았습니다.

이 폴더의 파일은 2026-10-16 커밋 `b1ffa17` 시점 그대로입니다.

| 파일 | 내용 |
|---|---|
| `lovelace-as-006.kicad_pcb`, `.kicad_sch` | 보드와 회로도. 풋프린트는 파일 안에 들어 있어 KiCad로 바로 열립니다(3D 모델은 `hardware/lovelace-as-007/lib/3d/`에 있음) |
| `lovelace-as-006-revA-release.zip` | Gerber, drill, IPC-D-356, JLC BOM / CPL. SHA-256 `1776e5a4ec738caaa8a2a451bd88c7316016e06a56e59838f48fc6d022177278` |
| `REVIEW.md`, `REVIEW_NETLIST.md`, `REVIEW_LAYOUT.md`, `BRINGUP.md` | 당시 검토 문서와 첫 보드 절차. 링크와 경로는 당시 폴더(`hardware/lovelace-as-006/`) 기준입니다 |
| `renders/` | `render_board.py` 출력과 `renders/extra/`(3D 뷰, 회로도·층 PDF) |

생성 스크립트는 같은 폴더에서 AS-007로 이어져 따로 보관하지 않았습니다. 커밋 `b1ffa17`에서 `hardware/lovelace-as-006/`을 꺼내면 그대로 다시 만들 수 있습니다.

## AS-007로 올린 이유

**이 판의 AUX 잭 배선은 틀렸습니다. 이대로 만들면 오른쪽 채널이 나오지 않습니다.**

PJ-320D 도면은 단자를 개구부 쪽부터 D, C, B, A로 표시하지만, 각 단자의 기능은 적혀 있지 않습니다. AS-003부터 AS-006까지는 단자 위치가 접점 위치와 같다고 가정했습니다. 그래서 D·C = GND, B = Ring(LINE_R), A = Tip(LINE_L)으로 배정했습니다.

LCSC 엔지니어 회신(2026-10-16)은 A = Tip, D = Ring 1, C = Ring 2, B = Sleeve였습니다. 도면 회로도(OA–OD)의 순서와도 같습니다.

| 단자 (개구부 쪽부터) | 실제 기능 | AS-006 | AS-007 |
|---|---|---|---|
| D (KiCad `R2`) | Ring 1 = R | GND | LINE_R |
| C (`R1`) | Ring 2 (TRS 플러그에서는 슬리브) | GND | GND |
| B (`T`) | Sleeve | LINE_R | GND |
| A (`S`) | Tip = L | LINE_L | LINE_L |

AS-006대로 만들면 다음과 같습니다.
- 플러그의 Ring이 D 패드를 통해 접지됩니다.
- LINE_R은 B 패드를 통해 상대 기기의 접지로 들어갑니다.
- 470Ω(R12)이 전류를 제한하므로 부품이 망가지지는 않습니다.
- 펌웨어로는 고칠 수 없습니다.

AS-007은 J2 넷 배정을 고치고, ESD 다이오드 D2를 새 LINE_R 패드 옆으로 옮겨 다시 배선했습니다. J2 랜드와 BOM은 같고, CPL은 D2 한 줄만 바뀌었습니다.
