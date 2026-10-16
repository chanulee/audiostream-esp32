# AS-004 rev A 독립 재검수 — 2026-10-16

**판정: 조건부 소량 시제품 제작 가능. 완성품·양산 승인 단계는 아니다.** 현재 PCB와 주문 ZIP에서 부팅이나 오디오 출력을 막는 확정적인 단락·단선·핀 배정 오류는 발견하지 못했다. 다만 펌웨어의 뮤트 대기에 확정 오류가 있고, AUX 잭의 제조사 권장 랜드와 다른 치수는 조립업체 확인이 필요하다. 아래 1번은 펌웨어로 해결할 수 있다.

이번 작업은 검수다. 회로도, PCB, 프로젝트 규칙, BOM, CPL, 제조 ZIP, 펌웨어 소스는 수정하지 않았다. 기존 보고서의 통과 기록을 그대로 인용하지 않고 저장된 최종 파일의 복사본에서 검사했다. KiCad MCP는 연결돼 있지 않아 **KiCad 10.0.6 CLI와 pcbnew API**를 사용했다.

## 1. [P2 / 확정] 5ms DAC 뮤트 대기가 실제로는 0틱이다

- 위치: `firmware/main/audio/audio_output.c:153`, `firmware/sdkconfig.lovelace-as-004:1795`.
- 현재 코드: `vTaskDelay(pdMS_TO_TICKS(DAC_MUTE_RAMP_MS))`, 상수는 5ms. 실제 빌드의 `CONFIG_FREERTOS_HZ`는 100이다.
- ESP-IDF에 포함된 FreeRTOS 매크로는 정수 계산 `(ms * Hz) / 1000`을 사용한다. 따라서 `5 * 100 / 1000 = 0`. FreeRTOS 구현에서도 `vTaskDelay(0)`는 대기 시간을 보장하지 않고 재스케줄만 한다.
- 44.1/48kHz 전환과 source 전환·RTSP flush 경로가 `i2s_restart_muted()`를 호출한다. XSMT를 내린 직후 I2S를 끌 수 있어, **클럭이 도는 동안 소프트 뮤트를 완료한다는 설계 의도가 지켜지지 않는다.** PCM5102A는 44.1kHz에서 약 3.60ms(150 sample + 0.2ms)가 필요하다. DAC 자체 클럭 정지 뮤트도 있으므로 항상 팝이 난다는 뜻은 아니지만, 현재 코드로 팝 방지를 보장할 수 없다.
- 최소 수정: 같은 파일의 종료 핸들러처럼 `esp_rom_delay_us(DAC_MUTE_RAMP_MS * 1000)` 등 최소 5ms를 보장하는 대기로 바꾼다. 태스크 대기를 사용한다면 틱 경계에서 실제 대기가 짧아지는 경우까지 고려해야 한다. 단순히 1틱으로 올리면 최소 5ms 보장이 되지 않는다.
- 확인: XSMT 하강부터 BCK 정지까지 5ms 이상인지 계측하고, 44.1↔48kHz·소스 전환·flush에서 팝을 확인한다. 기존 호스트 테스트는 이 FreeRTOS 대기 시간을 검증하지 않는다.
- 근거: [TI PCM5102A 데이터시트, §11.2](https://www.ti.com/lit/ds/symlink/pcm5102a.pdf), 실제 빌드 설정과 FreeRTOS `projdefs.h`/`tasks.c`. 재현 수치는 `work/as004-independent-review-20261016/mute-timing.json`.

## 2. [제작 전 확인 / 치수 확정, 영향 미측정] J2 랜드가 해당 MPN 도면과 다르다

대상은 BOM의 **SHOU HAN PJ-320D / C431535**다. 새로 받은 제조사 도면 첫 페이지와 실제 PCB 및 프로젝트 라이브러리를 대조했다.

| 항목 | 제조사 권장 도면 | 현재 PCB |
|---|---:|---:|
| 위치 결정용 NPTH 2개 | Ø1.00mm | Ø1.50mm |
| 플러그 삽입 방향의 SMD 패드 폭 | 1.50mm | 1.20mm |
| 두 위치 결정 홀의 중심 간격 | 7.00mm | 7.00mm |

풋프린트 위치: `lib/Connector_Audio.pretty/Jack_3.5mm_PJ320D_Horizontal.kicad_mod:330` 이후. 실제 제조 ZIP에도 Ø1.50mm 구멍이 들어 있다. 일반 KiCad 라이브러리와 같다는 검사만으로 해당 부품의 제조사 권장 치수까지 같다고 볼 수 없다.

큰 홀은 핀 삽입을 막지는 않지만 위치 결정 여유가 커진다. 권장보다 좁은 패드와 함께 사용했을 때 리플로 중 정렬 및 반복적인 플러그 삽입에 대한 접합 품질은 현재 검사로 판정할 수 없다. **불량이 확정된 것은 아니다.** 주문 전 이 차이를 조립업체에 확인하거나, 실제 부품을 확보해 랜드와 접점을 대조한다. 수정하기로 하면 해당 MPN의 권장 랜드로 맞춘 뒤 DRC·Gerber·CPL을 다시 검사한다.

JLC 좌표를 직접 변환했을 때 J2의 패드 중심 차이는 최대 약 0.437mm였다. 이것도 기존 검사기가 0.45mm 허용오차로 통과시키는 항목이다. 단순 회전 오류로 판정하지 않았으며, 최종 PCBA 미리보기와 실물 확인이 필요하다.

현재 전기 배정은 잭 앞쪽부터 `GND / GND / LINE_R / LINE_L`. 뒤쪽 단독 패드를 Tip으로 해석한 설계와 일치한다. 다만 부품 치수 도면·라이브러리 대조를 실물 TRS 플러그 연속성 측정의 대체로 보지는 않는다.

근거: [SHOU HAN 제조사 도면](https://datasheet.lcsc.com/datasheet/pdf/50aca6c1750ca25d6422baa81dc852bf.pdf), 로컬 사본 `work/as004-independent-review-20261016/pj320d.pdf`와 렌더 `pj320d.png`.

## 3. [Minor / 문서] L1 전류 정격이 뒤바뀌어 기록돼 있다

`plan_pcb.py:216` 부근과 `REVIEW_NETLIST.md:40`은 DFE201612P-2R2M의 포화 관련 전류를 1.5A로 적는다. Murata 표는 **인덕턴스 30% 감소 기준 2.1A, 온도 상승 40°C 기준 1.5A**다. 표의 기준과 typ/max 구분을 유지해서 문서를 정정해야 한다.

이는 현재 부품이 부적합하다는 발견이 아니다. 정상 부하에서의 여유는 유지된다. 또한 실제 L1 랜드는 패드 0.55×1.60mm, 패드 사이 0.90mm, 전체 2.00mm로 제조사 권장 패턴과 일치한다. 기존 보고서의 “Murata 권장 랜드 미확인”은 이번에 해소했다.

근거: [Murata DFE201612P 원문](https://www.murata.com/~/media/webrenewal/products/inductor/chip/tokoproducts/wirewoundmetalalloychiptype/m_dfe201612p.ashx?la=en).

## 새로 실행한 검사

| 검사 | 결과 |
|---|---|
| KiCad 10.0.6 DRC, schematic parity 포함 | 위반 0, 미연결 0, 회로도 불일치 0 |
| KiCad ERC | 위반 0 |
| 무시된 7종 규칙을 모두 warning으로 활성화 | 30건, 아래에서 분류. 새 단락·단선 없음 |
| 배치 검사 | ERROR 0 / WARN 0, 사용 가능 면적 점유율 약 75% |
| 데이터시트 기대 핀 표 검사 | 138/138 |
| PCB 좌표·핀넷 readback | 설계 데이터와 일치 |
| 디커플링 패드 거리 | 19/19 |
| 라이브러리와 실제 패드 형상 | 54/54 |
| 윗면 SMD 패드에 닿는 보드 비아 | 0개. 의도한 EP 방열홀은 별도 |
| 제조 ZIP 구조·BOM/CPL 감사 | 17파일, 오류 0 / 경고 0 |
| Gerber 대 IPC-D-356 연결성 | 327/327 패드·비아 구리 존재, shorts 0 / opens 0 / undrilled 0 |
| Gerber 독립 간격 검사 | 다른 넷 사이 0.10mm 미만 0건, 4개 구리층 모두 |
| 현재 PCB 재수출 대 ZIP | 구리·마스크·페이스트·실크·외곽선 차이 0층, 드릴 111개 일치 |
| ZIP 대 작업 폴더 BOM/CPL | 바이트 단위 일치 |
| 제조 Gerber 렌더 | 앞뒤 실크-마스크 개구 겹침 0.000mm², 구리-가장자리 약 0.405mm |
| CPL 독립 변환 | 53개 실장 부품의 저장된 JLC 좌표·회전을 실제 PCB 패드에 대입. 기존 허용 범위와 일치 |
| ngspice 전원 경로 모델 재실행 | 기존 모델의 기동·규정 부하·홀드업 조건 PASS |
| 펌웨어 `lovelace-as-004` 재빌드 | SUCCESS, 2,305,707 / 3,145,728 bytes (73.3%) |
| 오디오·FIFO·소스 전환·capture 호스트 검사 | PASS |
| 실크 편집기 검사 | KiCad Python으로 9/9 PASS |

시스템 Python의 호스트 테스트에서는 KiCad가 필요한 6개 검사가 skip됐다. 이후 KiCad Python으로 9개 실크 테스트를 따로 실행해 모두 통과했다. 확장 DRC와 실크 검사 중 CLI가 macOS 앱 등록 단계에서 SIGABRT를 냈으나, 동일 검사를 샌드박스 밖에서 실행하면 완료됐다. 이를 PCB 불량으로 세지 않았다.

확장 DRC 30건의 내역:

- 15건: 배선 끝점이 비아 중심과 다름. 실제 중심선-비아 거리는 0.05–0.20mm이고 구리 연결이 유지된다. 제조 Gerber 연결성 검사도 통과했다.
- 3건: J1/J2/U1이 라이브러리와 다름. 보드 가장자리 실크 등 의도한 변경이 있고, 패드 형상은 동일하다.
- 1건: U1의 SMD 속성과 EP의 도금 방열홀 조합에 따른 부품 타입 경고.
- 11건: 바닥 테스트패드의 `TestPoint` 라이브러리가 프로젝트 테이블에 등록되지 않음. 패드는 PCB와 Gerber에 들어 있다.

따라서 “모든 규칙을 켜도 0”은 아니다. 기본 프로젝트 규칙에서 0이며, 숨겨진 경고를 별도로 검토했다.

## 직접 본 회로·배치·배선

- 4개 구리층, 앞뒤 제조 Gerber, 조립도, 3D 렌더를 확인했다. L2 GND/L3 디지털 전원은 연속적인 큰 평면이고 내부층 신호 배선은 없다. 3D에는 U1/J1/J2 모델이 빠져 있어 완전한 기구 검증으로 사용하지 않았다.
- 배치도에서 MCU가 왼쪽·상단, DAC/LDO가 오른쪽, 스위칭 전원이 아래쪽에 모인다. 매우 조밀하지만 검사상 courtyard 충돌은 없다. 안테나 영역은 상단 보드 밖으로 나간다.
- I2S는 GPIO21/19/18 → BCK/DIN/LRCK, XSMT GPIO22, LED GPIO23, 버튼 GPIO0으로 실제 펌웨어와 맞는다. GPIO16/17은 사용하지 않는다. I2S는 수 mm의 윗면 배선이다.
- WCH CH340N 원문에서 1 UD+, 2 UD−, 3 GND, 5 VCC, 6 TXD, 7 RXD, 8 V3 및 3.3V에서 VCC/V3 연결을 확인했다. UART 교차와 전원 연결은 맞는다. 내장 클럭 사용이며 DTR은 없어 수동 BOOT가 필요하다.
- ST USBLC6 원문에서 1/6 IO1, 3/4 IO2, 2 GND, 5 VBUS를 확인했다. HRO USB-C 원문과 CC/D+/D− 배정을 대조했다. 앞선 보고서에 남아 있던 이 부품들의 원문 확인 공백을 줄였다.
- 스위칭 전원의 C4는 VIN과 같은 면에 직접 연결돼 있으나 hot loop는 더 줄일 수 있다. 현재 배치를 “실측 없이 안정성 보장”으로 해석하지 않았다. TI는 VIN/PGND 입력 루프와 VOS/출력 C의 짧은 경로를 요구한다.
- USB D−는 비아가 여러 개이고 D+와 균일한 차동쌍이 아니다. 짧은 USB Full Speed 경로라 이를 동작 불가 판정으로 삼지 않았지만, 전송 오류·케이블 호환성은 첫 보드에서 확인해야 한다.

## 전원 계산과 아직 남은 실측

계산은 `pcbcalc.py`와 기존 ngspice 모델로 수행했다. 외층 1oz, 비아 도금 20µm 가정이며 실제 제조 적층·도금 조건을 확인해야 한다.

| 경로 | 계산과 약한 지점 | 판단 |
|---|---|---|
| VBUS → eFuse → +5V | ILIM 약 0.56–0.75A. 0.75A/10°C 상승의 외층 요구 폭 약 0.203mm, 배선 최소 0.25–0.30mm | 정상 부하에서 명백한 선폭 부족 없음. eFuse가 전류 한계 |
| Buck → +3V3_D → MCU | L3 평면으로 연결, 대표 전원 비아 Ø0.60/드릴0.30mm. 계산상 1개당 약 0.534A(10°C 상승, 0.7 감액) | 예상 약 0.37A 모델 부하에는 여유. 0.6A 이상 스트레스는 별도 계측 필요 |
| +5V → D5 → C25 → LDO/DAC | DAC 모델 31mA. VIN 5.7V, 주위55°C, θJA187.1°C/W 가정 시 LDO 74.4mW, Tj 약68.9°C | 명백한 LDO 발열 문제 없음. 이 값은 레이아웃을 포함한 실측 온도가 아님 |

ngspice 재실행에서 기존 모델의 전원 차단 여유는 5.87–10.48ms였다. 그러나 이 모델은 평균화한 버크, 이상화한 LDO/eFuse, 가정한 부하와 커패시턴스를 사용한다. 실제 제어 루프, 기생 성분, 전 부품 공차와 온도 모서리 조건, DAC 신호핀 전원 시퀀스까지 검증한 결과가 아니다. **“USB를 뽑아도 팝이 없다”는 보장은 하지 않는다.**

모델에서도 ILIM 최소값 0.556A에서 3.3V 부하를 0.7A로 올리면 5V 입력에서 전원이 무너지는 조건이 있다. 실제 보드가 그 부하를 요구한다는 뜻은 아니다. 데이터시트 기반 0.37A 모델은 통과했다. 첫 보드에서는 3V3의 순간 최저값과 리셋 원인을 함께 확인해야 한다.

제작·완성 판정에 남은 항목:

1. 1번 펌웨어 대기 수정 후 XSMT/BCK 타이밍 확인.
2. J2 랜드 차이 수용 여부 및 최종 JLC 배치 미리보기 확인. U2/U4/U5/U7/C25 방향을 특히 확인.
3. 조립 공정 레일은 좌우에 배치하고, 상단 안테나 약6.2mm·하단 AUX 돌출 때문에 패널 상하 간격도 확보. 현재 렌더에는 커넥터 3D가 빠져 있다.
4. TRS 플러그를 꽂고 Tip→L, Ring→R, Sleeve→GND 연속성 및 좌우 재생 확인.
5. 4.75/5.0/5.25V, 짧은 케이블/긴 케이블에서 cold boot·다운로드·OTA 및 동시 Wi-Fi/BT 부하 확인. 내부 RAM 여유는 빌드의 정적 RAM 비율로 보장할 수 없다.
6. 전원 투입·분리·재부팅·44.1/48kHz 전환의 팝, PC USB와 충전기에서의 잡음, 케이스 안 RSSI/끊김 확인.

이 항목이 끝나기 전에는 실제 AirPlay·Spotify·Bluetooth 재생, 음질, RF 성능, EMC/ESD 내성을 통과했다고 표현하지 않는다.

## 검수 대상과 증거 파일

- PCB SHA-256: `34edd4e9d45c3e7578a548e8b51e674ea8e9261ab2f0cd8cc0c521eceb67af9c`
- 제조 ZIP SHA-256: `022dbf24257904e7c45229e8b02280edff5600e331298c839451dc7562eea1df`
- 원본 6개 파일의 검수 전후 SHA-256 일치 확인.
- 로그·스냅샷·원문 도면·렌더·결과 JSON: `work/as004-independent-review-20261016/` (로컬 검수 폴더, Git 제외).
- 주요 결과: `verification-summary.json`, `drc.json`, `erc.json`, `drc-strict.json`, `gerber-diff.log`, `cpl-independent.json`, `mute-timing.json`, `simulation.log`, `firmware-build.log`, `host-tests.log`, `silkscreen-tests-unsandboxed.log`.

추가 원문: [ST USBLC6](https://www.st.com/resource/en/datasheet/usblc6-2.pdf), [WCH CH340](https://datasheet.lcsc.com/datasheet/pdf/a3b2ca2c7638da2635df3f5b1d90bcc0.pdf), [HRO TYPE-C-31-M-12](https://datasheet.lcsc.com/datasheet/pdf/9e56b777c022540fcce7c7f67825f55e.pdf), [TI TPS62162](https://www.ti.com/lit/ds/symlink/tps62162.pdf), [Espressif WROVER-E](https://documentation.espressif.com/esp32-wrover-e_esp32-wrover-ie_datasheet_en.html). CPL 비교에는 저장소의 JLCPCB/EasyEDA 캐시를 사용했으며 실시간 재고 및 발주 승인은 확인하지 않았다.
