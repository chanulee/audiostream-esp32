# LOVELACE / AS-007 rev A (보관, 버전 기록 09)

ESP32-WROVER-E-N8R8 + PCM5102A, **37 × 41 mm, 4층**, KiCadRoutingTools 배선. LCSC 엔지니어 회신대로 AUX 잭(J2) 단자 배정을 고친 판입니다(A = Tip, D = Ring 1, B·C = GND). 주문하지 않았습니다.

이 폴더의 파일은 2026-10-18 커밋 `8e44d02` 시점 그대로입니다.

| 파일 | 내용 |
|---|---|
| `lovelace-as-007.kicad_pcb`, `.kicad_sch` | 보드와 회로도. 풋프린트는 파일 안에 들어 있어 KiCad로 바로 열립니다(3D 모델은 `hardware/lovelace-as-008/lib/3d/`에 있음) |
| `lovelace-as-007-revA-release.zip` | Gerber, drill, IPC-D-356, JLC BOM / CPL. SHA-256 `99f5318f815b9582a004e5b17b560f92eff92da18d63902b64472b8c75c9c924` |
| `REVIEW.md`, `REVIEW_NETLIST.md`, `REVIEW_LAYOUT.md`, `REVIEW_KICAD_HAPPY.md`, `BRINGUP.md` | 당시 검토 문서와 첫 보드 절차. 링크와 경로는 당시 폴더(`hardware/lovelace-as-007/`) 기준입니다 |
| `renders/` | `render_board.py` 출력과 `renders/extra/`(3D 뷰, 회로도·층 PDF) |

생성 스크립트는 같은 폴더에서 AS-008로 이어져 따로 보관하지 않았습니다. 커밋 `8e44d02`에서 `hardware/lovelace-as-007/`을 꺼내면 그대로 다시 만들 수 있습니다.

## AS-008로 올린 이유

이 판은 그대로 만들어도 동작할 것으로 봅니다(kicad-happy 검토, `REVIEW_KICAD_HAPPY.md`). 주문 전이라 검토에서 나온 구리 변경 두 가지를 반영했습니다.

| 항목 | AS-007 | AS-008 |
|---|---|---|
| USB_DM via 4개 | 0.4 / 0.2mm. JLC 다층 기판의 최소 지름 0.45mm보다 작고 "한계값"(0.4mm)에 걸림 | 0.45 / 0.2mm. 넷 클래스와 보드 최소값도 0.45mm |
| U6 ITIMER(10번) | 연결 없음(가장 빠른 과전류 응답) | 미실장 0402 C26(ITIMER–GND). Wi-Fi 피크가 전류 제한(ILIM)에 걸리면 1–10nF를 달아, ILIM–2 × ILIM 사이 짧은 피크를 nF당 약 0.8ms 통과시킴. 다시 만들 필요 없음 |
| R16 위치 | U6 오른쪽 (16.55, 34.85) | C26에 자리를 내주고 U6 EN/UVLO 옆 (11.7, 35.88) |

회로·BOM은 같고, CPL은 R16 한 줄만 바뀝니다.
