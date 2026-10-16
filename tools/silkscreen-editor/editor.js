/* SVG is rendered locally as a monochrome stencil, at 0.025 mm resolution. */
'use strict';
const $ = id => document.getElementById(id);
const token = location.hash.slice(1);
const NS = 'http://www.w3.org/2000/svg';
let state, selected = null, background = null, drag = null, dirty = false, busy = false;
let inspection=null, inspectionURL=null;

async function api(path, data) {
  const response = await fetch(path, {method: data ? 'POST' : 'GET', headers: {'X-Silk-Token': token, ...(data ? {'Content-Type':'application/json'} : {})}, ...(data ? {body:JSON.stringify(data)} : {})});
  if (!response.ok) throw new Error((await response.json()).error);
  return response;
}
function status(message, error=false) { $('status').textContent=message; $('status').classList.toggle('error',error); }
function clearInspection() {
  inspection=null;
  if(inspectionURL)URL.revokeObjectURL(inspectionURL);inspectionURL=null;
  $('resume').hidden=true;$('check-results').textContent='';
}
function markDirty() {clearInspection();dirty=true; $('dirty').textContent='저장하지 않은 변경';}
function current() {return state.layout.items.find(i=>i.id===selected);}
function itemLabel(item) {return item.kind==='text' ? item.text.trim().replace(/\n/g,' / ')||'(빈 텍스트)' : item.name||'SVG';}
function svgNode(tag, attrs, text) {
  const element=document.createElementNS(NS,tag);
  for(const [key,value] of Object.entries(attrs)) element.setAttribute(key,value);
  if(text!==undefined) element.textContent=text;
  return element;
}
function draw() {
  if(!state) return;
  const board=$('board'), side=$('side').value;
  board.setAttribute('viewBox',`0 0 ${state.width} ${state.height}`);
  board.setAttribute('width',state.width); board.setAttribute('height',state.height);
  board.replaceChildren(svgNode('rect',{width:state.width,height:state.height,fill:'#195039'}));
  const checked=inspection?.side===side[0];
  if(background) {
    const image=svgNode('image',{href:background,width:state.width,height:state.height,opacity:checked ? .45 : 1});
    if(side==='B.SilkS') image.setAttribute('transform',`translate(${state.width},0) scale(-1,1)`);
    board.append(image);
  }
  if(checked) {
    const image=svgNode('image',{href:inspectionURL,width:state.width,height:state.height});
    if(side==='B.SilkS')image.setAttribute('transform',`translate(${state.width},0) scale(-1,1)`);
    board.append(image);
    const boxes=new Map();
    inspection.issues.forEach((issue,index)=>issue.boxes.forEach(box=>{
      const key=box.join(',');
      if(!boxes.has(key))boxes.set(key,{box,numbers:new Set()});
      boxes.get(key).numbers.add(index+1);
    }));
    for(const {box:[x,y,w,h],numbers} of boxes.values()) {
      const left=side==='B.SilkS'?state.width-x-w:x;
      board.append(svgNode('rect',{x:left,y,width:w,height:h,class:'drc-box'}));
      board.append(svgNode('text',{x:left,y:y-.3,fill:'#ff6257','font-size':.8},[...numbers].join(',')));
    }
  }
  for(const item of state.layout.items.filter(i=>!checked&&i.side===side)) {
    const g=svgNode('g',{'data-id':item.id,class:'art',transform:`translate(${item.x} ${item.y}) rotate(${item.rotation})`});
    if(item.kind==='text') {
      const text=svgNode('text',{'text-anchor':'middle','dominant-baseline':'central','font-family':'sans-serif','font-size':item.size,fill:'#fff',stroke:'#fff','stroke-width':Math.max(0,item.thickness-.12)});
      const lines=item.text.split('\n');
      lines.forEach((line,i)=>text.append(svgNode('tspan',{x:0,y:(i-(lines.length-1)/2)*item.size*1.5,'xml:space':'preserve'},line)));
      g.append(text);
    } else {
      const d=item.rectangles.map(([x,y,w,h])=>`M${(x-.5)*item.width},${(y-.5)*item.height}h${w*item.width}v${h*item.height}h${-w*item.width}z`).join('');
      g.append(svgNode('path',{d,fill:'#fff'}));
      g.append(svgNode('rect',{x:-item.width/2,y:-item.height/2,width:item.width,height:item.height,fill:'transparent'}));
    }
    board.append(g);
    if(item.id===selected) {
      const bounds=g.getBBox();
      g.append(svgNode('rect',{class:'selection',x:bounds.x-.3,y:bounds.y-.3,width:bounds.width+.6,height:bounds.height+.6}));
    }
  }
  board.append(svgNode('rect',{x:0,y:0,width:state.width,height:state.height,fill:'none',stroke:'#f3c96a','stroke-width':.1,'stroke-dasharray':'.5 .3','pointer-events':'none'}));
}
function refresh() {
  if(!state)return;
  const items=$('items'); items.replaceChildren();
  for(const item of state.layout.items.filter(i=>i.side===$('side').value)) {
    const option=document.createElement('option'); option.value=item.id;
    option.textContent=itemLabel(item); items.append(option);
  }
  if(![...items.options].some(o=>o.value===selected)) selected=items.options[0]?.value||null;
  items.value=selected||'';
  const item=current(); $('properties').disabled=!item;
  $('text-label').hidden=item?.kind!=='text'; $('text-fields').hidden=item?.kind!=='text'; $('svg-fields').hidden=item?.kind!=='svg';
  if(item) for(const field of ['text','x','y','rotation','size','thickness','width','height']) {
    const value=item[field];$(field).value=typeof value==='number'?Number(value.toFixed(4)):value??'';
  }
  $('ignore-white').checked=item?.ignoreWhite||false;
  draw();
}
async function loadBackground() {
  const side=$('side').value;
  const copper=$('show-copper').checked;
  const response=await api(`/api/background/${side[0]}${copper?'/copper':''}`);
  const url=URL.createObjectURL(await response.blob());
  if(side!==$('side').value||copper!==$('show-copper').checked){URL.revokeObjectURL(url);return;}
  if(background)URL.revokeObjectURL(background); background=url; draw();
}
// Merge runs vertically: preserves cutouts without requiring polygon hole support.
function maskRectangles(pixels,width,height,ignoreWhite) {
  let active=new Map(); const output=[];
  function ink(x,y) {const i=(y*width+x)*4; return pixels[i+3]>=128&&(!ignoreWhite||Math.min(pixels[i],pixels[i+1],pixels[i+2])<245);}
  for(let y=0;y<height;y++) {
    const next=new Map();
    for(let x=0;x<width;) {
      if(!ink(x,y)){x++;continue;}
      const start=x;while(x<width&&ink(x,y))x++;
      const key=`${start}:${x}`, rect=active.get(key)||[start,y,x-start,0]; rect[3]++;
      next.set(key,rect); active.delete(key);
    }
    output.push(...active.values()); active=next;
  }
  output.push(...active.values());
  return output.map(([x,y,w,h])=>[x/width,y/height,w/width,h/height]);
}
function cleanSVG(source) {
  if(new TextEncoder().encode(source).length>512000)throw new Error('SVG는 500 KB 이하만 지원합니다.');
  const doc=new DOMParser().parseFromString(source,'image/svg+xml');
  if(doc.querySelector('parsererror')||doc.documentElement.localName!=='svg')throw new Error('올바른 SVG 파일이 아닙니다.');
  if(doc.doctype)throw new Error('DOCTYPE을 제거한 일반 SVG로 저장하세요.');
  for(const element of doc.querySelectorAll('*')) {
    if(['script','foreignObject','animate','animateMotion','animateTransform','set','image'].includes(element.localName))throw new Error('외부 이미지·스크립트·애니메이션 없이 SVG 경로로 내보내세요.');
    if(element.localName==='style'&&(/@import/i.test(element.textContent)||[...element.textContent.matchAll(/url\((.*?)\)/gi)].some(m=>!/^\s*['"]?#[\w.-]+['"]?\s*$/.test(m[1]))))throw new Error('외부 스타일 참조는 지원하지 않습니다.');
    for(const attr of element.attributes) {
      if(/^on/i.test(attr.name)||(/href$/i.test(attr.name)&&!attr.value.startsWith('#'))||(/url\s*\(/i.test(attr.value)&&!/url\(\s*['"]?#[\w.-]+['"]?\s*\)/i.test(attr.value)))throw new Error('외부 참조나 실행 코드가 있는 SVG는 지원하지 않습니다.');
    }
  }
  const svg=doc.documentElement, box=svg.getAttribute('viewBox')?.trim().split(/[\s,]+/).map(Number);
  let width=box?.[2]||parseFloat(svg.getAttribute('width'))||100;
  let height=box?.[3]||parseFloat(svg.getAttribute('height'))||100;
  if(!Number.isFinite(width)||!Number.isFinite(height)||width<=0||height<=0)throw new Error('SVG 크기가 잘못됐습니다.');
  svg.setAttribute('width',width);svg.setAttribute('height',height);
  return {source:new XMLSerializer().serializeToString(svg),ratio:height/width};
}
async function rasterize(item) {
  const cleaned=cleanSVG(item.svg), width=Math.max(1,Math.ceil(item.width*40)), height=Math.max(1,Math.ceil(item.height*40));
  if(width*height>4_000_000)throw new Error('SVG 크기가 너무 큽니다.');
  const url=URL.createObjectURL(new Blob([cleaned.source],{type:'image/svg+xml'}));
  try {
    const image=new Image(); image.src=url; await image.decode();
    const canvas=document.createElement('canvas');canvas.width=width;canvas.height=height;
    const ctx=canvas.getContext('2d',{willReadFrequently:true});ctx.drawImage(image,0,0,width,height);
    const rectangles=maskRectangles(ctx.getImageData(0,0,width,height).data,width,height,item.ignoreWhite);
    if(!rectangles.length)throw new Error('인쇄할 도형이 없습니다. 흰 로고라면 “흰 배경 제외”를 해제하세요.');
    if(rectangles.length>40000)throw new Error('SVG가 너무 복잡합니다. 도형을 단순화하세요.');
    return rectangles;
  } finally {URL.revokeObjectURL(url);}
}
function error(exc) {status(exc.message||String(exc),true);}
async function withBusy(action) {
  if(busy||!state)return;busy=true;$('save').disabled=true;$('check').disabled=true;$('side').disabled=true;$('upload').disabled=true;$('properties').disabled=true;
  try{await action();}catch(exc){error(exc);}finally{busy=false;$('save').disabled=!state;$('check').disabled=false;$('side').disabled=false;$('upload').disabled=false;refresh();}
}
$('side').addEventListener('change',()=>{clearInspection();background=null;refresh();loadBackground().catch(error);});
$('show-copper').addEventListener('change',()=>{background=null;draw();loadBackground().catch(error);});
$('resume').addEventListener('click',()=>{clearInspection();draw();status('편집 모드입니다. 변경 후 다시 검사하세요.');});
$('check').addEventListener('click',()=>withBusy(async()=>{
  status('KiCad 실제 글꼴로 검사 중… 원본 PCB는 변경하지 않습니다.');
  const response=await api('/api/check',{revision:state.revision,layout:state.layout,side:$('side').value[0]});
  clearInspection();inspection=await response.json();
  inspectionURL=URL.createObjectURL(new Blob([inspection.svg],{type:'image/svg+xml'}));
  $('resume').hidden=false;
  const result=$('check-results');
  result.textContent=`실제 KiCad 인쇄 형상 · 현재 면 실크 검사 ${inspection.issues.length}건. 빨간 상자와 번호로 표시합니다.`;
  const list=document.createElement('ol');
  for(const issue of inspection.issues){const li=document.createElement('li');li.textContent=issue.label;list.append(li);}
  result.append(list);status('검사 완료. 위치·문구를 수정하거나 “편집 계속”으로 돌아가세요.');
}));
$('items').addEventListener('change',()=>{selected=$('items').value;refresh();});
$('add-text').addEventListener('click',()=>{
  if(!state||busy)return;
  const item={id:crypto.randomUUID(),kind:'text',side:$('side').value,text:'새 텍스트',x:state.width/2,y:state.height/2,size:1,thickness:.15,rotation:0};
  state.layout.items.push(item);selected=item.id;markDirty();refresh();
});
$('delete').addEventListener('click',()=>{if(!current()||busy)return;state.layout.items=state.layout.items.filter(i=>i.id!==selected);selected=null;markDirty();refresh();});
for(const field of ['text','x','y','rotation','size','thickness']) $(field).addEventListener('input',()=>{
  const item=current();if(!item||busy)return;
  const value=field==='text'?$(field).value:Number($(field).value);
  if(!$(field).checkValidity()||(field!=='text'&&(!$(field).value||!Number.isFinite(value)))) {status('입력 범위를 확인하세요.',true);return;}
  item[field]=value;markDirty();draw();
  if(field==='text')$('items').selectedOptions[0].textContent=itemLabel(item);
});
$('width').addEventListener('change',()=>withBusy(async()=>{
  const item=current(),width=Number($('width').value);if(!item||item.kind!=='svg')return;
  if(!Number.isFinite(width)||width<.1||width>state.width)throw new Error('가로 크기를 보드 안으로 입력하세요.');
  const candidate={...item,width,height:item.height*width/item.width};
  candidate.rectangles=await rasterize(candidate);Object.assign(item,candidate);markDirty();
}));
$('ignore-white').addEventListener('change',()=>withBusy(async()=>{
  const item=current();if(!item||item.kind!=='svg')return;
  const candidate={...item,ignoreWhite:$('ignore-white').checked};candidate.rectangles=await rasterize(candidate);Object.assign(item,candidate);markDirty();
}));
$('upload').addEventListener('change',()=>withBusy(async()=>{
  const file=$('upload').files[0];if(!file)return;
  try {
    const svg=cleanSVG(await file.text()),width=Math.min(12,state.width*.6,state.height*.6/svg.ratio);
    const item={id:crypto.randomUUID(),kind:'svg',side:$('side').value,name:file.name,svg:svg.source,x:state.width/2,y:state.height/2,width,height:width*svg.ratio,rotation:0,ignoreWhite:false};
    item.rectangles=await rasterize(item);state.layout.items.push(item);selected=item.id;markDirty();status('SVG를 불러왔습니다. 크기와 위치를 조절하세요.');
  } finally {$('upload').value='';}
}));
function point(event) {const pt=new DOMPoint(event.clientX,event.clientY);return pt.matrixTransform($('board').getScreenCTM().inverse());}
$('board').addEventListener('pointerdown',event=>{
  if(busy||event.button!==0)return;const target=event.target.closest('[data-id]');if(!target)return;
  selected=target.getAttribute('data-id');const item=current(),pt=point(event);drag={id:selected,x:pt.x,y:pt.y,originalX:item.x,originalY:item.y};
  $('board').setPointerCapture(event.pointerId);refresh();event.preventDefault();
});
$('board').addEventListener('pointermove',event=>{
  if(!drag)return;const pt=point(event),item=current();
  item.x=Math.round(Math.max(0,Math.min(state.width,drag.originalX+pt.x-drag.x))*100)/100;
  item.y=Math.round(Math.max(0,Math.min(state.height,drag.originalY+pt.y-drag.y))*100)/100;
  $('x').value=item.x;$('y').value=item.y;markDirty();draw();
});
for(const event of ['pointerup','pointercancel']) $('board').addEventListener(event,()=>{drag=null;});
$('save').addEventListener('click',()=>withBusy(async()=>{
  status('저장 중…');
  const response=await api('/api/save',{revision:state.revision,layout:state.layout});const saved=await response.json();
  state.revision=saved.revision;dirty=false;$('dirty').textContent='저장됨';status(saved.message);
}));
window.addEventListener('beforeunload',event=>{if(dirty){event.preventDefault();event.returnValue='';}});
(async()=>{
  try{state=await (await api('/api/state')).json();$('dimensions').textContent=`${state.width} × ${state.height} mm · ${state.id} rev ${state.rev}`;$('board-id').textContent=`LOVELACE / ${state.id}`;
    $('x').max=state.width;$('y').max=state.height;$('width').max=state.width;$('save').disabled=false;
    refresh();await loadBackground();status('배치 준비 완료. 저장 전에는 원본 파일이 바뀌지 않습니다.');
  }catch(exc){error(exc);}
})();
