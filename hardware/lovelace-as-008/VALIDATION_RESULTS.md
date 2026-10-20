# AS-008 보강 검사 실행 결과 — 2026-10-20

**새 검사에서도 현재 AS-008 rev A의 필수 정적 검사와 동작 모델 기준은 통과했다. PCB·BOM·주문 ZIP을 바꿀 새로운 설계 오류는 발견하지 않았다. 실물 동작·전원 품질·팝 검증 완료라는 뜻은 아니다.**

[실행 계획](ACTION_PLAN.md) 2-3·2-4를 적용했다. 전체 보드를 재생성/재배선하지 않고 현재 동결된 설계, 저장된 PCB/회로도, 제조 파일을 검사했다. 재고 재조회·주문 화면 확인·결제는 이번 작업 범위에 포함하지 않았다.

## 바뀐 검사

- `pinout_check.py`: 커패시터 값·두 단자·필수 실장과 C25 극성, C26의 의도적인 DNP를 검사한다. 부품 누락·중복·잘못된 필수 속성도 거부한다. 기대값은 생성기의 테이블을 자동 복사하지 않는다.
- `audit_pcb.py`: 기존 위치/넷 검사에 실제 PCB 부품값·DNP 일치 검사를 추가했다. `design.json`만 맞고 저장된 PCB의 값/실장이 다른 경우도 거부한다.
- `sim/power_path.py`: 30초 timeout, 프로세스 종료 코드, stderr/수렴 오류, 마지막 해석 시각, 모든 필수 측정값의 존재·유한성을 검사한다. 일부 측정값 또는 exit 0만으로 PASS 처리하지 않는다.
- 전원 해석 미완료는 `UNVERIFIED` 및 exit 2, 모델 기준 미달은 `FAIL` 및 exit 1로 구분한다. 원시 회로와 로그는 `reports/sim-cases/`, 요약은 [`reports/sim.json`](reports/sim.json)에 저장한다.
- `make_board.sh`: 기존 핀 검사에 이어 전원 동작 모델 검사를 release 생성 전에 실행한다. 검사 실패/미완료 시 새 release 생성을 중단한다. 기존 ZIP이 남아 있는 것은 새 빌드 성공의 증거가 아니다.

## 실행 결과

| 검사 | 결과 |
|---|---|
| 핀·수동부품·실장 계약 | **305/305 일치** |
| 독립 검토의 의도적 오류 주입 | **7/7 검출**, 정상 입력 통과 |
| 추가 보강 회귀 테스트 | **13개 테스트 통과**. 삭제/중복/잘못된 속성, PCB 값/DNP 불일치, 미완료 시뮬레이션, 3.1V 경계, release 중단 포함 |
| KiCad DRC / 미연결 / schematic parity | **0 / 0 / 0** |
| KiCad ERC | **0** |
| PCB readback | 55개 부품 위치·넷·값·DNP 일치 |
| 디커플링 거리 / 라이브러리 패드 | **19/19 / 55/55** |
| 상단 SMD 패드 안 via | **0** |
| 배치 검사 | ERROR **0**, WARN **0** |
| release 파일 감사 | 17개 파일, errors **0**, warnings **0** |
| Gerber ↔ IPC 연결성 | shorts **0**, opens **0**, 구리 없는 패드 **0**, undrilled **0**. 패드/via **331/331**에 구리 존재 |
| 전원 동작 모델 실행 | **55/55 완주**, 실행 오류 **0** |
| 필수 모델 조건 | 기동 **3/3**, 0.37A 펄스 부하 **6/6**, 홀드업 **16/16 PASS** |
| 추가 과부하 탐색 | **30조건 STRESS_ONLY**. 전부 정상 동작했다는 뜻이 아니며 전압 붕괴/전류 제한 원시 수치를 별도 보관 |
| 전체 호스트 검사 | C/C++ 검사 통과. Python **30개 중 24개 통과, 6개 skip**(기존 실크 편집기의 KiCad Python 전용 테스트) |

오류 주입 7건은 PCM5102A FMT 오배선, CH340N TXD 오배선, R15 510Ω, C25 22µF, C12 DNP, C15 디지털 전원 이동, C17 10nF다. 추가 PCB readback 테스트는 KiCad가 읽은 보드 객체의 C25 값과 C12 DNP를 메모리에서 바꾸어 거부 여부를 확인하며 원본 PCB는 저장하지 않는다.

KiCad CLI 병렬 실행 때 종료 과정에서 lock-file 경고가 나와 DRC와 ERC를 순차 재실행했다. 재실행도 위반 0이며 lock-file 오류는 없었다. KiCad의 fontconfig 경고와 기존 Python wx 초기화 진단은 남았으나 검사 결과 데이터와 개별 감사 조건은 정상으로 확인했다.

## 홀드업 판정

입력 5.0/4.4V × ESP 부하 80/250mA × C25 220/176µF × DAC 부하 31/45mA의 16조건을 실행했다. 입력 소스 저항은 각각 0.1/0.3Ω다. 모든 실행은 150ms까지 완주했다.

공통 DAC 레일은 AVDD·DVDD·CPVDD를 함께 공급하므로 DVDD/CPVDD 권장 하한 **3.1V**로 판정한다. clock-stop 기준은 **3ms**이고 XSMT의 **150/fs + 0.2ms**와 혼동하지 않는다. [TI PCM5102A §8.3·§11.2](https://www.ti.com/lit/ds/symlink/pcm5102a.pdf)

| 입력 / ESP 부하 | C25 / DAC 부하 | 클럭 정지 가정 후 3.1V까지 | 3ms 대비 여유 |
|---|---|---:|---:|
| 5.0V / 80mA | 220µF / 31mA | 11.029ms | +8.029ms |
| 5.0V / 80mA | 176µF / 45mA | 5.765ms | +2.765ms |
| 4.4V / 80mA | 220µF / 31mA | 6.731ms | +3.731ms |
| 4.4V / 80mA | 176µF / 45mA | **3.441ms** | **+0.441ms** |
| 4.4V / 250mA | 176µF / 45mA | 3.569ms | +0.569ms |

가장 짧은 조건은 기존 보고서와 같은 4.4V·C25 −20%·45mA 조건이다. 기존 보고서의 2.994ms는 **3.2V까지**이고, 이번 3.441ms는 **3.1V까지**라서 두 수치를 동일 기준의 개선으로 해석하면 안 된다. 회로나 부품은 변경하지 않았다.

XSMT 경로의 요구 시간은 44.1kHz 3.601ms, 48kHz 3.325ms로 별도 기록했다. 이 모델에는 XSMT 파형·실제 DAC 뮤트 동작이 없으므로 해당 경로는 **UNVERIFIED**다. ESP32 2.43V 도달 시각을 실제 XSMT 하강 시각으로 대신하지 않았다.

## 남은 한계와 다음 단계

- 버크는 이상적인 전압원이고 LDO 강하는 고정 20mV다. 실제 제어 루프·리플·기생 성분·온도·LDO dropout 편차를 검증하지 않는다.
- DAC는 저항성 부하다. 45mA는 3.3V에서의 조건이며 전압이 떨어지면 모델 전류도 감소한다. 모든 온도·모드에서의 최악 소비전류를 보장하는 실험이 아니다.
- 0.441ms는 이 16조건과 가정 안의 시간 여유다. 실제 클럭 정지 시각과 팝 없는 종료를 보장하지 않는다.
- 다음 단계는 실행 계획의 주문 화면 확인과 첫 보드 1–7단계다. 팝·전원 품질은 별도의 8단계에서 파형으로 확인한다. 이번 결과만으로 PCB 재설계나 대량 발주를 결정하지 않는다.

## 재현

저장소 루트에서:

```sh
python3 -m unittest discover -s tests -p test_hardware_validation.py -v
python3 hardware/lovelace-as-008/pinout_check.py
python3 hardware/lovelace-as-008/sim/power_path.py
sh tools/test_host.sh
```

KiCad 검사에는 `make_board.sh`와 같은 KiCad CLI/Python 및 기존 `pcb-layout-skill` 검사 스크립트를 사용했다. 원시 DRC/ERC와 실행 로그는 `work/independent-stress-20261020/strengthened-*`에 보관했다. 전체 `make_board.sh` 재생성은 하지 않았고, 실제 스크립트가 핀 실패 및 전원 검사 exit 1/2에서 보드 생성 전 중단하는지는 임시 디렉터리의 회귀 테스트로 확인했다.

## 검사 대상 고정

아래 파일은 작업 시작 때와 SHA-256이 같으며 변경하지 않았다.

| 파일 | SHA-256 |
|---|---|
| design.json | `bf7849110d0e9f6c8939a1ea7c03d91768cf016558283e19154efd07535cec72` |
| lovelace-as-008.kicad_pcb | `84081de12d6fc12277b90378a8de1a7ca73551c62f8aba34c9f0055b1b113218` |
| release ZIP | `01da18469ebcb7702c129164d3dc142bf781da75446652fb82398336b2845529` |
| bom.csv | `63efb1a932b8444062064e5163f01547d461f085fff92a41f919e3ea00788fb6` |
| cpl.csv | `d836b545e0dbe416fe5d3f2d6747f33e5226ebdd0a2a1dfac366df7fc4c0a239` |
