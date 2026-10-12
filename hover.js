/* Shared-time chart inspection. The cursor is a requested time, not an interpolated
 * measurement: every value is taken from its nearest retained row and names that
 * row's own timestamp. Keep missing rows in the search so gaps are never bridged. */
'use strict';
(function (root) {
 const NS='http://www.w3.org/2000/svg', LEFT=65, RIGHT=875, TOP=40, BOTTOM=440, DRAG=8;
 let svg=null,readout=null,doc=null,data=null,cursor=null,gesture=null,pinned=null,activeTime=null,resumePoint=null,listeners=[];
 const finite=v=>typeof v==='number'&&Number.isFinite(v);
 const number=v=>String(Number(v.toFixed(3)));
 function listen(node,type,handler,options){node.addEventListener(type,handler,options);listeners.push([node,type,handler,options]);}
 function hide(){
  if(cursor){cursor.remove();cursor=null;}
  if(readout){readout.hidden=true;readout.replaceChildren();}
  pinned=null;activeTime=null;
 }
 function clear(){data=null;gesture=null;resumePoint=null;hide();}
 function destroy(){for(const [node,type,handler,options]of listeners)node.removeEventListener(type,handler,options);listeners=[];clear();svg=readout=doc=null;}
 function point(event){
  try{
   const matrix=svg.getScreenCTM();if(!matrix)return null;
   const p=svg.createSVGPoint();p.x=event.clientX;p.y=event.clientY;
   const result=p.matrixTransform(matrix.inverse());return finite(result.x)&&finite(result.y)?result:null;
  }catch(_){return null;}
 }
 const inside=p=>p&&p.x>=LEFT&&p.x<=RIGHT&&p.y>=TOP&&p.y<=BOTTOM;
 const selecting=()=>svg.getAttribute('data-select-mode')==='true';
 const elapsed=x=>data.from+(Math.max(LEFT,Math.min(RIGHT,x))-LEFT)/(RIGHT-LEFT)*(data.to-data.from);
 function nearest(rows,time){
  if(!rows.length)return null;
  let lo=0,hi=rows.length;
  while(lo<hi){const mid=(lo+hi)>>>1;if(rows[mid][0]<time)lo=mid+1;else hi=mid;}
  if(lo===0)return rows[0];if(lo===rows.length)return rows[lo-1];
  return time-rows[lo-1][0]<=rows[lo][0]-time?rows[lo-1]:rows[lo];
 }
 function text(tag,value,className){const node=doc.createElement(tag);node.textContent=value;if(className)node.className=className;return node;}
 function inspect(time,mode=null){
  if(!data)return;
  time=Math.max(data.from,Math.min(data.to,time));activeTime=time;pinned=mode;
  const x=LEFT+(time-data.from)/(data.to-data.from)*(RIGHT-LEFT);
  if(!cursor){
   cursor=doc.createElementNS(NS,'line');
   for(const [key,value]of Object.entries({'data-hover-cursor':'true',y1:TOP,y2:BOTTOM,stroke:'#e5edf5','stroke-width':1,'stroke-dasharray':'4 3','pointer-events':'none','aria-hidden':'true'}))cursor.setAttribute(key,value);
   svg.append(cursor);
  }
  cursor.setAttribute('x1',x);cursor.setAttribute('x2',x);
  readout.replaceChildren();
  readout.append(text('strong',`Cursor ${number(time)} s${mode?' · pinned':''}`,'hover-heading'));
  for(const series of data.series){
   const row=nearest(series.rows,time),value=row?.[series.valueIndex],line=doc.createElement('div');line.className='hover-series';
   if(/^#[0-9a-f]{3,8}$/i.test(series.color||'')){
    const swatch=doc.createElementNS(NS,'svg'),dot=doc.createElementNS(NS,'circle');
    for(const [key,value]of Object.entries({class:'hover-swatch',viewBox:'0 0 12 12',width:12,height:12,'aria-hidden':'true',focusable:'false'}))swatch.setAttribute(key,value);
    for(const [key,value]of Object.entries({cx:6,cy:6,r:4,fill:series.color}))dot.setAttribute(key,value);
    swatch.append(dot);line.append(swatch);
   }
   line.append(text('span',`${series.label}: `),text('span',finite(value)?`${number(value)}${series.units?' '+series.units:''}`:'unavailable','hover-value'));
   line.append(text('span',row?` · sample ${String(row[0])} s`:' · no retained samples','hover-sample'));
   readout.append(line);
  }
  readout.append(text('span','Nearest retained samples; no interpolation. '+(mode?'Tap elsewhere or press Escape to dismiss.':'Tap to pin on touch screens.'),'hover-note'));
  readout.hidden=false;
 }
 function pointerDown(event){
  if(event.isPrimary===false){gesture=null;hide();return;}
  if(event.button!==undefined&&event.button!==0)return;
  const p=point(event);hide();
  if(!data||!inside(p)){gesture=null;return;}
  gesture={id:event.pointerId,type:event.pointerType,start:p,last:p,dragged:false,selecting:selecting()};resumePoint=null;
 }
 function pointerMove(event){
  if(event.isPrimary===false)return;
  const p=point(event);
  if(gesture){
   if(event.pointerId!==gesture.id)return;
   if(p){gesture.last=p;if(Math.hypot(p.x-gesture.start.x,p.y-gesture.start.y)>=DRAG)gesture.dragged=true;}
   hide();return;
  }
  if(event.pointerType==='touch'||pinned)return;
  if(!data||!inside(p)||selecting()||event.buttons){hide();return;}
  // Zoom redraws happen inside another pointerup listener. A release at the old
  // coordinate must not immediately show a value from the newly zoomed window.
  if(resumePoint){if(Math.hypot(p.x-resumePoint.x,p.y-resumePoint.y)<2)return;resumePoint=null;}
  inspect(elapsed(p.x));
 }
 function pointerUp(event){
  if(!gesture||event.pointerId!==gesture.id)return;
  const previous=gesture,p=point(event)||previous.last;gesture=null;
  const moved=previous.dragged||Math.hypot(p.x-previous.start.x,p.y-previous.start.y)>=DRAG;
  if(moved||previous.selecting){resumePoint=p;hide();return;}
  if(previous.type==='touch'&&inside(p)&&data&&!selecting())inspect(elapsed(p.x),'touch');
 }
 function pointerCancel(event){
  if(gesture&&event.pointerId===gesture.id){resumePoint=gesture.last;gesture=null;hide();}
 }
 function keyDown(event){
  if(event.key==='Escape'){gesture=null;resumePoint=null;hide();return;}
  if(!data||selecting()||gesture||event.altKey||event.ctrlKey||event.metaKey||!['ArrowLeft','ArrowRight','Home','End'].includes(event.key))return;
  event.preventDefault();
  let time=activeTime??(data.from+data.to)/2;
  if(event.key==='Home')time=data.from;
  else if(event.key==='End')time=data.to;
  else{
   const times=data.times;
   if(event.key==='ArrowRight')time=times.find(t=>t>time)??data.to;
   else{let i=times.length-1;while(i>=0&&times[i]>=time)i--;time=i>=0?times[i]:data.from;}
  }
  inspect(time,'keyboard');
 }
 function init(options){
  if(!options?.svg||!options?.readout)throw new TypeError('ChartHover.init requires svg and readout elements');
  if(svg)destroy();
  svg=options.svg;readout=options.readout;doc=svg.ownerDocument||root.document;
  readout.setAttribute('role','status');readout.setAttribute('aria-live','polite');readout.setAttribute('aria-atomic','true');
  svg.setAttribute('aria-keyshortcuts','ArrowLeft ArrowRight Home End Escape');
  hide();
  // Capture only observes the gesture; the chart owns pointer capture, default
  // prevention, zoom selection and redraw. No listener stops propagation.
  listen(svg,'pointerdown',pointerDown,true);listen(svg,'pointermove',pointerMove,true);listen(svg,'pointerup',pointerUp,true);
  listen(svg,'pointercancel',pointerCancel,true);listen(svg,'lostpointercapture',pointerCancel,true);
  listen(svg,'pointerleave',()=>{if(!pinned&&!gesture)hide();});
  listen(svg,'keydown',keyDown);listen(svg,'blur',()=>{if(pinned==='keyboard')hide();});
  listen(doc,'pointerdown',event=>{if(!svg.contains(event.target)&&!readout.contains(event.target)){gesture=null;resumePoint=null;hide();}},true);
  listen(doc,'keydown',event=>{if(event.key==='Escape'){gesture=null;resumePoint=null;hide();}});
  return root.ChartHover;
 }
 function update(options){
  hide();data=null;
  if(!svg||!options||!finite(options.from)||!finite(options.to)||!finite(options.end)||options.end<=0||options.from<0||options.to<=options.from||options.to>options.end)return;
  const series=(options.series||[]).map(item=>({...item,rows:(item.rows||[]).filter(row=>Array.isArray(row)&&finite(row[0]))}));
  const times=[...new Set(series.flatMap(item=>item.rows.map(row=>row[0])).filter(t=>t>=options.from&&t<=options.to))].sort((a,b)=>a-b);
  data={from:options.from,to:options.to,end:options.end,series,times};
 }
 root.ChartHover=Object.freeze({init,update,clear,destroy});
})(globalThis);
