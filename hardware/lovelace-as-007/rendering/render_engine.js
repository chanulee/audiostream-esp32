'use strict';

function createPcbRenderer(canvas, mesh) {
  const gl=canvas.getContext('webgl',{antialias:true,alpha:true,preserveDrawingBuffer:true});
  if(!gl)throw new Error('WebGL을 사용할 수 없습니다.');
  const {center,radius}=mesh;
  const cameraGLSL=`uniform vec3 center,right,up,eye;uniform vec2 span;uniform float radius,perspective,cameraDistance,nearPlane,farPlane;
    vec4 project(vec3 p){vec3 q=p-center;float z=dot(q,eye);if(perspective>.5){float d=cameraDistance-z;float a=(farPlane+nearPlane)/(farPlane-nearPlane),b=-2.*farPlane*nearPlane/(farPlane-nearPlane);return vec4(dot(q,right)*cameraDistance/span.x,dot(q,up)*cameraDistance/span.y,a*d+b,d);}return vec4(dot(q,right)/span.x,dot(q,up)/span.y,-z/(radius*2.),1.);}`;
  const lightGLSL=`uniform vec3 lightDir,lightRight,lightUp;uniform vec3 center;uniform float radius;
    vec3 shadowPoint(vec3 p){vec3 q=p-center;return vec3(dot(q,lightRight)/(radius*1.15)*.5+.5,dot(q,lightUp)/(radius*1.15)*.5+.5,.5-dot(q,lightDir)/(radius*4.));}`;
  function program(vs,fs){
    function shader(type,src){const s=gl.createShader(type);gl.shaderSource(s,src);gl.compileShader(s);if(!gl.getShaderParameter(s,gl.COMPILE_STATUS))throw new Error(gl.getShaderInfoLog(s));return s;}
    const p=gl.createProgram();gl.attachShader(p,shader(gl.VERTEX_SHADER,vs));gl.attachShader(p,shader(gl.FRAGMENT_SHADER,fs));gl.linkProgram(p);if(!gl.getProgramParameter(p,gl.LINK_STATUS))throw new Error(gl.getProgramInfoLog(p));return p;
  }
  const faces=program(`attribute vec3 position,normal,color;attribute float board;varying vec3 world,N,C;varying float B;${cameraGLSL}
    void main(){world=position;N=normal;C=color;B=board;gl_Position=project(position);}`,
    `precision highp float;varying vec3 world,N,C;varying float B;
    uniform int mode;uniform vec3 paper,boardColor,cameraPosition,eye;uniform float perspective,roughness,metalness,intensity,exposure,environment,opacity,shadows,softness;
    uniform sampler2D shadowMap;${lightGLSL}
    const float PI=3.14159265359;
    vec3 srgb(vec3 c){return mix(c*12.92,1.055*pow(max(c,vec3(0.)),vec3(1./2.4))-.055,step(vec3(.0031308),c));}
    vec3 linear(vec3 c){return mix(c/12.92,pow((c+.055)/1.055,vec3(2.4)),step(vec3(.04045),c));}
    float unpack(vec4 c){return dot(c,vec4(1.,1./255.,1./65025.,1./16581375.));}
    float visibility(vec3 n){if(shadows<.5)return 1.;vec3 p=shadowPoint(world);if(p.x<0.||p.y<0.||p.x>1.||p.y>1.)return 1.;float sum=0.;float bias=max(.00022,.001*(1.-abs(dot(n,lightDir))));
      for(int x=-1;x<=1;x++)for(int y=-1;y<=1;y++){float depth=unpack(texture2D(shadowMap,p.xy+vec2(float(x),float(y))*(1.+softness)/2048.));sum+=p.z-bias<=depth?1.:0.;}return .2+.8*sum/9.;}
    vec3 fresnel(float c,vec3 f){return f+(1.-f)*pow(1.-c,5.);}
    vec3 brdf(vec3 n,vec3 v,vec3 l,vec3 base,float metal,float rough){vec3 h=normalize(v+l);float nv=max(dot(n,v),.001),nl=max(dot(n,l),0.),nh=max(dot(n,h),0.),vh=max(dot(v,h),0.);float a=rough*rough,a2=a*a;float d=a2/(PI*pow(nh*nh*(a2-1.)+1.,2.)+.00001);float k=pow(rough+1.,2.)/8.;float g=nv/(nv*(1.-k)+k)*nl/(nl*(1.-k)+k);vec3 f=fresnel(vh,mix(vec3(.04),base,metal));return ((1.-f)*(1.-metal)*base/PI+d*g*f/(4.*nv*max(nl,.001)))*nl;}
    vec3 softbox(vec3 r,float rough){float p=mix(180.,3.,rough);float key=pow(max(dot(r,lightDir),0.),p);float strip=pow(max(dot(r,normalize(vec3(-.5,.25,1.))),0.),p*.45);return vec3(.35+.18*max(r.z,0.)+key*3.+strip*1.8);}
    vec3 aces(vec3 x){return clamp((x*(2.51*x+.03))/(x*(2.43*x+.59)+.14),0.,1.);}
    void main(){vec3 n=normalize(N);vec3 v=perspective>.5?normalize(cameraPosition-world):eye;if(dot(n,v)<0.)n=-n;vec3 base=mix(C,linear(boardColor),step(.5,B));
      if(mode==0||mode==1){gl_FragColor=vec4(paper,1.);return;}
      if(mode==2){gl_FragColor=vec4(srgb(base),1.);return;}
      if(mode==5){gl_FragColor=vec4(n*.5+.5,1.);return;}
      if(mode==6){gl_FragColor=vec4(vec3(.65,.72,.82),opacity*(.2+.8*pow(1.-abs(dot(n,v)),2.)));return;}
      float grey=max(max(base.r,base.g),base.b)-min(min(base.r,base.g),base.b);
      float metal=metalness*(1.-step(.5,B))*step(.14,max(max(base.r,base.g),base.b))*max(1.-step(.08,grey),step(base.b*2.,base.r));
      float rough=clamp(roughness+(.2*(1.-metal)),.06,.98);
      if(mode==3){base=linear(paper)*.7;metal=0.;rough=.6;}
      vec3 color=brdf(n,v,lightDir,base,metal,rough)*intensity*4.*visibility(n);
      color+=brdf(n,v,normalize(vec3(-.65,.3,.6)),base,metal,rough)*intensity*.8;
      vec3 f=fresnel(max(dot(n,v),0.),mix(vec3(.04),base,metal));
      color+=environment*(base*(1.-metal)*.25+softbox(reflect(-v,n),rough)*f*(1.-rough*.4));
      gl_FragColor=vec4(srgb(aces(color*exposure)),1.);
    }`);
  const edges=program(`attribute vec3 start,end;attribute vec2 corner;uniform vec2 pixels;uniform float width;${cameraGLSL}
    void main(){vec4 a=project(start),b=project(end);vec2 d=(b.xy/b.w-a.xy/a.w)*pixels;d=length(d)>.00001?normalize(d):vec2(1.,0.);vec4 p=mix(a,b,corner.x);p.xy+=vec2(-d.y,d.x)*width/pixels*corner.y*p.w;gl_Position=p;}`,
    'precision mediump float;uniform vec3 ink;uniform float alpha;void main(){gl_FragColor=vec4(ink,alpha);}');
  const inkProgram=program(`attribute vec3 position;${cameraGLSL}void main(){gl_Position=project(position);}`,
    'precision mediump float;uniform vec3 ink;void main(){gl_FragColor=vec4(ink,1.);}');
  const depthProgram=program(`attribute vec3 position;${lightGLSL}void main(){vec3 p=shadowPoint(position);gl_Position=vec4(p*2.-1.,1.);}`,
    `precision highp float;void main(){vec4 c=fract(gl_FragCoord.z*vec4(1.,255.,65025.,16581375.));c-=c.yzww*vec4(1./255.,1./255.,1./255.,0.);gl_FragColor=c;}`);
  function buffer(data){const b=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,b);gl.bufferData(gl.ARRAY_BUFFER,new Float32Array(data),gl.STATIC_DRAW);return b;}
  const positionBuffer=buffer(mesh.triangles),normalBuffer=buffer(mesh.normals),colorBuffer=buffer(mesh.colors),boardBuffer=buffer(mesh.board),silkBuffer=buffer(mesh.silk);
  function lineBuffer(lines){const data=new Float32Array(lines.length/6*48);let k=0;for(let i=0;i<lines.length;i+=6)for(const c of [[0,-1],[1,-1],[0,1],[0,1],[1,-1],[1,1]]){data.set(lines.slice(i,i+6),k);k+=6;data.set(c,k);k+=2;}return {buffer:buffer(data),count:data.length/8};}
  const fineEdges=lineBuffer(mesh.lines),cleanEdges=lineBuffer(mesh.clean_lines);
  function attribute(p,name,b,size,stride=0,offset=0){const a=gl.getAttribLocation(p,name);if(a<0)return;gl.bindBuffer(gl.ARRAY_BUFFER,b);gl.enableVertexAttribArray(a);gl.vertexAttribPointer(a,size,gl.FLOAT,false,stride,offset);}
  function resetAttributes(){for(let i=0;i<gl.getParameter(gl.MAX_VERTEX_ATTRIBS);i++)gl.disableVertexAttribArray(i);}
  function f(p,k,v){gl.uniform1f(gl.getUniformLocation(p,k),v);}
  function v3(p,k,v){gl.uniform3fv(gl.getUniformLocation(p,k),v);}
  const shadowTexture=gl.createTexture();gl.bindTexture(gl.TEXTURE_2D,shadowTexture);gl.texImage2D(gl.TEXTURE_2D,0,gl.RGBA,2048,2048,0,gl.RGBA,gl.UNSIGNED_BYTE,null);
  for(const parameter of [gl.TEXTURE_MIN_FILTER,gl.TEXTURE_MAG_FILTER])gl.texParameteri(gl.TEXTURE_2D,parameter,gl.NEAREST);
  for(const parameter of [gl.TEXTURE_WRAP_S,gl.TEXTURE_WRAP_T])gl.texParameteri(gl.TEXTURE_2D,parameter,gl.CLAMP_TO_EDGE);
  const shadowDepth=gl.createRenderbuffer();gl.bindRenderbuffer(gl.RENDERBUFFER,shadowDepth);gl.renderbufferStorage(gl.RENDERBUFFER,gl.DEPTH_COMPONENT16,2048,2048);
  const shadowFrame=gl.createFramebuffer();gl.bindFramebuffer(gl.FRAMEBUFFER,shadowFrame);gl.framebufferTexture2D(gl.FRAMEBUFFER,gl.COLOR_ATTACHMENT0,gl.TEXTURE_2D,shadowTexture,0);gl.framebufferRenderbuffer(gl.FRAMEBUFFER,gl.DEPTH_ATTACHMENT,gl.RENDERBUFFER,shadowDepth);
  if(gl.checkFramebufferStatus(gl.FRAMEBUFFER)!==gl.FRAMEBUFFER_COMPLETE)throw new Error('그림자 버퍼를 만들 수 없습니다.');
  gl.bindFramebuffer(gl.FRAMEBUFFER,null);
  let lastShadow='';

  function render(settings,exportScale=null){
    const s=settings,dpr=typeof exportScale==='number'?exportScale:Math.min(window.devicePixelRatio||1,2);
    const max=gl.getParameter(gl.MAX_RENDERBUFFER_SIZE);
    const w=Math.min(max,Math.max(1,Math.round(canvas.clientWidth*dpr))),h=Math.min(max,Math.max(1,Math.round(canvas.clientHeight*dpr)));
    if(canvas.width!==w||canvas.height!==h){canvas.width=w;canvas.height=h;}
    const az=s.azimuth*Math.PI/180,el=s.elevation*Math.PI/180;
    const right=[-Math.sin(az),Math.cos(az),0],up=[-Math.sin(el)*Math.cos(az),-Math.sin(el)*Math.sin(az),Math.cos(el)],eye=[Math.cos(el)*Math.cos(az),Math.cos(el)*Math.sin(az),Math.sin(el)];
    const spanY=radius*1.12/s.zoom*Math.max(1,h/w),distance=radius*1.12*Math.max(1,h/w)*s.lens/12;
    const la=s.lightAz*Math.PI/180,le=s.lightEl*Math.PI/180;
    const lightDir=[Math.cos(le)*Math.cos(la),Math.cos(le)*Math.sin(la),Math.sin(le)],lightRight=[-Math.sin(la),Math.cos(la),0],lightUp=[-Math.sin(le)*Math.cos(la),-Math.sin(le)*Math.sin(la),Math.cos(le)];
    function light(p){v3(p,'center',center);f(p,'radius',radius);v3(p,'lightDir',lightDir);v3(p,'lightRight',lightRight);v3(p,'lightUp',lightUp);}
    function camera(p){gl.useProgram(p);light(p);v3(p,'right',right);v3(p,'up',up);v3(p,'eye',eye);gl.uniform2f(gl.getUniformLocation(p,'span'),spanY*w/h,spanY);f(p,'perspective',s.projection==='perspective'?1:0);f(p,'cameraDistance',distance);f(p,'nearPlane',Math.max(.1,distance-radius*1.1));f(p,'farPlane',distance+radius*2);}
    const lit=['studio','material'].includes(s.style);
    gl.enable(gl.DEPTH_TEST);gl.depthFunc(gl.LEQUAL);gl.disable(gl.BLEND);gl.colorMask(true,true,true,true);gl.depthMask(true);
    const shadowKey=[s.lightAz,s.lightEl].join(',');
    if(lit&&s.shadows&&shadowKey!==lastShadow){
      gl.bindFramebuffer(gl.FRAMEBUFFER,shadowFrame);gl.viewport(0,0,2048,2048);gl.clearColor(1,1,1,1);gl.clear(gl.COLOR_BUFFER_BIT|gl.DEPTH_BUFFER_BIT);
      gl.useProgram(depthProgram);light(depthProgram);attribute(depthProgram,'position',positionBuffer,3);gl.drawArrays(gl.TRIANGLES,0,mesh.triangles.length/3);resetAttributes();lastShadow=shadowKey;
    }
    gl.bindFramebuffer(gl.FRAMEBUFFER,null);gl.viewport(0,0,w,h);gl.clearColor(...s.paper,s.transparent?0:1);gl.clear(gl.COLOR_BUFFER_BIT|gl.DEPTH_BUFFER_BIT);
    const wire=s.style==='wire',xray=s.style==='xray',pure=['line','detail'].includes(s.style);
    camera(faces);attribute(faces,'position',positionBuffer,3);attribute(faces,'normal',normalBuffer,3);attribute(faces,'color',colorBuffer,3);attribute(faces,'board',boardBuffer,1);
    const modes={line:0,detail:1,original:2,studio:3,material:4,normal:5,xray:6};
    gl.uniform1i(gl.getUniformLocation(faces,'mode'),modes[s.style]||0);v3(faces,'paper',s.paper);v3(faces,'boardColor',s.boardColor);v3(faces,'cameraPosition',center.map((v,i)=>v+eye[i]*distance));
    for(const key of ['roughness','metalness','intensity','exposure','environment','opacity','softness'])f(faces,key,s[key]);f(faces,'shadows',s.shadows?1:0);
    gl.activeTexture(gl.TEXTURE0);gl.bindTexture(gl.TEXTURE_2D,shadowTexture);gl.uniform1i(gl.getUniformLocation(faces,'shadowMap'),0);
    if(pure)gl.colorMask(false,false,false,false);
    if(xray){gl.disable(gl.DEPTH_TEST);gl.depthMask(false);gl.enable(gl.BLEND);gl.blendFunc(gl.SRC_ALPHA,gl.ONE);}
    gl.enable(gl.POLYGON_OFFSET_FILL);gl.polygonOffset(1,2);
    if(!wire)gl.drawArrays(gl.TRIANGLES,0,mesh.triangles.length/3);
    gl.disable(gl.POLYGON_OFFSET_FILL);gl.colorMask(true,true,true,true);resetAttributes();
    if(!wire&&!xray){camera(inkProgram);attribute(inkProgram,'position',silkBuffer,3);v3(inkProgram,'ink',s.style==='original'||s.style==='material'?[.92,.94,.9]:s.ink);gl.drawArrays(gl.TRIANGLES,0,mesh.silk.length/3);resetAttributes();}
    if(pure||wire||xray||s.edges){
      if(wire||xray){gl.disable(gl.DEPTH_TEST);gl.enable(gl.BLEND);gl.blendFunc(gl.SRC_ALPHA,xray?gl.ONE:gl.ONE_MINUS_SRC_ALPHA);}
      camera(edges);const data=s.style==='line'?cleanEdges:fineEdges;
      attribute(edges,'start',data.buffer,3,32,0);attribute(edges,'end',data.buffer,3,32,12);attribute(edges,'corner',data.buffer,2,32,24);
      gl.uniform2f(gl.getUniformLocation(edges,'pixels'),w,h);f(edges,'width',Math.max(.6,s.stroke*h/(2*spanY))*(s.style==='detail'?.75:1));v3(edges,'ink',s.ink);f(edges,'alpha',xray?.38:wire?.65:1);
      gl.drawArrays(gl.TRIANGLES,0,data.count);resetAttributes();
    }
    gl.depthMask(true);gl.enable(gl.DEPTH_TEST);gl.disable(gl.BLEND);
  }
  return {render,maxSize:gl.getParameter(gl.MAX_RENDERBUFFER_SIZE)};
}
