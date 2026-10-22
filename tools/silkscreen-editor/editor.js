/* SVG is rendered locally as a monochrome stencil, at 0.025 mm resolution. */
'use strict';
const $ = id => document.getElementById(id);
const token = location.hash.slice(1);
const NS = 'http://www.w3.org/2000/svg';
let state, selected = null, background = null, drag = null, dirty = false, busy = false;
let inspection=null, inspectionURL=null;
let edits=null,savedLayout='',activeVariant=new URLSearchParams(location.search).get('variant')||'',zoom=100;
const sessions=new Map();
const holeSizes={'M2':2.2,'M2.5':2.7,'M3':3.2,'M4':4.3,'M5':5.3};
function visibleItems() {
  const side=$('side').value;
  return [...(state.editableComponents ? state.layout.components.filter(c=>c.both||c.side===side).map(c=>({...c,kind:'native',x:side==='B.SilkS'?state.width-c.x:c.x,rotation:side==='B.SilkS'?-c.rotation:c.rotation})) : []), ...state.layout.items.filter(i=>i.side===side), ...(state.editableHoles ? state.layout.holes.map(h=>({...h,kind:'hole',x:side==='B.SilkS'?state.width-h.x:h.x})) : [])];
}
function holePosition(item,x,y) {
  item.x=(state.editableComponents&&state.layout.components.some(c=>c.id===item.id)||state.editableHoles&&holeSizes[item.id])&&$('side').value==='B.SilkS'?state.width-x:x;item.y=y;
}

async function api(path, data) {
  const endpoint=path+(activeVariant?`${path.includes('?')?'&':'?'}variant=${encodeURIComponent(activeVariant)}`:'');
  const response = await fetch(endpoint, {method: data ? 'POST' : 'GET', headers: {'X-Silk-Token': token, ...(data ? {'Content-Type':'application/json'} : {})}, ...(data ? {body:JSON.stringify(data)} : {})});
  if (!response.ok) throw new Error((await response.json()).error);
  return response;
}
function status(message, error=false) { $('status').textContent=message; $('status').classList.toggle('error',error); }
function clearInspection() {
  inspection=null;
  if(inspectionURL)URL.revokeObjectURL(inspectionURL);inspectionURL=null;
  $('resume').hidden=true;$('check-results').textContent='';
}
function updateDirty(){dirty=JSON.stringify(state.layout)!==savedLayout;$('dirty').textContent=dirty?'저장하지 않은 변경':'저장됨';$('undo').disabled=busy||!edits?.canUndo;$('redo').disabled=busy||!edits?.canRedo;}
function markDirty(key=null){clearInspection();edits?.record(state.layout,key);updateDirty();}
function restoreEdit(direction){if(busy||!edits)return;const layout=edits[direction]();if(!layout)return;state.layout=layout;clearInspection();updateDirty();refresh();status(direction==='undo'?'실행을 취소했습니다.':'다시 실행했습니다.');}
$('undo').addEventListener('click',()=>restoreEdit('undo'));
$('redo').addEventListener('click',()=>restoreEdit('redo'));
window.addEventListener('keydown',event=>{if(!(event.metaKey||event.ctrlKey)||event.altKey)return;const key=event.key.toLowerCase();if(key==='z'||key==='y'){event.preventDefault();restoreEdit(key==='y'||event.shiftKey?'redo':'undo');}else if(key==='s'){event.preventDefault();$('save').click();}});
function applyZoom(){const board=$('board');board.style.width=`${state.width*5*zoom/100}px`;$('zoom').value=zoom;$('zoom-value').textContent=`${Math.round(zoom)}%`;}
$('zoom').addEventListener('input',()=>{zoom=Number($('zoom').value);applyZoom();});
$('fit').addEventListener('click',()=>{if(!state)return;zoom=Math.max(30,Math.min(400,(document.querySelector('.stage').clientWidth-60)/(state.width*5)*100));applyZoom();});

function current() {return state.layout.items.find(i=>i.id===selected)||state.layout.holes?.find(i=>i.id===selected)||state.layout.components?.find(i=>i.id===selected);}
function itemLabel(item) {return state.editableComponents&&state.layout.components.some(c=>c.id===item.id) ? item.name : holeSizes[item.id]&&state.editableHoles ? `${item.id} · 구멍 Ø${holeSizes[item.id]} mm` : item.kind==='text' ? item.text.trim().replace(/\n/g,' / ')||'(빈 텍스트)' : item.name||'SVG';}
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
  board.replaceChildren(svgNode('rect',{width:state.width,height:state.height,fill:state.color||'#195039'}));
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
  for(const item of visibleItems().filter(()=>!checked)) {
    const g=svgNode('g',{'data-id':item.id,class:'art',transform:`translate(${item.x} ${item.y}) rotate(${item.rotation||0})`});
    if(item.kind==='native') {
      const [x,y,w,h]=item.bounds, back=side==='B.SilkS';
      const art=svgNode('g',back?{transform:'scale(-1 1)','pointer-events':'none'}:{'pointer-events':'none'});
      art.append(svgNode('image',{href:`/assets/${item.id}-${side[0]}.svg`,x,y,width:w,height:h}));
      for(const t of item.texts.filter(t=>t.side===side[0])){
        const text=svgNode('text',{'text-anchor':t.align,'dominant-baseline':t.valign,'font-family':'Arial,sans-serif','font-size':t.size,fill:'#fff',transform:`translate(${t.x} ${t.y}) rotate(${t.rotation}) scale(${t.mirror?-1:1} 1)`},t.text);art.append(text);
      }
      for(const [dx,dy,diameter] of item.drills||[])art.append(svgNode('circle',{cx:dx,cy:dy,r:diameter/2,fill:'#b6b8b9'}));
      g.append(art);
      if(item.side===side)g.append(svgNode('rect',{x:back?-x-w:x,y,width:w,height:h,fill:'transparent'}));
      else for(const [dx,dy,diameter] of item.drills||[])g.append(svgNode('circle',{cx:back?-dx:dx,cy:dy,r:diameter/2+.2,fill:'transparent'}));
    } else if(item.kind==='hole') {
      g.append(svgNode('circle',{r:holeSizes[item.id]/2,fill:'#b6b8b9',stroke:'#e8bb63','stroke-width':.18}));
      g.append(svgNode('text',{y:-holeSizes[item.id]/2-1.3,'text-anchor':'middle','dominant-baseline':'central','font-size':.85,fill:'#fff'},`${item.id} / ${holeSizes[item.id]}`));
    } else if(item.kind==='text') {
      const text=svgNode('text',{'text-anchor':item.align||'middle','dominant-baseline':item.valign||'central','font-family':'Arial,sans-serif','font-size':item.size,fill:'#fff',stroke:'#fff','stroke-width':Math.max(0,item.thickness-.12)});
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
  for(const item of visibleItems()) {
    const option=document.createElement('option'); option.value=item.id;
    option.textContent=itemLabel(item); items.append(option);
  }
  if(![...items.options].some(o=>o.value===selected)) selected=items.options[0]?.value||null;
  items.value=selected||'';
  const item=current(),native=state.editableComponents&&state.layout.components.some(c=>c.id===item?.id),hole=state.editableHoles&&item&&holeSizes[item.id]; $('properties').disabled=!item;
  $('rotation').parentElement.hidden=!!hole;$('delete').hidden=!!hole;
  $('text-label').hidden=item?.kind!=='text'&&!(native&&item.texts.length);
  if(native&&item.texts.length){$('text').value=item.texts.map(t=>t.text).join('\n');$('text').maxLength=10000;}else $('text').maxLength=120; $('text-fields').hidden=item?.kind!=='text'; $('svg-fields').hidden=item?.kind!=='svg';
  if(item) for(const field of ['text','x','y','rotation','size','thickness','width','height']) {
    if(native&&field==='text')continue;
    const value=(hole||native)&&field==='x'&&$('side').value==='B.SilkS'?state.width-item.x:native&&field==='rotation'&&$('side').value==='B.SilkS'?-item.rotation:item[field];$(field).value=typeof value==='number'?Number(value.toFixed(4)):value??'';
  }
  $('ignore-white').checked=item?.ignoreWhite||false;
  $('selected-name').textContent=item?itemLabel(item):'요소를 선택하세요';
  const provenance=$('provenance');provenance.replaceChildren();
  if(item?.source){const link=document.createElement('a');link.href=item.source.url;link.target='_blank';link.rel='noreferrer';link.textContent=item.source.name;provenance.append(link,document.createElement('br'),document.createTextNode(item.source.license||''));}
  if(item?.note){const note=document.createElement('p');note.textContent=item.note;provenance.append(note);}
  const list=$('layer-list'),query=$('search').value.toLowerCase();list.replaceChildren();
  const visible=visibleItems();$('item-count').textContent=visible.length;
  for(const entry of visible.filter(i=>itemLabel(i).toLowerCase().includes(query))){const row=document.createElement('button');row.className='layer-row';row.setAttribute('aria-pressed',String(entry.id===selected));row.textContent=itemLabel(entry);row.addEventListener('click',()=>{selected=entry.id;refresh();});list.append(row);}
  updateDirty();draw();

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
  try{updateDirty();await action();}catch(exc){error(exc);}finally{busy=false;$('save').disabled=!state;$('check').disabled=false;$('side').disabled=false;$('upload').disabled=false;refresh();}
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
$('delete').addEventListener('click',()=>{if(!current()||busy)return;state.layout.items=state.layout.items.filter(i=>i.id!==selected);if(state.editableComponents)state.layout.components=state.layout.components.filter(i=>i.id!==selected);selected=null;markDirty();refresh();});
for(const field of ['text','x','y','rotation','size','thickness']) $(field).addEventListener('input',()=>{
  const item=current();if(!item||busy)return;
  const value=field==='text'?$(field).value:Number($(field).value);
  if(!$(field).checkValidity()||(field!=='text'&&(!$(field).value||!Number.isFinite(value)))) {status('입력 범위를 확인하세요.',true);return;}
  const native=state.editableComponents&&state.layout.components.some(c=>c.id===item.id);
  if(native&&field==='text'){const lines=value.split('\n');if(lines.length!==item.texts.length){status(`구성 텍스트 ${item.texts.length}줄을 유지하세요.`,true);return;}lines.forEach((line,i)=>item.texts[i].text=line);markDirty(field+selected);draw();return;}
  if(field==='rotation'&&native&&$('side').value==='B.SilkS')item.rotation=-value;else if(field==='x'&&(native||state.editableHoles&&holeSizes[item.id])&&$('side').value==='B.SilkS')item.x=state.width-value;else item[field]=value;markDirty(field+selected);draw();
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
  selected=target.getAttribute('data-id');const item=current(),pt=point(event);drag={id:selected,x:pt.x,y:pt.y,originalX:(state.editableComponents&&state.layout.components.some(c=>c.id===item.id)||state.editableHoles&&holeSizes[item.id])&&$('side').value==='B.SilkS'?state.width-item.x:item.x,originalY:item.y};
  $('board').setPointerCapture(event.pointerId);refresh();event.preventDefault();
});
$('board').addEventListener('pointermove',event=>{
  if(!drag)return;const pt=point(event),item=current();
  const x=Math.round(Math.max(0,Math.min(state.width,drag.originalX+pt.x-drag.x))*100)/100;
  const y=Math.round(Math.max(0,Math.min(state.height,drag.originalY+pt.y-drag.y))*100)/100;
  holePosition(item,x,y);
  $('x').value=x;$('y').value=y;clearInspection();dirty=true;$('dirty').textContent='저장하지 않은 변경';draw();
});
for(const event of ['pointerup','pointercancel']) $('board').addEventListener(event,()=>{if(drag)markDirty();drag=null;refresh();});
$('save').addEventListener('click',()=>withBusy(async()=>{
  status('저장 중…');
  const response=await api('/api/save',{revision:state.revision,layout:state.layout});const saved=await response.json();
  state.revision=saved.revision;savedLayout=JSON.stringify(state.layout);updateDirty();status(saved.message);
}));
window.addEventListener('beforeunload',event=>{if(dirty){event.preventDefault();event.returnValue='';}});
$('search').addEventListener('input',refresh);
$('module').addEventListener('change',()=>{const c=state.catalog?.find(c=>c.id===$('module').value);$('module-source').textContent=c?`${c.source?.name||'원본'} · ${c.source?.license||''}`:'';});
$('add-module').addEventListener('click',()=>{
  if(busy||!state?.editableComponents)return;
  const c=state.catalog.find(c=>c.id===$('module').value);if(!c)return;
  if(state.layout.components.some(i=>i.id===c.id)){selected=c.id;$('side').value=c.side;refresh();status('이미 배치된 모듈을 선택했습니다.');return;}
  const item=structuredClone(c);item.x=state.width/2-(item.bounds[0]+item.bounds[2]/2);item.y=state.height/2-(item.bounds[1]+item.bounds[3]/2);item.rotation=0;
  state.layout.components.push(item);selected=item.id;$('side').value=item.side;markDirty();refresh();loadBackground().catch(error);
});
$('projects').addEventListener('click',()=>{$('overview').hidden=false;document.querySelector('main').hidden=true;});
function setupProject(){
  $('overview').hidden=true;document.querySelector('main').hidden=false;
  $('dimensions').textContent=`${state.width} × ${state.height} mm · ${state.id}`;$('board-id').textContent=`LOVELACE / ${state.id}`;
  $('x').max=state.width;$('y').max=state.height;$('width').max=state.width;$('save').disabled=false;
  if(state.editableComponents||state.editableHoles){$('x').step='any';$('y').step='any';document.title='LOVELACE · Ruler Studio';document.querySelector('h1').textContent='Ruler Studio';}
  $('variant-notes').textContent=state.notes||'';
  const variants=state.variants||[];$('projects').hidden=!variants.length;$('variant-label').hidden=!variants.length;
  $('variant').replaceChildren();$('project-cards').replaceChildren();
  for(const v of variants){const option=document.createElement('option');option.value=v.id;option.textContent=v.name;$('variant').append(option);const card=document.createElement('button');card.className='project-card';const title=document.createElement('strong');title.textContent=v.name;const desc=document.createElement('span');desc.textContent=v.description;card.append(title,desc);card.addEventListener('click',()=>switchVariant(v.id));$('project-cards').append(card);}
  $('variant').value=activeVariant;
  $('library').hidden=!state.editableComponents;$('module').replaceChildren();
  for(const c of state.catalog||[]){const option=document.createElement('option');option.value=c.id;option.textContent=c.name;$('module').append(option);}
  $('module').dispatchEvent(new Event('change'));
  refresh();applyZoom();
}
async function switchVariant(id){
  if(busy||!state)return;
  sessions.set(activeVariant,{state,selected,edits,savedLayout,side:$('side').value});
  const previous=activeVariant;activeVariant=id;busy=true;
  try{
    const cached=sessions.get(id);
    if(cached){({state,selected,edits,savedLayout}=cached);$('side').value=cached.side;}
    else{state=await(await api('/api/state')).json();selected=null;savedLayout=JSON.stringify(state.layout);edits=new LayoutHistory(state.layout);$('side').value='F.SilkS';}
    clearInspection();background=null;setupProject();await loadBackground();
    window.history.replaceState(null,'',`?variant=${encodeURIComponent(id)}${location.hash}`);
    status('설계안을 전환했습니다. 각 안의 편집 내용은 이 탭에서 유지됩니다.');
  }catch(exc){activeVariant=previous;const cached=sessions.get(previous);({state,selected,edits,savedLayout}=cached);$('side').value=cached.side;setupProject();error(exc);}
  finally{busy=false;refresh();}
}
$('variant').addEventListener('change',()=>switchVariant($('variant').value));
(async()=>{
  try{state=await(await api('/api/state')).json();activeVariant=state.activeVariant||'';savedLayout=JSON.stringify(state.layout);edits=new LayoutHistory(state.layout);$('side').value='F.SilkS';setupProject();await loadBackground();$('fit').click();status('배치 준비 완료. 실행 취소·다시 실행과 원본 모듈 추가를 사용할 수 있습니다.');}
  catch(exc){error(exc);}
})();
