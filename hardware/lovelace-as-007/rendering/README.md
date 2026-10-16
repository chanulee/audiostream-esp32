# PCB 렌더링 도구

렌더링 코드, 브라우저 UI, 모델 캐시, Python 환경, 검증 코드를 이 폴더에서 관리합니다.
PCB와 부품 원본은 상위 디렉터리, 생성 결과는 `../renders/`에 둡니다.

## 실행

같은 구조의 AS-007, AS-008 폴더 안으로 `rendering/`을 복사하거나 옮겨도 코드 수정 없이 실행됩니다.
상위 폴더의 `placement.json` → `board.name`에 해당하는 `.kicad_pcb`를 자동 선택합니다.
`placement.json`이 없으면 상위 폴더에 PCB가 정확히 한 개 있어야 합니다.
설정이 가리키는 PCB가 없거나 후보가 여러 개이면 오류를 표시합니다.
화면 이름·다운로드 이름은 선택한 PCB 파일명, 출력은 해당 PCB 폴더의 `renders/svg/`를 따릅니다.
커스텀 STEP은 보드 폴더의 `lib/3d/`와 `${KIPRJMOD}` 참조를 함께 유지하세요.

가장 간단한 실행(Python 3.10–3.13 필요):

```sh
bash rendering/run.sh
```

보드 폴더에서 실행하는 명령입니다. 다른 위치에서는 `run.sh`의 경로를 지정하면 됩니다.
필요하면 Python 환경·의존성과 누락된 공식 모델을 최초 실행에 설치합니다(인터넷 필요).
`.venv/`는 복사할 필요가 없으며, `.models/`를 함께 가져가면 공식 모델을 다시 받지 않습니다.
모델과 실행 환경이 준비된 이후에는 오프라인으로 동작합니다.
두 보드를 동시에 열려면 `bash rendering/run.sh --port 8878`처럼 포트를 구분합니다.

다른 PCB를 명시적으로 선택할 수도 있습니다:

```sh
bash rendering/run.sh /path/to/board.kicad_pcb
rendering/.venv/bin/python rendering/render_svg.py /path/to/board.kicad_pcb
```

아래는 실행 환경을 수동으로 준비하는 방법입니다.

이 폴더에서 최초 설치합니다(Python 3.10–3.13).

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-svg.txt
.venv/bin/python svg_viewer.py --fetch-models
```

이후 `.venv/bin/python svg_viewer.py`를 실행하고 [로컬 뷰어](http://127.0.0.1:8877)를 엽니다.
`--port 8880`으로 포트를 변경할 수 있습니다. 모델을 한 번 받으면 오프라인으로 동작합니다.
공식 KiCad 10.0.0 STEP 파일은 `.models/10.0.0/`에 보관합니다.
이미 설치했다면 `KICAD10_3DMODEL_DIR`도 사용할 수 있습니다.
PCB·실크를 수정해서 저장한 뒤에는 뷰어를 재시작하면 갱신됩니다.

- 드래그·방향키: 회전. 휠·+/−: 확대. 더블클릭: 초기화.
- `도면 면`: 앞면 부품 배치도 또는 뒷면 실크·테스트 패드 도면.
- 위·앞·아래 프리셋 또는 방위각·고도 직접 입력.
- 평행/원근 카메라 전환, 18–120 mm 렌즈(36×24 mm 센서 기준).
  렌즈 변경 시 보드의 기본 구도를 유지하도록 카메라 거리를 함께 조절합니다.
- 선화·스튜디오·법선 셰이딩 전환. 셰이딩은 미리보기용이며 SVG는 벡터 선화입니다.
- `3D 크게 보기`로 렌더 작업 영역을 확대합니다. PNG는 현재 스타일·카메라로 1×/2×/4× 저장하며,
  투명 배경도 유지합니다. GPU의 최대 이미지 크기 이내에서 출력합니다.
  `PNG 만들기`에서 해상도와 결과를 확인한 뒤 `결과 다운로드`로 저장합니다.
- 선 색·굵기·배경을 조정하고 `이 각도로 정밀 SVG 만들기` → 결과 확인 → 다운로드.
- SVG에는 전체 보드가 담깁니다. 화면 확대는 확인용입니다.
- 뒷면은 외부에서 읽는 방향으로 미러 처리합니다. PCB의 B.SilkS 도형과 기본 KiCad
  newstroke 글꼴을 사용하며, 글자도 SVG path로 출력합니다.
  풋프린트의 기본 Keep Upright 규칙도 KiCad와 동일하게 적용합니다.
  원근 SVG는 같은 카메라 중심·초점거리로 투영하며 뒷면 실크에도 원근을 적용합니다.

### 렌더 스타일

| 모드 | 표시 |
|---|---|
| 순수 선화 | 면은 depth buffer에만 기록. 색·밝기 변화·그림자 없이 보이는 날카로운 모서리 |
| 상세 선화 | 가려진 선 제거, 작은 접합선과 곡면 경계까지 표시 |
| 전체 모서리 | 면을 그리지 않고 뒤쪽과 내부 STEP 모서리까지 표시 |
| X-ray | 검은 배경, 반투명 면의 누적과 모든 모서리. 예시 1 프리셋 |
| 조명·클레이 | 단색 재질 + 키·필 조명 + 실제 부품 그림자 |
| STEP 원본 색상 | XCAF로 복원한 면별 선형 RGB를 sRGB로 표시. 조명·톤 매핑 없음 |
| 재질·금속 반사 | STEP 색상 + GGX BRDF + 절차적 소프트박스 반사 + PCF 그림자. 예시 2 프리셋 |
| 법선 검사 | 곡면의 보간된 법선 표시 |

원본 색상은 STEP의 면 → solid → 루트 색상 상속을 읽습니다. 색이 없는 면은 중성 회색으로
표시하며 화면에 원본 색상 복원 면 수를 표시합니다. PCB 몸체는 STEP에 없으므로 별도 PCB 색을 씁니다.
현재 17개 STEP의 3,461면 모두 색상을 복원했으며 `../renders/svg/color-sources.json`에
파일별 결과가 있습니다. 색상 메시를 `.cache/`에 압축 저장하고 보드·모델·생성 코드가 바뀌면 재생성합니다.
예시 2 프리셋은 검은 PCB·낮은 시점·원근 렌즈로 변경하며, 부품의 원본 색상은 유지합니다.
`STEP 원본 색상`에서 PCB를 원래 녹색으로 보고 싶으면 PCB 색을 `#145f35`로 지정합니다.

거칠기·금속성은 원본 STEP에 광학 속성이 없어 색상 분류로 추정하고 슬라이더로 조정합니다.
사진의 촬영 재질과 동일함을 보증하는 측정 재질이나 레이 트레이싱은 아닙니다.
조명 방향·높이·세기, 환경 반사, 노출, 그림자 부드러움, 모서리 겹쳐 그리기 등을 조절할 수 있습니다.
현재 그림자는 부품/PCB 사이의 directional shadow map이며, 바닥 평면·HDRI 텍스처는 사용하지 않습니다.
X-ray는 구조 설명용 시각화이며 물리적 유리 굴절 모델은 아닙니다.

SVG는 기술 선화용입니다. 전체 모서리·X-ray 모드에서는 숨은 STEP 모서리도 내보냅니다.
색·재질·조명 스타일의 결과는 PNG로 저장하며, SVG 안에 PNG를 숨겨 넣지 않습니다.

서버 없이 사용할 SVG와 정적 미리보기 생성:

```sh
.venv/bin/python render_svg.py
.venv/bin/python render_svg.py --azimuth 60 --elevation -40 --background '#eeffb3'
open ../renders/svg/index.html
```

`../renders/svg/`의 `top.svg`, `bottom.svg`, `iso.svg`와 `index.html`을 갱신합니다.
`--out DIR`로 출력 경로를 바꿀 수 있습니다.

## 파일

| 파일 | 역할 |
|---|---|
| `svg_viewer.py`, `.html`, `.js` | 로컬 WebGL 3D 뷰어 + STEP 숨은선 제거 SVG API |
| `render_engine.js` | depth 전용 선화·X-ray·조명·GGX 재질·그림자·PNG 출력 |
| `step_colors.py` | STEP/XCAF 색상·상속 복원과 부품별 색상 메시 |
| `render_svg.py` | 모델 배치, STEP 투영, 앞면 부품 도면, SVG 출력 |
| `silk_geometry.py` | PCB 뒷면 실크 도형·벡터 텍스트·3D 투영 |
| `newstroke_ascii.json`, `NEWSTROKE-LICENSE.txt` | KiCad 10 ASCII 글꼴 데이터와 원본 라이선스 |
| `audit_models.py` | 전체 STEP 형상·보드 교차 검사, `../renders/svg/model-audit.json` 출력 |
| `test_render_svg.py` | 기하·좌표·실크·API 입력 검증 |
| `render_board.py` | 기존 KiCad PNG/PDF·층별 렌더·버전 비교 |
| `render_extra.sh` | 기존 KiCad 3D 다각도 PNG와 층별 SVG/PDF |
| `render_placement.py` | 배치 JSON의 PNG 출력 |

`render_board.py`와 `render_extra.sh`는 KiCad 10 런타임이 필요합니다.
`../make_board.sh`는 새 경로의 `render_board.py`를 호출합니다.

## 3D 정렬 확인 — 2026-10-16

USB-C의 EasyEDA STEP는 접촉면이 이미 Z=0입니다. PCB에 저장된 추가 Z=-0.85 mm는
단자와 셸을 기판 안에 넣고 있었습니다. 모델 원본을 변형하지 않고 `build_pcb.py`와
PCB의 J1 3D offset을 **(0, -1.05, 0) mm**로 수정했습니다.

| 확인한 모델 특징 | 정렬 근거 |
|---|---|
| J1 위치 결정핀 | 원본 STEP의 (±2.89, -3.65) mm → 풋프린트 NPTH (±2.89, -2.60) mm |
| J1 셸 고정핀 | STEP 뒤쪽 Y≈-4.175 mm → 풋프린트 슬롯 Y=-3.13 mm (약 0.005 mm 차이) |
| J1 접촉면 | 원본 Z=0 → PCB 윗면 Z=1.60 mm |
| J1 개구부 | 원본 Y=2.60 mm → PCB Y=41.00 mm, 보드 끝과 일치 |
| J2 위치 결정핀 | 모델 중심이 NPTH에서 0.01 mm 어긋난 값을 보정 |
| J2 단자면 | 기판 안에 0.04 mm 들어간 모델을 올려 PCB 윗면과 일치 |

J2의 3D offset은 PCB와 원본 풋프린트 모두 **(-6.975, 0, 2.55) mm**로 수정했습니다.
패드·홀·부품의 PCB 배치와 구리 배선은 변경하지 않았습니다.
`../renders/svg/pcb-model-check.json`에 모델 항목을 제외한 PCB 전체가 Git HEAD와 동일하다는
비교 결과와 기존 JLC 위치 결정핀 오차 0.000 mm를 기록했습니다.

테스트 패드 라벨의 저장 각도 180°는 KiCad의 Keep Upright 기본 규칙으로 실제로는
0°로 그려집니다. 뷰어가 이 규칙을 빠뜨린 것을 수정했으며, VBUS의 첫 글자 좌표가
KiCad 네이티브 SVG와 일치하는 회귀 검사를 추가했습니다. PCB 실크 데이터는 변경하지 않았습니다.

형상과 실장면을 검증한 공급자 모델이며, 제조사 공차까지 보증하는 기구 설계 모델은 아닙니다.
J1 모델 셸 높이 약 3.25 mm와 [제조사 현재 제품 페이지](https://en.krhro.com/Product-Details/726.html)의
3.16 mm 표기는 차이가 있어, 외함 간섭 검토에는 제조사 도면과 실물을 기준으로 해야 합니다.
STEP의 회로도 로고 등 공급자 표식도 그대로 유지합니다.

## 검증

```sh
.venv/bin/python -m unittest test_render_svg -v
.venv/bin/python audit_models.py
node --check svg_viewer.js
```

KiCad 네이티브 SVG의 실크 좌표와 비교하는 회귀 검사, J1 고정핀·접촉면·개구부 정렬 검사,
숨은선 제거 검사, API 입력 검사 등을 포함합니다.
모델 감사는 실제 드릴 홀을 뺀 보드와 STEP의 교차 체적도 검사합니다.
기존 KiCad PNG/PDF 파이프라인 전체는 이번 변경에서 재실행하지 않았습니다.

현재 범위: AS-006 직사각형 보드와 앞면 실장. U6는 STEP 모델이 없어 2D 도면에만 표시됩니다.
입체도의 구리 배선과 앞면 실크는 생략합니다. 뒷면 글꼴은 일반 ASCII 기본 글꼴만 지원하며,
다른 글꼴·문자는 오류로 알립니다. STEP 곡선의 SVG 근사 허용치는 0.008 mm입니다.
