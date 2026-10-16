# LOVELACE / AS-004 rev A (보관, 버전 기록 06)

ESP32-WROVER-E-N8R8 + PCM5102A, **37 × 41 mm, 4층**, KiCadRoutingTools 배선. AS-003과 넷리스트·배치가 같고, 상단 SMD 패드에 닿던 via를 없앤 배선입니다. 주문하지 않았습니다.

이 폴더의 파일은 2026-10-16 커밋 `4f9fd6f` 시점 그대로입니다.

| 파일 | 내용 |
|---|---|
| `lovelace-as-004.kicad_pcb`, `.kicad_sch` | 보드와 회로도. 풋프린트는 파일 안에 들어 있어 KiCad로 바로 열립니다 |
| `lovelace-as-004-revA-release.zip` | Gerber, drill, IPC-D-356, JLC BOM / CPL. SHA-256 `022dbf24257904e7c45229e8b02280edff5600e331298c839451dc7562eea1df` |
| `REVIEW.md`, `REVIEW_NETLIST.md`, `REVIEW_LAYOUT.md`, `BRINGUP.md` | 당시 검토 문서와 첫 보드 절차. 링크와 경로는 당시 폴더(`hardware/lovelace-as-004/`) 기준입니다 |
| `REVIEW_INDEPENDENT_2026-10-16.md` | 독립 재검수. AS-005로 올린 근거입니다 |
| `renders/` | `render_board.py` 출력(PCBA, 맨 기판, 배치도, 층별 구리, 배선도). `renders/extra/`는 3D 뷰, 회로도·층 PDF |

생성 스크립트는 같은 폴더에서 AS-005로 이어져 따로 보관하지 않았습니다. 커밋 `4f9fd6f`에서 `hardware/lovelace-as-004/`를 꺼내면 그대로 다시 만들 수 있습니다.

## AS-005로 올린 이유

독립 재검수([REVIEW_INDEPENDENT_2026-10-16.md](REVIEW_INDEPENDENT_2026-10-16.md) 2절)에서 AUX 잭 J2(SHOU HAN PJ-320D, C431535)의 랜드가 제조사 도면과 다르다는 점을 찾았습니다. KiCad 기본 풋프린트를 그대로 써서 위치 결정 NPTH가 Ø1.5mm(도면 Ø1.0mm, 핀 Ø0.75mm), 패드 폭이 1.2mm(도면 1.5mm)였습니다. 불량으로 확정된 것은 아니지만 주문 전이라 랜드를 도면대로 고쳤고, 구리가 바뀌므로 번호를 올렸습니다. 넷리스트·배치·배선·BOM의 부품·CPL은 같습니다.

같은 검수의 나머지 두 항목은 보드와 무관해 번호를 올리지 않고 고쳤습니다. 펌웨어 DAC 뮤트 대기(5ms가 100Hz tick에서 0틱)는 `audio_output.c`에서, L1 전류 정격 표기는 `plan_pcb.py`와 `REVIEW_NETLIST.md`에서 고쳤습니다.
