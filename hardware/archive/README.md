# 하드웨어 버전 기록

| # | 버전 | 크기 | 날짜 | 상태 | 폴더 |
|---|---|---|---|---|---|
| 01 | AudioStream S3 rev A (ESP32-S3) | 80 × 60 mm | 2026-10-14 | 보관 | [01-audiostream-s3-revA](01-audiostream-s3-revA/README.md) |
| 02 | LOVELACE AS-001 (ESP32-S3) | 55 × 55 mm | 2026-10-14 | 보관 | [02-lovelace-as-001](02-lovelace-as-001/README.md) |
| 03 | LOVELACE AS-002 rev B (WROVER) | 35 × 50 mm | 2026-10-14 | 보관, 이미지만 | [03-lovelace-as-002-revB](03-lovelace-as-002-revB/README.md) |
| 04 | LOVELACE AS-002 rev C (WROVER) | 37 × 41 mm | 2026-10-15 | 보관 | [04-lovelace-as-002-revC](04-lovelace-as-002-revC/README.md) |
| — | **LOVELACE AS-003 rev A** (WROVER) | 37 × 41 mm | 2026-10-15 | **현재**, 주문 전 | [../lovelace-as-003](../lovelace-as-003/README.md) |

렌더를 나란히 보려면 [index.html](index.html)을 엽니다(현재 보드의 `renders/latest/index.html` 아래쪽에도 같은 기록이 있습니다). 둘 다 `hardware/versions.json`에서 만들어집니다.

## 버전 규칙

- **AS-<n>**: 새 설계입니다. 주문 전에 넷리스트나 외곽이 바뀌면 번호를 올립니다.
- **rev A, B, …**: 주문한 뒤에 같은 설계를 고친 판입니다. 실크에 `AS-003 rev A`처럼 찍히고, KiCad title block, 릴리스 zip 이름(`lovelace-as-003-revA-release.zip`)에도 같은 값이 들어갑니다.
- 값은 `plan_pcb.py`의 `BOARD_ID`, `BOARD_REV` 한 곳에서만 정합니다.
- 새 버전을 시작할 때는 현재 폴더를 `archive/NN-<이름>/`으로 복사해 보관합니다. 그다음 현재 폴더 이름과 `BOARD_ID`를 올리고, `versions.json`에 항목을 추가합니다.
- 주문한 판은 git 태그 `hw/<board>-rev<X>`(예: `hw/as-003-revA`)로 표시합니다.
- 펌웨어 버전(`firmware/version.txt`)은 하드웨어와 따로 올립니다. 호환 범위는 루트 README에 적습니다.
