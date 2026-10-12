// Dependency-free checks against the production hover module, including capture
// ordering relative to the chart's existing pointer handlers and zoom redraws.
'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
class Element{
 constructor(tag,doc){this.tagName=tag;this.ownerDocument=doc;this.children=[];this.listeners=new Map();this.attributes={};this.hidden=false;this._text='';}
 set textContent(value){this._text=String(value);this.replaceChildren();}get textContent(){return this._text+this.children.map(child=>child.textContent).join('');}
 append(...nodes){for(const node of nodes){node.parentNode=this;this.children.push(node);}}
 replaceChildren(...nodes){for(const node of this.children)node.parentNode=null;this.children=[];this.append(...nodes);}
 setAttribute(key,value){this.attributes[key]=String(value);}getAttribute(key){return this.attributes[key]??null;}
 contains(node){return this===node||this.children.some(child=>child.contains(node));}
 remove(){if(this.parentNode){this.parentNode.children=this.parentNode.children.filter(child=>child!==this);this.parentNode=null;}}
 addEventListener(type,handler,capture=false){if(!this.listeners.has(type))this.listeners.set(type,[]);this.listeners.get(type).push({handler,capture:!!capture});}
 removeEventListener(type,handler,capture=false){this.listeners.set(type,(this.listeners.get(type)||[]).filter(item=>item.handler!==handler||item.capture!==!!capture));}
 createSVGPoint(){return {x:0,y:0,matrixTransform(matrix){return {x:this.x*matrix.a+matrix.e,y:this.y*matrix.d+matrix.f};}};}
 getScreenCTM(){return this.ctm===null?null:{inverse:()=>this.ctm||{a:1,d:1,e:0,f:0}};}
}
const source=fs.readFileSync(path.join(__dirname,'../dashboard/hover.js'),'utf8');
function harness(beforeInit){
 const doc=new Element('document');doc.createElement=tag=>new Element(tag,doc);doc.createElementNS=(_,tag)=>new Element(tag,doc);
 const svg=doc.createElement('svg'),readout=doc.createElement('div'),outside=doc.createElement('button');doc.append(svg,readout,outside);
 const ctx={document:doc};vm.createContext(ctx);vm.runInContext(source,ctx);
 const hover=ctx.ChartHover;
 const fire=(type,extra={},target=svg)=>{
  const event={type,target,pointerId:1,pointerType:'mouse',isPrimary:true,button:0,buttons:0,clientX:470,clientY:180,preventDefault(){this.defaultPrevented=true;},...extra};
  const chain=[];for(let current=target;current;current=current.parentNode)chain.push(current);
  for(const node of chain.slice().reverse())for(const listener of (node.listeners.get(type)||[]).slice())if(listener.capture)listener.handler(event);
  for(const node of chain)for(const listener of (node.listeners.get(type)||[]).slice())if(!listener.capture)listener.handler(event);
  return event;
 };
 const api={doc,svg,readout,outside,hover,fire};if(beforeInit)beforeInit(api);hover.init({svg,readout});return api;
}
const series=[
 {label:'Target power',units:'W',color:'#b2c1cc',valueIndex:1,rows:[[0,100],[10,200],[20,250],[30,300],[40,350]]},
 {label:'Candidate plant',units:'W',color:'#58dec8',valueIndex:1,rows:[[0,99],[12,198.7654],[24,null],[36,298]]},
 {label:'Modeled cadence',units:'RPM',color:'#ba91ff',valueIndex:1,rows:[[0,80],[10,0],[20,null],[30,90],[40,100]]},
 {label:'Delivered cadence',units:'RPM',color:'#ead5ff',valueIndex:2,rows:[[0,80,79],[11,0,81],[21,90,0],[31,91,89],[40,100,99]]},
 {label:'Actual motor',units:'steps',color:'#ff646b',valueIndex:1,rows:[[0,10000],[9,11000],[19,null],[29,13000],[39,14000]]},
 {label:'Unrecorded',units:'W',valueIndex:1,rows:[]},
 {label:'<img src=x onerror=alert(1)>',units:'<script>',valueIndex:1,rows:[[0,0]]}
];
const full={from:0,to:40,end:40,series};
const x=time=>65+time/40*810;
const h=harness(),{hover,svg,readout,fire}=h;
const cursor=()=>svg.children.find(node=>node.getAttribute('data-hover-cursor')==='true');
const inspect=time=>fire('pointermove',{clientX:x(time)});
fire('pointermove');assert.equal(readout.hidden,true);assert.equal(cursor(),undefined);
hover.update(full);inspect(10);assert.equal(readout.hidden,false);assert.equal(Number(cursor().getAttribute('x1')),x(10));
assert.match(readout.textContent,/Cursor 10 s/);assert.match(readout.textContent,/Target power: 200 W · sample 10 s/);
assert.match(readout.textContent,/Candidate plant: 198.765 W · sample 12 s/);assert.match(readout.textContent,/Modeled cadence: 0 RPM · sample 10 s/);
assert.match(readout.textContent,/Delivered cadence: 81 RPM · sample 11 s/);assert.match(readout.textContent,/Actual motor: 11000 steps · sample 9 s/);
assert.match(readout.textContent,/Unrecorded: unavailable · no retained samples/);
assert.match(readout.textContent,/<img src=x onerror=alert\(1\)>: 0 <script>/);assert.equal(readout.children.some(node=>node.tagName==='img'),false);
assert.equal(readout.getAttribute('role'),'status');assert.equal(readout.getAttribute('aria-live'),'polite');
assert.equal(cursor().getAttribute('pointer-events'),'none');assert.equal(cursor().getAttribute('y1'),'40');assert.equal(cursor().getAttribute('y2'),'440');
inspect(20);assert.match(readout.textContent,/Candidate plant: unavailable · sample 24 s/);assert.match(readout.textContent,/Modeled cadence: unavailable · sample 20 s/);assert.match(readout.textContent,/Actual motor: unavailable · sample 19 s/);
inspect(15);assert.match(readout.textContent,/Target power: 200 W · sample 10 s/); // tie is deterministically earlier
fire('pointermove',{clientX:x(10),clientY:400});assert.match(readout.textContent,/Target power: 200 W/); // same shared time from cadence panel
fire('pointerleave');assert.equal(readout.hidden,true);assert.equal(cursor(),undefined);
inspect(10);fire('pointermove',{clientX:64});assert.equal(readout.hidden,true);
fire('pointermove',{clientY:441});assert.equal(readout.hidden,true);
svg.ctm=null;assert.doesNotThrow(()=>inspect(10));assert.equal(readout.hidden,true);delete svg.ctm;
// Convert CSS screen coordinates through the SVG transform (responsive/mobile view).
svg.ctm={a:2,d:2,e:-20,f:-40};fire('pointermove',{clientX:(x(10)+20)/2,clientY:110});assert.match(readout.textContent,/Cursor 10 s/);delete svg.ctm;
// Zoom retains the exact same row selection with the new x -> elapsed mapping.
hover.update({...full,from:10,to:20});assert.equal(readout.hidden,true);fire('pointermove',{clientX:470});assert.match(readout.textContent,/Cursor 15 s/);assert.match(readout.textContent,/Target power: 200 W · sample 10 s/);
hover.update(full);
// Touch taps pin; scrolls, selection gestures, secondary touches and cancellations do not.
const touch=(type,time,extra={})=>fire(type,{clientX:x(time),pointerType:'touch',...extra});
assert.equal(touch('pointerdown',10).defaultPrevented,undefined);touch('pointerup',10);assert.match(readout.textContent,/Cursor 10 s · pinned/);
fire('pointerleave');inspect(30);assert.match(readout.textContent,/Cursor 10 s · pinned/);
fire('pointerdown',{},h.outside);assert.equal(readout.hidden,true);
touch('pointerdown',10);touch('pointerup',10);fire('keydown',{key:'Escape'},h.doc);assert.equal(readout.hidden,true);
touch('pointerdown',10);touch('pointermove',10,{clientY:210});touch('pointerup',10,{clientY:210});assert.equal(readout.hidden,true);
touch('pointerdown',10);touch('pointerdown',20,{pointerId:2,isPrimary:false});touch('pointerup',10);assert.equal(readout.hidden,true);
touch('pointerdown',10);touch('pointercancel',10);touch('pointerup',10);assert.equal(readout.hidden,true);
touch('pointerdown',10);touch('lostpointercapture',10);touch('pointerup',10);assert.equal(readout.hidden,true);
svg.setAttribute('data-select-mode','true');touch('pointerdown',10);svg.setAttribute('data-select-mode','false');touch('pointerup',10);assert.equal(readout.hidden,true);
svg.setAttribute('data-select-mode','true');inspect(30);assert.equal(readout.hidden,true);svg.setAttribute('data-select-mode','false');
// A data refresh clears a pinned readout rather than carrying old values forward.
touch('pointerdown',10);touch('pointerup',10);hover.update(full);assert.equal(readout.hidden,true);assert.equal(cursor(),undefined);
// Arrow keys move between retained timestamps, Home/End respect the visible window.
hover.update({...full,from:10,to:30});fire('keydown',{key:'Home'});assert.match(readout.textContent,/Cursor 10 s · pinned/);
assert.equal(fire('keydown',{key:'ArrowRight'}).defaultPrevented,true);assert.match(readout.textContent,/Cursor 11 s · pinned/);
fire('keydown',{key:'ArrowLeft'});assert.match(readout.textContent,/Cursor 10 s · pinned/);
fire('keydown',{key:'End'});assert.match(readout.textContent,/Cursor 30 s · pinned/);fire('keydown',{key:'ArrowRight'});assert.match(readout.textContent,/Cursor 30 s · pinned/);
fire('blur');assert.equal(readout.hidden,true);
fire('keydown',{key:'Home',ctrlKey:true});assert.equal(readout.hidden,true);
fire('keydown',{key:'Home'});fire('keydown',{key:'Escape'});assert.equal(readout.hidden,true);
hover.clear();fire('keydown',{key:'Home'});inspect(10);assert.equal(readout.hidden,true);
for(const invalid of [null,{...full,to:0},{...full,to:50},{...full,from:-1},{...full,end:NaN}]){hover.update(invalid);inspect(10);assert.equal(readout.hidden,true);}
// Capture listeners see the drag before the chart's already-registered bubble
// listener releases capture, replaces SVG children, and updates the time window.
const z=harness(({svg,hover,fire})=>{
 svg.addEventListener('pointerup',()=>{fire('lostpointercapture');svg.replaceChildren();hover.update({...full,from:10,to:30});});
});
z.hover.update(full);z.fire('pointermove',{clientX:200});assert.equal(z.readout.hidden,false);
z.fire('pointerdown',{clientX:200});z.fire('pointermove',{clientX:700,buttons:1});assert.equal(z.readout.hidden,true);
z.fire('pointerup',{clientX:700});assert.equal(z.readout.hidden,true);z.fire('pointermove',{clientX:700});assert.equal(z.readout.hidden,true);
z.fire('pointermove',{clientX:701});assert.equal(z.readout.hidden,true);z.fire('pointermove',{clientX:704});assert.equal(z.readout.hidden,false);
// Tiny click redraws, cancellations and redraws mid-drag cannot resurrect values.
z.fire('pointerdown',{clientX:200});z.fire('pointerup',{clientX:202});assert.equal(z.readout.hidden,true);
z.fire('pointerdown',{clientX:200});z.fire('pointermove',{clientX:500,buttons:1});z.hover.update(full);z.fire('pointerup',{clientX:500});assert.equal(z.readout.hidden,true);
z.fire('pointerdown',{clientX:200});z.fire('pointermove',{clientX:600,buttons:1});z.fire('pointercancel',{clientX:600});assert.equal(z.readout.hidden,true);
// Reinitialization removes old listeners and is safe for new chart containers.
const count=svg.listeners.get('pointermove').length;hover.init({svg,readout});assert.equal(svg.listeners.get('pointermove').length,count);
hover.update(full);inspect(10);hover.destroy();assert.equal(readout.hidden,true);assert.equal(svg.listeners.get('pointermove').length,0);assert.equal(cursor(),undefined);
console.log('PASS: chart hover nearest retained values/timestamps, null gaps, zero cadence, independent clocks, shared zoom coordinates, responsive transforms, safe DOM text, touch pin/dismiss/scroll, keyboard inspection, selection redraw/capture ordering, cancellation and stale-data clearing');
