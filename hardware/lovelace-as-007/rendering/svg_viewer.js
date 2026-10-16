'use strict';
const $ = id => document.getElementById(id);
const canvas = $('viewport');
const state = {azimuth: -65, elevation: 38, zoom: 1, projection:'orthographic',lens:50};
let draw = () => {}, exportSvg = '', exportName = '', pngResult = null;
const styleInputs = ['weight', 'ink', 'paper', 'clear', 'refs'].map($);
const rgb = hex => [1, 3, 5].map(i => parseInt(hex.slice(i, i + 2), 16) / 255);

function download(text, filename) {
  const url = URL.createObjectURL(new Blob([text], {type: 'image/svg+xml'}));
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function applyStyle() {
  $('weight-value').textContent = $('weight').value + ' mm';
  for (const svg of $('top').querySelectorAll('svg')) {
  const group = svg.querySelector('#visible-edges');
  group.setAttribute('stroke-width', $('weight').value);
  group.setAttribute('stroke', $('ink').value);
  const refs = svg.querySelector('#references');
  if (refs) {refs.setAttribute('fill', $('ink').value);
  refs.style.display = $('refs').checked ? '' : 'none';}
  for (const path of svg.querySelectorAll('#back-silkscreen path')) {
    for (const attr of ['fill','stroke']) if(path.getAttribute(attr)!=='none')path.setAttribute(attr,$('ink').value);
  }
  svg.querySelector('#background').setAttribute('fill', $('clear').checked ? 'none' : $('paper').value);
  }
  $('top').classList.toggle('checker', $('clear').checked);
  $('live-stage').classList.toggle('checker', $('clear').checked);
  draw();
}
styleInputs.forEach(input => input.addEventListener('input', applyStyle));
$('download-top').onclick = () => {
  const svg = $('top').querySelectorAll('svg')[$('drawing-side').value === 'front' ? 0 : 1].cloneNode(true);
  svg.removeAttribute('style');
  download(new XMLSerializer().serializeToString(svg), `${CONFIG.boardName}-${$('drawing-side').value}.svg`);
};
$('drawing-side').onchange = () => {
  const back = $('drawing-side').value === 'back';
  $('top').querySelectorAll('svg').forEach((svg,i) => svg.style.display = i === (back ? 1 : 0) ? '' : 'none');
  $('drawing-title').textContent = back ? '01 / BACK — 뒷면 실크스크린' : '01 / ASSEMBLY — 정면 부품 배치도';
  state.zoom = 1; setView(back ? 90 : -65, back ? -90 : 38);
};

function setView(az, el) {
  if (!Number.isFinite(az) || !Number.isFinite(el)) return;
  state.azimuth = ((az + 180) % 360 + 360) % 360 - 180;
  state.elevation = Math.max(-90, Math.min(90, el));
  $('azimuth').value = Math.round(state.azimuth * 10) / 10;
  $('elevation').value = Math.round(state.elevation * 10) / 10;
  draw();
}
for (const id of ['azimuth', 'elevation']) $(id).addEventListener('change', () => setView(Number($('azimuth').value), Number($('elevation').value)));
document.querySelectorAll('[data-preset]').forEach(button => button.onclick = () => {
  state.zoom = 1;
  setView(...button.dataset.preset.split(',').map(Number));
});
$('fit').onclick = () => {state.zoom = 1; draw();};
$('lens').disabled = true;
for(const id of ['projection','lens','shading'])$(id).addEventListener('input',()=>{
  state.projection=$('projection').value;state.lens=Number($('lens').value);
  $('lens').disabled=state.projection!=='perspective';$('lens-value').textContent=state.lens+' mm';draw();
});
canvas.ondblclick = () => {state.zoom = 1; setView(-65, 38);};
let drag = null;
canvas.addEventListener('pointerdown', event => {
  if (drag || event.button !== 0) return;
  drag = {id: event.pointerId, x: event.clientX, y: event.clientY};
  canvas.setPointerCapture(event.pointerId);
  canvas.focus({preventScroll: true});
});
canvas.addEventListener('pointermove', event => {
  if (!drag || drag.id !== event.pointerId) return;
  if (event.buttons === 0) {drag = null; return;}
  setView(state.azimuth - (event.clientX - drag.x) * .45,
          state.elevation + (event.clientY - drag.y) * .35);
  drag.x = event.clientX; drag.y = event.clientY;
});
for (const type of ['pointerup', 'pointercancel', 'lostpointercapture']) canvas.addEventListener(type, () => {drag = null;});
canvas.addEventListener('wheel', event => {
  event.preventDefault();
  state.zoom = Math.max(.5, Math.min(4, state.zoom * Math.exp(-event.deltaY * .0015)));
  draw();
}, {passive: false});
canvas.addEventListener('keydown', event => {
  const keys = {ArrowLeft: [-5, 0], ArrowRight: [5, 0], ArrowUp: [0, 5], ArrowDown: [0, -5]};
  if (keys[event.key]) {
    event.preventDefault();
    const [a, e] = keys[event.key]; setView(state.azimuth + a, state.elevation + e);
  } else if (['+', '=', '-'].includes(event.key)) {
    event.preventDefault();
    state.zoom = Math.max(.5, Math.min(4, state.zoom * (event.key === '-' ? .9 : 1.1)));
    draw();
  }
});

$('export').onclick = async () => {
  const button = $('export');
  const chosen = {...state, style:$('shading').value, aspect:canvas.clientWidth/canvas.clientHeight,stroke: Number($('weight').value), ink: $('ink').value, opacity: Number($('opacity').value),
    background: $('clear').checked ? 'transparent' : $('paper').value};
  button.disabled = true;
  $('status').classList.remove('error');
  $('status').textContent = 'STEP 원본의 숨은선을 제거하는 중…';
  try {
    const response = await fetch('/api/project', {method: 'POST',
      headers: {'Content-Type': 'application/json', 'X-PCB-Viewer': CONFIG.token}, body: JSON.stringify(chosen)});
    const text = await response.text();
    if (!response.ok) throw new Error(text);
    const parsed = new DOMParser().parseFromString(text, 'image/svg+xml');
    if (parsed.querySelector('parsererror') || parsed.documentElement.localName !== 'svg') throw new Error('잘못된 SVG 응답입니다.');
    exportSvg = text; pngResult=null;
    const cameraLabel = chosen.projection==='perspective'?`원근 ${chosen.lens} mm`:'평행 투영';
    exportName = `${CONFIG.boardName}-${chosen.projection}-${chosen.lens}mm-${chosen.azimuth.toFixed(1)}-${chosen.elevation.toFixed(1)}.svg`;
    $('result').replaceChildren(document.importNode(parsed.documentElement, true));
    $('result-title').textContent = `정밀 SVG · ${cameraLabel} · ${chosen.azimuth.toFixed(1)}° / ${chosen.elevation.toFixed(1)}°`;
    $('status').textContent = '정밀 SVG 준비 완료';
    $('result-dialog').showModal();
  } catch (error) {
    $('status').textContent = error.message;
    $('status').classList.add('error');
  } finally {button.disabled = false;}
};
$('download-3d').onclick = () => {if(pngResult){const url=URL.createObjectURL(pngResult.blob),link=document.createElement('a');link.href=url;link.download=pngResult.name;document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);}else download(exportSvg,exportName);};
$('close-result').onclick = () => $('result-dialog').close();

const descriptions={
  line:'면 색·조명·그림자 없이 보이는 윤곽만 표시합니다. 면은 가림 판정에만 사용합니다.',
  detail:'가려진 선은 제거하고, STEP의 작은 모서리와 접합선까지 표시합니다.',
  wire:'면을 그리지 않고 가려진 모서리까지 모두 표시합니다.',
  xray:'검은 배경의 반투명 면과 전체 모서리. 첨부 예시처럼 내부를 투시합니다.',
  studio:'단색 표면에 키·필 조명과 부품 사이의 실제 그림자를 적용합니다.',
  original:'STEP 파일에 저장된 면별 RGB를 조명 없이 표시합니다. PCB 색은 별도 설정입니다.',
  material:'STEP 색상에 GGX 금속 반사·소프트박스 환경·그림자를 적용합니다. 반사값은 조정 가능합니다.',
  normal:'표면 법선 방향을 색상으로 표시합니다.'
};
let lastStyle='line';
$('shading').addEventListener('change',()=>{
  const mode=$('shading').value;
  if(mode==='xray'){$('paper').value='#101114';$('ink').value='#dbe5f5';}
  else if(lastStyle==='xray'){$('paper').value='#ffffff';$('ink').value='#464a46';}
  $('style-description').textContent=descriptions[mode];lastStyle=mode;applyStyle();
});
$('expand-view').onclick=()=>{$('workspace').classList.toggle('expanded');$('expand-view').textContent=$('workspace').classList.contains('expanded')?'도면 함께 보기':'3D 크게 보기';};
function renderSettings(){
  return {...state,style:$('shading').value,stroke:Number($('weight').value),ink:rgb($('ink').value),paper:rgb($('paper').value),transparent:$('clear').checked,
    boardColor:rgb($('board-color').value),roughness:Number($('roughness').value),metalness:Number($('metalness').value),
    intensity:Number($('light-intensity').value),exposure:Number($('exposure').value),environment:Number($('environment').value),
    lightAz:Number($('light-azimuth').value),lightEl:Number($('light-elevation').value),opacity:Number($('opacity').value),
    softness:Number($('softness').value),shadows:$('shadows').checked,edges:$('overlay-edges').checked};
}
for(const id of ['board-color','roughness','metalness','light-intensity','exposure','environment','light-azimuth','light-elevation','opacity','softness','shadows','overlay-edges'])$(id).addEventListener('input',()=>draw());
$('preset-product').onclick=()=>{$('shading').value='material';$('projection').value='perspective';state.projection='perspective';$('lens').disabled=false;state.lens=70;$('lens').value='70';$('lens-value').textContent='70 mm';$('board-color').value='#242725';$('paper').value='#ffffff';$('roughness').value='.26';$('metalness').value='.9';$('overlay-edges').checked=false;$('shadows').checked=true;setView(-85,18);$('shading').dispatchEvent(new Event('change'));};
$('preset-xray').onclick=()=>{$('shading').value='xray';$('shading').dispatchEvent(new Event('change'));};
$('download-png').onclick=()=>{
  const scale=Number($('png-scale').value);draw(scale);
  const width=canvas.width,height=canvas.height,style=$('shading').value;
  canvas.toBlob(blob=>{
    if(!blob){$('status').textContent='PNG 생성에 실패했습니다.';draw();return;}
    pngResult={blob,name:`${CONFIG.boardName}-${style}-${width}x${height}.png`};
    const image=document.createElement('img'),url=URL.createObjectURL(blob);image.src=url;image.alt=`${style} 렌더 ${width} × ${height}`;image.onload=()=>URL.revokeObjectURL(url);
    $('result').replaceChildren(image);$('result-title').textContent=`PNG · ${width} × ${height} · ${style}`;$('result-dialog').showModal();draw();
  },'image/png');
};
async function initialize(){
  const response=await fetch('/mesh.json');if(!response.ok)throw new Error('3D 모델을 불러오지 못했습니다.');
  const mesh=await response.json();const engine=createPcbRenderer(canvas,mesh);
  draw=scale=>engine.render(renderSettings(),typeof scale==='number'?scale:null);
  new ResizeObserver(()=>draw()).observe(canvas);
  const stats=Object.values(mesh.color_sources);const colored=stats.reduce((n,s)=>n+s.colored_faces,0),total=stats.reduce((n,s)=>n+s.faces,0);
  $('color-status').textContent=`STEP ${stats.length}개 파일 · 원본 색상 ${colored.toLocaleString()}/${total.toLocaleString()}면 · ${Math.round(mesh.triangles.length/9).toLocaleString()} triangles`;
  $('style-description').textContent=descriptions[$('shading').value];applyStyle();$('export').disabled=false;$('download-png').disabled=false;$('status').textContent='시점을 골라 SVG 또는 PNG로 내보내세요';
  canvas.addEventListener('webglcontextlost',event=>{event.preventDefault();$('status').textContent='GPU 연결이 중단됐습니다. 새로고침하세요.';$('status').classList.add('error');});
}
applyStyle();initialize().catch(error=>{$('status').textContent=error.message;$('status').classList.add('error');});
