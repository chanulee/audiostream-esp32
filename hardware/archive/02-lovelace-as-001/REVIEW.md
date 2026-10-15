# AS-001 재검토 — 2026-10-14

검토 범위: 회로·native PCB·실제 핀넷·저장된 fill·Gerber/drill/IPC·펌웨어 이벤트. **제작 승인 보류: 실물 검증과 아래 Major 항목의 해소가 필요합니다.** Critical 0 / Major 4 / Minor 1. 결과는 소프트웨어/정적 검사이며 실제 제품 시험은 아닙니다.

## 남은 발견 사항

1. **[Major] USB 90Ω / 리턴 경로 미확정** — B11은 D+/D− 90Ω pair를 요구합니다. 현재 연결/간격은 통과했으나 제조사 스택업이 없고 autorouter로 배선한 pair의 impedance/skew를 확정하지 않았습니다. USB_DM의 분기 포함 비아 합계를 pair의 층 변경 수로 해석하면 안 됩니다. 영향: PC 연결/다운로드 불안정 가능. 수정: 제조 스택업을 확정하고 pair 전용 재배선, branch별 길이 및 리턴 via 확인. 신뢰도: 높음.
2. **[Major] 전원 경로 여유 및 B5/B7/B8 미완료** — VBUS/+5V/+3V3_D의 최소 선폭 0.15mm, 일부 경로 단일 전원 비아입니다. B5의 IN/OUT 각 25mm² bar와 B7 bulk 양패드 각각 2개 비아를 일괄 충족하지 않습니다. B8 모든 regulator ground에 전용 via라는 요구도 일부는 면 연결로 대체되어 있습니다. 아래 계산은 정상 0.55A에서 좁은 배선의 25% 여유가 부족하고 최대 전류 제한값에서 더욱 부족함을 보여줍니다. 영향: 레일 droop/열/접지 임피던스. 수정: 전원 넓은 구리·병렬 비아를 직접 설계하고 부하/온도 측정. 작은 저전류 보드라는 이유만으로 규칙 준수로 처리하지 않았습니다. 신뢰도: 높음.
3. **[Major] 구매 부품/PCBA 승인 미완료** — 수동 부품의 일부 MPN 칸은 사양이며 주문 코드가 아닙니다. C6=47µF 선택은 3.3V DC bias 후 유효 용량 확인이 필요합니다. 자체 RPW HotRod 10-pin 풋프린트는 TI 권장 pattern 기준이지만 paste/회전/실물 맞춤 독립 검토가 남아 있습니다. 영향: 잘못된 부품/조립/전원 안정성. 수정: supplier 확정 및 assembler BOM/CPL/footprint 승인. 신뢰도: 높음.
4. **[Major] 전원 보호·USB 규격 실물 시험 없음** — OVLO는 명목 5.376V, 계산 worst range 5.292–5.488V, raw cap 100nF/50V, eFuse soft-start 회로를 추가했습니다. 정적 설계로 빠른 과도전압 차단을 증명할 수 없습니다. CC advertised current 검출·열거 전 전류 규격도 구현/검증하지 않았습니다. OFF 상태 PC USB data 역급전 시험 필요. 수정: 5V 정상/9–20V 이상입력/ON-OFF/돌입전류 시험; 필요한 경우 USB current detection, data isolation 또는 전원 구조 보완. 신뢰도: 높음.
5. **[Minor] power-off pop / 케이스 fit 미검증** — DAC XSMT는 풀업 상태이며 전원 소실 선제 mute 회로는 없습니다. USB/스위치의 일부 3D 모델이 없어 렌더만으로 케이스 fit를 판단할 수 없습니다. 수정: 실제 AUX pop/noise, 커넥터·스위치·안테나 케이스 fit 확인. 신뢰도: 중간.

## 전원 경로 계산과 제한

가정: 외층 1oz, 내층 0.5oz, 1.6mm PCB, via 도금 25µm, 온도 상승 10°C. MCU 3.3V 0.5A peak + DAC digital 0.01A + analog 0.05A, buck 효율 90%에서 여유 포함 입력 검토 전류 0.55A. 실제 측정값 아님.

| 경로 | 검토 전류 | 실제 최소 / 제한 요소 |
|---|---:|---|
| VBUS → eFuse → +5V | 0.55A 정상; ILIM 명목 0.671A, +15% 가정 0.772A | 0.15mm neck, +5V via 2개가 서로 다른 branch일 수 있으므로 병렬로 합산 금지. 가장 좁은 trace / 경로별 단일 via가 제한 요소 |
| Buck → digital 3.3V | 0.51A | 최소 0.15mm, L1→C6 국부 0.8mm; 경로별 단일 전원 via / 배선 neck |
| LDO → analog 3.3V | 0.05A | 최소 0.15mm, 공급 via 1개; 실제 noise/return impedance가 핵심 |

스킬 `pcbcalc.py trace-width --current-a .55 --width-mm .15 --copper-oz 1 --temp-rise-c 10 --length-mm 10`: 필요한 폭 약 0.132mm, 25% 여유 권장 약 0.166mm. `.772A` 같은 조건은 필요한 폭 약 0.211mm, 여유 포함 약 0.264mm입니다. 10mm 길이는 비교 가정이며 실제 각 경로 길이가 아닙니다. `via-current --hole-mm .3 --plating-um 25 --count 1 --board-mm 1.6 --temp-rise-c 10`: 0.7 derating 후 단일 via 약 0.628A. 실제 도금·온도·IPC-2152/측정으로 재평가해야 합니다. 상세 JSON은 reports에 있습니다.

## 이번에 수정 / 확인한 사항

- 80×60 → 55×55mm, 단면 실장. 안테나 외곽 돌출 / M3 keepout 유지, 제품·버전 실크 변경.
- TPS25947 eFuse, OVLO, soft-start, OFF/ON 스위치, 녹색 status LED 추가.
- DAC flying cap과 디커플링을 실제 공급 pad 방향에 맞췄고 18/18 거리 목표 통과.
- buck SW 경로가 VOS를 가로지르던 초안 수정. 최소 0.15mm 보정 / buck ground direct zone 연결 / BOOT label 위치 조정은 후보 파일에서 DRC 후 최종본에 적용. 후보와 적용본 byte 비교 일치.
- 좌표·핀넷 readback 일치, 고정 anchor baseline changes 0. L2/L3 signal 0, 0/45/90 이외 track 0. USB shell 내 top trace endpoint 0. 이 endpoint 검사는 shell 전체 기하 검사의 대체가 아니며 zone keepout과 native DRC/시각 확인을 함께 사용.
- ERC/DRC 0, 미연결 0. Gerber netcheck 310/310, shorts/opens/missing/undrilled 0. 제작 파일 audit 0/0, silk-on-mask 0, copper-edge 약0.505mm.
- 상·하 거버/3D와 4개 구리층 시각 확인: 실크 읽힘, 뒷면 텍스트 없음, 안테나 바깥 구리 없음, 내부 GND 신호 슬롯 없음. 부품 모델 일부 없음.
- Spotify begin/pause/resume/end 이벤트를 LED에 반영. 2026-10-14 후속 수정에서는 AirPlay 고정 우선권을 제거하고 양방향 재생/재개 전환과 비활성 세션 flush/LED 보호를 추가했습니다. 호스트 테스트 및 새로운 lovelace-as-001 profile 빌드 성공.

## 스킬/API에 대한 정확한 답

스킬 Python checker/calculator/release tools와 KiCad pcbnew API를 사용했습니다. EasyEDA Pro API는 사용하지 않았습니다. KiCad 지원은 스킬에 명시되어 있습니다. 하지만 이전 결과 및 현재 시제품을 스킬 모든 규칙을 완전히 만족한 결과라고 말하면 부정확합니다. 특히 위 B5/B7/B8/B11이 미완료입니다. DRC/거버 0만으로 ready-to-order라고 선언하지 않습니다.

이전 80×60 제조 ZIP은 `hardware/archive/01-audiostream-s3-revA/audiostream-s3-rev-a-prototype.zip`로 보존했습니다. 크기/부품/회로가 크게 바뀌어 거버 차이는 전체에 걸쳐 발생하므로 좌표 baseline은 새로운 55×55 고정 anchor에 대해 검사했습니다. 두 릴리스 차이 검사 기록은 reports/legacy-gerber-diff.txt에 있습니다.
