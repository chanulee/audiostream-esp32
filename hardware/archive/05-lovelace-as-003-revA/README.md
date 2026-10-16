# LOVELACE / AS-003 rev A (보관, 버전 기록 05)

ESP32-WROVER-E-N8R8 + PCM5102A, **37 × 41 mm, 4층**, KiCadRoutingTools 배선. AS-002 rev C의 AUX 잭 배정, DAC 뮤트(XSMT → GPIO22)·홀드업, JLC CPL 회전, 배선을 고친 판입니다. 주문하지 않았습니다.

이 폴더의 파일은 2026-10-16 커밋 `c8e4b74` 시점 그대로입니다.

| 파일 | 내용 |
|---|---|
| `lovelace-as-003.kicad_pcb`, `.kicad_sch` | 보드와 회로도. 풋프린트는 파일 안에 들어 있어 KiCad로 바로 열립니다 |
| `lovelace-as-003-revA-release.zip` | Gerber, drill, IPC-D-356, JLC BOM / CPL. SHA-256 `86ebc3f8a43c1e4256cf45ec191f5daa3e95f3ead39808d2759972801f75efd2` |
| `REVIEW.md`, `REVIEW_NETLIST.md`, `REVIEW_LAYOUT.md`, `BRINGUP.md` | 당시 검토 문서와 첫 보드 절차. 링크와 경로는 당시 폴더(`hardware/lovelace-as-003/`) 기준입니다 |
| `renders/` | `render_board.py` 출력(PCBA, 맨 기판, 배치도, 층별 구리, 배선도) |

생성 스크립트는 같은 폴더에서 AS-004로 이어져 따로 보관하지 않았습니다. 이 커밋에서 `hardware/lovelace-as-003/`를 꺼내면 그대로 다시 만들 수 있습니다.

## AS-004로 올린 이유

넷리스트·부품·배치는 바뀌지 않았습니다. 바뀐 것은 배선뿐입니다. 이 판의 처음 배선에는 상단 SMD 패드에 닿는 via가 10개 있었습니다. 그중 4개는 패드 안(R17.1, R10.2, U4.1, U1.34)에 있었습니다. 위 release ZIP은 이를 고친 뒤의 배선입니다. 같은 "AS-003 rev A" 이름으로 Gerber가 두 가지 생긴 셈이라, 혼동을 막으려고 고친 배선을 AS-004 rev A로 올렸습니다. AS-004의 Gerber는 이 폴더의 ZIP과 구리가 같고, 실크의 보드 번호만 다릅니다.
