'use strict';
const $=id=>document.getElementById(id);
const el=(tag,text,cls)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n;};
const number=v=>typeof v==='number'&&Number.isFinite(v)?v.toFixed(2):'n/a';
const safeId=s=>typeof s==='string'&&/^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,100}$/.test(s);
const decision=(v,relative=false)=>v===true?'PASS':v===false?(relative?'REGRESSION':'OUTSIDE BAND'):'UNAVAILABLE';
const desiredSeed='7';
let current, history, serial=0, desiredScenario=null, desiredDuration=null, desiredTable=null, desiredSensitivity=null, shortScenario=null;
ChartHover.init({svg:$('chart'),readout:$('chart-readout')});
function runDate(md){const value=md.run_completed_at||md.imported_at;if(!value||!Number.isFinite(Date.parse(value)))return 'time not recorded';return new Intl.DateTimeFormat('en-US',{timeZone:'Etc/GMT+5',year:'numeric',month:'short',day:'numeric',hour:'2-digit',minute:'2-digit',second:'2-digit',hour12:false}).format(new Date(value))+' UTC−05:00';}
const initialState=s=>({empty:'empty starting table',partial:'partially learned TESTED RANGE',full:'fully learned TESTED RANGE'})[s]||'starting state not recorded';
function rideLabel(minutes,state){return `${[30,60,90].includes(minutes)?minutes+' min':'duration not recorded'} · ${initialState(state)}`;}
function runName(r){return `${runDate(r.metadata)} · ${(r.candidate_commit||'revision not recorded').slice(0,12)} · ${r.id}`;}
// A branch is a navigation group, never a claim that its snapshots are equivalent.
function firmwareKey(r){return r.metadata.release_tag?'release:'+r.metadata.release_tag:r.display_ref&&r.display_ref!=='Unrecorded ref'&&!r.display_ref.startsWith('commit ')?'branch:'+r.display_ref:'commit:'+(r.candidate_commit||r.id);}
function firmwareName(r){return r.metadata.release_tag?`${r.metadata.release_tag} · release${r.metadata.release_published_at?' · '+r.metadata.release_published_at.slice(0,10):''}`:r.display_ref||r.candidate_commit||'Unrecorded firmware';}
const sprintExperiment='continuous-long-ride-sprints-v2';
const isLongExperiment=experiment=>['continuous-long-ride-v1',sprintExperiment].includes(experiment);
const isLongType=type=>['long','long-sprints'].includes(type);
const testTypes=[['short','Short scenario tests'],['long-sprints','Long rides + 500 W sprints (v2)'],['long','Long rides without sprints (v1 archive)']];
const testType=r=>r.metadata.experiment===sprintExperiment?'long-sprints':r.metadata.experiment==='continuous-long-ride-v1'?'long':'short';
const selectionRows=r=>(r.selections||[]).filter(x=>String(x.seed)===desiredSeed);
function matchesLongFilters(r){return r.metadata.initial_state===desiredTable&&(testType(r)==='long-sprints'?r.metadata.experiment_duration_min===90&&String(r.metadata.sensitivity)===desiredSensitivity:String(r.metadata.experiment_duration_min)===desiredDuration);}
function selectedRuns(){return history.filter(r=>selectionRows(r).length&&firmwareKey(r)===$('firmware').value&&testType(r)===$('test-type').value&&(!isLongType($('test-type').value)||matchesLongFilters(r)));}
function updateSelectors(preferredId){
 const type=$('test-type').value;options($('test-type'),testTypes.map(([v,t])=>[v,t+(history.some(r=>firmwareKey(r)===$('firmware').value&&testType(r)===v&&selectionRows(r).length)?'':' (unavailable)')]),type);
 const long=isLongType(type),sprints=type==='long-sprints';$('duration-filter').hidden=type!=='long';$('sensitivity-filter').hidden=!sprints;$('table-filter').hidden=!long;
 const family=history.filter(r=>testType(r)===$('test-type').value),group=family.filter(r=>firmwareKey(r)===$('firmware').value&&selectionRows(r).length);
 const durations=[...new Set(family.map(r=>String(r.metadata.experiment_duration_min)))].filter(x=>x!=='undefined').sort((a,b)=>Number(a)-Number(b));
 if(!desiredDuration)desiredDuration=durations[0]||'30';if(!desiredTable||sprints&&desiredTable==='partial')desiredTable='empty';if(!desiredSensitivity)desiredSensitivity='3';
 options($('duration'),durations.map(v=>[v,`${v} min${group.some(r=>String(r.metadata.experiment_duration_min)===v)?'':' (unavailable)'}`]),desiredDuration);
 options($('sensitivity'),['3','5','10'].map(v=>[v,`${v}${group.some(r=>String(r.metadata.sensitivity)===v&&r.metadata.initial_state===desiredTable)?'':' (unavailable)'}`]),desiredSensitivity);
 options($('table'),(sprints?['empty','full']:['empty','partial','full']).map(v=>[v,initialState(v)+(group.some(r=>r.metadata.initial_state===v&&(sprints?String(r.metadata.sensitivity)===desiredSensitivity:String(r.metadata.experiment_duration_min)===desiredDuration))?'':' (unavailable)')]),desiredTable);
 const names=[...new Set(family.flatMap(r=>selectionRows(r).map(x=>x.scenario)))];
 if(!desiredScenario)desiredScenario=names[0]|| (long?'long_ride':'');
 if(desiredScenario&&!names.includes(desiredScenario))names.unshift(desiredScenario);
 const matches=selectedRuns(),chosen=matches.find(r=>r.id===preferredId)||matches.find(r=>selectionRows(r).some(x=>x.scenario===desiredScenario&&String(x.seed)===desiredSeed))||matches[0],available=chosen?selectionRows(chosen):[];
 options($('scenario'),names.map(v=>[v,v+(available.some(x=>x.scenario===v)?'':' (unavailable)')]),desiredScenario);
 // Keep a chosen snapshot within a test; switching firmware selects its newest
 // matching experiment, visibly naming its exact revision rather than substituting it.
 options($('history'),matches.length?matches.map(r=>[r.id,runName(r)]):[['','No recorded experiment for this combination']],chosen?.id);
 $('history').disabled=!matches.length;$('scenario').disabled=false;
 return matches.length>0;
}
async function choose(preferredId){
 if(updateSelectors(preferredId))return load();
 ++serial;current=null;clearRun();clearChartZoom(true);$('scenario').disabled=false;
 $('notice').textContent='UNAVAILABLE: No recorded '+($('test-type').value==='long-sprints'?`90-minute sprint ride with ${initialState(desiredTable)} and ERG sensitivity ${desiredSensitivity}`:isLongType($('test-type').value)?`${desiredDuration}-minute long ride with ${initialState(desiredTable)}`:'short scenario test')+' for this firmware at seed 7. Seed 7 is used for every displayed test. Your scenario selection is kept. Choose another test or firmware; no previous chart or baseline-only result is shown.';
 $('chart-label').textContent='Selected test unavailable';location.hash='';
}
function options(node,items,value){node.replaceChildren();for(const [v,t]of items){const o=el('option',t);o.value=v;node.append(o);}if(value&&items.some(x=>x[0]===value))node.value=value;}
function card(label,value,note,ok){const d=el('div',undefined,'card');d.append(el('span',label),el('strong',value,ok===true?'good':ok===false?'bad':''),el('span',note));return d;}
function combinedDecision(checks,key){const values=checks.map(check=>check?.[key]);return values.includes(false)?false:values.every(value=>value===true)?true:null;}
function pairDecision(row,key){return combinedDecision([row,row?.reported_power_comparison],key);}
function both(row,key){
 const checks=[row,row.reported_power_comparison];if(row.overall_checks)checks.push(row.overall_checks);
 if(row.scenario==='long_ride'&&isLongExperiment(current?.comparison?.experiment)){
  for(const field of ['window_comparisons',...(current.comparison.experiment===sprintExperiment?['sprint_comparisons']:[])])for(const name of ['early','middle','late'])checks.push(row[field]?.[name],row[field]?.[name]?.reported_power_comparison);
 }
 return combinedDecision(checks,key);
}
function line(label,value){$('provenance').append(el('dt',label),el('dd',String(value??'Not recorded')));}
function link(text,path){const a=el('a',text);a.href=path;return a;}
// One shared elapsed-time window for every series; y axes stay stable while zooming.
let zoomWindow=null,chartEnd=0,chartRow=null,selection=null,selectMode=false;
const zoomIds=['zoom-in','zoom-out','zoom-reset','zoom-earlier','zoom-later','zoom-select'];
const formatTime=t=>Number(t.toFixed(1)).toString();
function clampWindow(range,end){
 const span=Math.min(end,Math.max(Math.min(1,end),Math.abs(range[1]-range[0])));
 const from=Math.max(0,Math.min(Math.min(...range),end-span));
 return span>=end?null:[from,from+span];
}
function windowRows(rows,from,to){
 // Keep neighboring samples for line intersections at the clip edges; no new data is inferred.
 let first=rows.findIndex(r=>r[0]>=from);if(first<0)first=rows.length;
 let last=rows.findIndex(r=>r[0]>to);if(last<0)last=rows.length;
 return rows.slice(Math.max(0,first-1),Math.min(rows.length,last+1));
}
function updateZoomControls(){
 const ready=chartEnd>0,range=zoomWindow||[0,chartEnd],span=range[1]-range[0];
 for(const id of zoomIds)$(id).disabled=!ready;
 $('zoom-in').disabled=!ready||span<=Math.min(1,chartEnd);
 for(const id of ['zoom-out','zoom-reset'])$(id).disabled=!ready||!zoomWindow;
 $('zoom-earlier').disabled=!ready||!zoomWindow||range[0]<=0;
 $('zoom-later').disabled=!ready||!zoomWindow||range[1]>=chartEnd;
 $('zoom-select').setAttribute('aria-pressed',String(selectMode));
 $('chart').setAttribute('data-select-mode',String(selectMode));
 $('zoom-select').textContent=selectMode?'Cancel selection':'Select area';
 $('zoom-range').textContent=ready?`${zoomWindow?'Showing':'Full ride'}: ${formatTime(range[0])}–${formatTime(range[1])} s of ${formatTime(chartEnd)} s`:'Zoom unavailable';
}
function cancelSelection(){
 if(selection){const id=selection.id;selection.rect.remove();selection=null;if($('chart').hasPointerCapture?.(id))$('chart').releasePointerCapture(id);}
}
function clearChartZoom(reset=false){ChartHover.clear();cancelSelection();chartRow=null;chartEnd=0;selectMode=false;if(reset)zoomWindow=null;updateZoomControls();}
function changeZoom(factor,shift=0){
 if(!chartRow||!chartEnd)return;const [a,b]=zoomWindow||[0,chartEnd],span=(b-a)*factor,center=(a+b)/2+(b-a)*shift;
 zoomWindow=clampWindow([center-span/2,center+span/2],chartEnd);draw(chartRow);
}
function plotPoint(event){
 const point=$('chart').createSVGPoint();point.x=event.clientX;point.y=event.clientY;
 return point.matrixTransform($('chart').getScreenCTM().inverse());
}
function selectionEnd(event,cancel=false){
 if(!selection||event.pointerId!==selection.id)return;
 const {start,last,range}=selection;cancelSelection();
 if(!cancel&&Math.abs(last-start)>=8){const time=x=>range[0]+(x-65)/810*(range[1]-range[0]);zoomWindow=clampWindow([time(start),time(last)],chartEnd);}
 selectMode=false;updateZoomControls();if(chartRow)draw(chartRow);
}
$('chart').addEventListener('pointerdown',event=>{
 if(!chartRow||!chartEnd||event.isPrimary===false||event.button!==0||event.pointerType==='touch'&&!selectMode)return;
 if(selection)return;const point=plotPoint(event);if(point.x<65||point.x>875||point.y<40||point.y>440)return;
 event.preventDefault();const rect=document.createElementNS('http://www.w3.org/2000/svg','rect');
 for(const[k,v]of Object.entries({x:point.x,y:40,width:0,height:400,fill:'#58dec833',stroke:'#58dec8','pointer-events':'none'}))rect.setAttribute(k,v);
 $('chart').append(rect);selection={id:event.pointerId,start:point.x,last:point.x,range:zoomWindow||[0,chartEnd],rect};$('chart').setPointerCapture(event.pointerId);
});
$('chart').addEventListener('pointermove',event=>{
 if(!selection||event.pointerId!==selection.id)return;event.preventDefault();selection.last=Math.max(65,Math.min(875,plotPoint(event).x));
 selection.rect.setAttribute('x',Math.min(selection.start,selection.last));selection.rect.setAttribute('width',Math.abs(selection.last-selection.start));
});
$('chart').addEventListener('pointerup',event=>selectionEnd(event));
$('chart').addEventListener('pointercancel',event=>selectionEnd(event,true));
$('chart').addEventListener('lostpointercapture',event=>selectionEnd(event,true));
document.addEventListener('keydown',event=>{if(event.key==='Escape'){cancelSelection();selectMode=false;updateZoomControls();}});
$('zoom-select').addEventListener('click',()=>{cancelSelection();selectMode=!selectMode;updateZoomControls();});
$('zoom-in').addEventListener('click',()=>changeZoom(.5));
$('zoom-out').addEventListener('click',()=>changeZoom(2));
$('zoom-earlier').addEventListener('click',()=>changeZoom(1,-.5));
$('zoom-later').addEventListener('click',()=>changeZoom(1,.5));
$('zoom-reset').addEventListener('click',()=>{zoomWindow=null;if(chartRow)draw(chartRow);});

function draw(row){
cancelSelection();const svg=$('chart');svg.replaceChildren();chartRow=row;const ns='http://www.w3.org/2000/svg';
const add=(tag,attrs,text)=>{const n=document.createElementNS(ns,tag);for(const[k,v]of Object.entries(attrs))n.setAttribute(k,v);if(text)n.textContent=text;svg.append(n);};
const key=`${row.scenario}-${row.seed}`,artifactKey=safeId(row.artifact_key)?row.artifact_key:key,traces=current.traces?.[key]||current.traces?.[artifactKey]||{};
const c=traces.candidate||[],b=traces.baseline||[],motor=current.motor?.traces?.[key]||current.motor?.traces?.[artifactKey]||[];
const cadence=current.cadence?.traces?.[key]||current.cadence?.traces?.[artifactKey]||[];
const validCadence=cadence.filter(r=>r.slice(1,3).some(v=>typeof v==='number'&&Number.isFinite(v)));
$('cadence-note').textContent=validCadence.length?'Violet: candidate modeled rider cadence (cadence_rpm), recorded in RPM. Missing samples are gaps. '+(cadence.some(r=>typeof r[2]==='number'&&Number.isFinite(r[2]))?'Dashed lavender: recorded firmware-received cadence.':'Firmware-received cadence is not available as a complete recorded time series and is not inferred.'):'Cadence unavailable for this run / scenario / seed; no RPM values are inferred.';
const validMotor=motor.filter(r=>typeof r[1]==='number'&&Number.isFinite(r[1]));
$('motor-note').textContent=validMotor.length?'Red: candidate simulated actual motor position (motor_steps), right axis in steps. This is the virtual motor counter; commanded target and physical bike position are separate signals.'+(validMotor.length<motor.length?' Missing position samples are shown as gaps.':''):'Actual motor position unavailable for this run / scenario / seed; no position values are inferred.';
if(!c.length&&!b.length){add('text',{x:65,y:140},'No power trace available for this run.');if(!validMotor.length&&!validCadence.length){clearChartZoom(true);return;}}
const all=[...c,...b],end=Math.max(...all.map(r=>r[0]),...motor.map(r=>r[0]),...cadence.map(r=>r[0]),1);
// Watts and steps have independent scales. Motor values must never inflate watts.
const top=Math.ceil(Math.max(...all.flatMap(r=>r.slice(1,4)),100)/100)*100;
chartEnd=end;zoomWindow=zoomWindow?clampWindow(zoomWindow,end):null;updateZoomControls();
const [from,to]=zoomWindow||[0,end];
const left=65,right=875,x=t=>left+(t-from)/(to-from)*(right-left),y=w=>280-w/top*240;
const defs=document.createElementNS(ns,'defs'),clip=document.createElementNS(ns,'clipPath'),rect=document.createElementNS(ns,'rect');clip.setAttribute('id','plot-clip');for(const[k,v]of Object.entries({x:left,y:40,width:right-left,height:240}))rect.setAttribute(k,v);clip.append(rect);defs.append(clip);svg.append(defs);
for(let i=0;i<=4;i++){const w=top*i/4;add('line',{x1:left,x2:right,y1:y(w),y2:y(w),stroke:'#304255'});add('text',{x:10,y:y(w)+4},`${w} W`);const t=from+(to-from)*i/4;add('text',{x:x(t)-10,y:306},`${formatTime(t)}s`);}
for(const[rows,col,color]of [[c.length?c:b,1,'#b2c1cc'],[b,2,'#639de8'],[c,2,'#58dec8'],[c,3,'#f5c16c']]){if(!rows.length)continue;add('polyline',{'clip-path':'url(#plot-clip)',points:windowRows(rows,from,to).map(r=>`${x(r[0]).toFixed(2)},${y(r[col]).toFixed(2)}`).join(' '),fill:'none',stroke:color,'stroke-width':col===3?1:1.6,opacity:col===3?.6:1});}
if(validMotor.length){
const values=validMotor.map(r=>r[1]),lo=Math.min(...values),hi=Math.max(...values),pad=Math.max((hi-lo)*.08,1);
const bottom=Math.floor(lo-pad),topStep=Math.ceil(hi+pad),ym=p=>280-(p-bottom)/(topStep-bottom)*240;
add('line',{x1:right,x2:right,y1:40,y2:280,stroke:'#ff646b'});add('text',{x:right+10,y:22,class:'motor-axis'},'Motor (steps)');
for(let i=0;i<=4;i++){const p=bottom+(topStep-bottom)*i/4;add('text',{x:right+10,y:ym(p)+4,class:'motor-axis'},String(Math.round(p)));}
let segment=[];const flush=()=>{if(segment.length===1)add('circle',{'clip-path':'url(#plot-clip)',cx:x(segment[0][0]),cy:ym(segment[0][1]),r:2,fill:'#ff646b','data-series':'actual-motor'});else if(segment.length)add('polyline',{'clip-path':'url(#plot-clip)',points:windowRows(segment,from,to).map(r=>`${x(r[0]).toFixed(2)},${ym(r[1]).toFixed(2)}`).join(' '),fill:'none',stroke:'#ff646b','stroke-width':1.8,'data-series':'actual-motor'});segment=[];};
for(const r of motor){if(typeof r[1]==='number'&&Number.isFinite(r[1]))segment.push(r);else flush();}flush();
}
// A separate RPM panel shares x coordinates and the exact same selected window.
const cadenceTop=Math.max(120,Math.ceil(Math.max(0,...validCadence.flatMap(r=>r.slice(1,3).filter(Number.isFinite)))/20)*20),yc=rpm=>440-rpm/cadenceTop*90;
const cadenceClip=document.createElementNS(ns,'clipPath'),cadenceRect=document.createElementNS(ns,'rect');cadenceClip.setAttribute('id','cadence-clip');for(const[k,v]of Object.entries({x:left,y:350,width:right-left,height:90}))cadenceRect.setAttribute(k,v);cadenceClip.append(cadenceRect);defs.append(cadenceClip);
add('text',{x:left,y:334,class:'cadence-axis'},'Cadence (RPM) · candidate');
for(let i=0;i<=2;i++){const rpm=cadenceTop*i/2;add('line',{x1:left,x2:right,y1:yc(rpm),y2:yc(rpm),stroke:'#304255'});add('text',{x:15,y:yc(rpm)+4,class:'cadence-axis'},String(rpm));}
for(let i=0;i<=4;i++){const t=from+(to-from)*i/4;add('text',{x:x(t)-10,y:466},`${formatTime(t)}s`);}
if(!validCadence.length)add('text',{x:left+12,y:400},'Cadence not recorded');
for(const [col,color,name,dash]of [[1,'#ba91ff','modeled-cadence',''],[2,'#ead5ff','received-cadence','6 4']]){
 let segment=[];const flush=()=>{if(segment.length===1)add('circle',{'clip-path':'url(#cadence-clip)',cx:x(segment[0][0]),cy:yc(segment[0][col]),r:2,fill:color,'data-series':name});else if(segment.length)add('polyline',{'clip-path':'url(#cadence-clip)',points:windowRows(segment,from,to).map(r=>`${x(r[0]).toFixed(2)},${yc(r[col]).toFixed(2)}`).join(' '),fill:'none',stroke:color,'stroke-width':2,'stroke-dasharray':dash,'data-series':name});segment=[];};
 for(const r of cadence){if(typeof r[col]==='number'&&Number.isFinite(r[col]))segment.push(r);else flush();}flush();
}
add('rect',{x:65,y:40,width:810,height:400,fill:'transparent','data-plot-hit':'true'});
ChartHover.update({from,to,end,series:[
 {label:'Target power',units:'W',rows:c.length?c:b,valueIndex:1,color:'#b2c1cc'},
 {label:'Candidate plant power',units:'W',rows:c,valueIndex:2,color:'#58dec8'},
 {label:'Baseline plant power',units:'W',rows:b,valueIndex:2,color:'#639de8'},
 {label:'Candidate delivered power',units:'W',rows:c,valueIndex:3,color:'#f5c16c'},
 {label:'Candidate actual motor',units:'steps',rows:motor,valueIndex:1,color:'#ff646b'},
 {label:'Candidate modeled rider cadence',units:'RPM',rows:cadence,valueIndex:1,color:'#ba91ff'},
 {label:'Candidate firmware-received cadence',units:'RPM',rows:cadence,valueIndex:2,color:'#ead5ff'}
]});
}

function testedCoverage(c){return Number.isInteger(c?.tested_range_required)&&c.tested_range_required>0&&Number.isInteger(c.tested_range_supported)&&c.tested_range_supported>=0&&c.tested_range_supported<=c.tested_range_required?`${c.tested_range_supported} / ${c.tested_range_required} tested cells`:'Tested-range coverage unavailable';}
function gridDescription(c){
const cells=Array.isArray(c?.tested_range_cells)?c.tested_range_cells:[],watts=[...new Set(cells.map(x=>x?.watts).filter(Number.isFinite))].sort((a,b)=>a-b),cadences=[...new Set(cells.map(x=>x?.cadence_rpm).filter(Number.isFinite))].sort((a,b)=>a-b);
if(!watts.length||!cadences.length)return 'Tested-grid coordinates unavailable; coverage counts use the recorded tested-range requirement.';
return `Recorded tested grid: ${watts.join(', ')} W × ${cadences.join(', ')} rpm.`+(cadences[0]===75&&cadences[cadences.length-1]===95?' The padded 75–95 rpm grid covers simulated cadence drift around the 80–90 rpm operational cues.':'');
}
function tableHead(node,labels){const tr=el('tr');for(const label of labels)tr.append(el('th',label));node.append(tr);}
function tableRow(node,values){const tr=el('tr');for(const value of values)tr.append(el('td',value));node.append(tr);}
function clearLearning(){for(const id of ['learning-label','learning-coverage','learning-metrics','learning-events','learning-evidence','learning-status','learning-hashes','learning-decisions','learning-grid'])$(id).replaceChildren();$('learning').hidden=true;}
function renderLearning(row){
clearLearning();if(!row||!isLongExperiment(current.comparison.experiment)||row.scenario!=='long_ride')return;
$('learning-grid').textContent=gridDescription(row.metadata?.candidate?.initial_coverage||row.metadata?.baseline?.initial_coverage);
$('learning').hidden=false;$('learning-scope').textContent='These repeated-probe comparisons are descriptive. They do not establish that learning causes an improvement. The main score table and its decision detail cover the whole ride. The summary absolute and relative cards require the whole ride, every probe'+(current.comparison.experiment===sprintExperiment?' and all three sprint blocks':'')+' to pass, for both plant and delivered sensor.';$('learning-label').textContent=rideLabel(row.minutes??current.metadata.experiment_duration_min,row.initial_state??current.metadata.initial_state);
for(const [variant,label]of [['baseline','Baseline'],['candidate','Candidate']]){const md=row.metadata?.[variant];$('learning-coverage').append(card(`${label.toUpperCase()} · START → FINISH`,`${testedCoverage(md?.initial_coverage)} → ${testedCoverage(md?.final_coverage)}`,"Measured support on this run’s tested grid; no full-table coverage claim."));}
tableHead($('learning-metrics'),['Probe / elapsed time','Firmware','Signal','MAE (W)','P95 error (W)','Worst settling (s)','Unsettled steps']);
tableHead($('learning-hashes'),['Snapshot','Firmware','Table SHA-256']);
for(const [variant,label]of [['baseline','Baseline'],['candidate','Candidate']])tableRow($('learning-hashes'),['Ride start',label,row.metadata?.[variant]?.initial_table_sha256||'Not recorded']);
tableHead($('learning-events'),['Probe','Firmware','Starting support','Table-seek time (s)','Learning observations','Insertion attempts','Table gain logs (sampled)','Fallback gain logs (sampled)']);
let present=0;
for(const name of ['early','middle','late'])for(const [variant,label]of [['baseline','Baseline'],['candidate','Candidate']]){
const windows=row.scores?.[variant]?.windows,win=Array.isArray(windows)?windows.find(w=>w?.name===name):null;
if(!win)continue;present++;tableRow($('learning-hashes'),[name,label,win.table_sha256||'Not recorded']);
const elapsed=Number.isFinite(win.start_s)&&Number.isFinite(win.duration_s)?`${number(win.start_s/60)}–${number((win.start_s+win.duration_s)/60)} min`:'time unavailable';
for(const [signal,metrics]of [['Plant',win.metrics],['Delivered sensor',win.delivered_sensor_metrics]])tableRow($('learning-metrics'),[`${name} · ${elapsed}`,label,signal,...['mae_w','p95_error_w','worst_settling_s','unsettled_steps'].map(k=>number(metrics?.[k]))]);
const count=kind=>win.events&&typeof win.events==='object'&&!Array.isArray(win.events)?number(win.events[kind]??0):'n/a';
tableRow($('learning-events'),[name,label,testedCoverage(win.starting_table),number(win.seeking_seconds),count('learning_observation'),count('table_insert_attempt'),count('table_gain_log'),count('fallback_gain_log')]);
}
for(const name of ['early','middle','late']){
const comparison=row.window_comparisons?.[name];
for(const [label,score]of [['Plant',comparison],['Delivered sensor',comparison?.reported_power_comparison]]){
$('learning-decisions').append(el('p',`${name} · ${label}: absolute ${decision(score?.absolute_passed)} · relative ${decision(score?.relative_passed,true)}`));
const ul=el('ul');for(const failure of (score?.failures||[]).filter(f=>label!=='Plant'||!f.startsWith('delivered sensor: ')))ul.append(el('li',failure,'bad'));$('learning-decisions').append(ul);
}
}
$('learning-status').textContent=present===6?'Identical six-minute early, middle and late probes are shown below.':`${present} / 6 firmware / probe summaries available. Missing window evidence is not inferred.`;
const training=current.metadata.training_run_id;
if(safeId(training))$('learning-evidence').append(link('Shared production-learning training evidence ZIP',`runs/${training}/evidence.zip`));
else $('learning-evidence').append(el('span','Shared training evidence link unavailable.'));
}

function clearSprints(){for(const id of ['sprint-label','sprint-status','sprint-summary','sprint-zoom','sprint-metrics','sprint-decisions','sprint-hashes'])$(id).replaceChildren();$('sprints').hidden=true;}
function sprintResponse(response,key){
 if(response?.[key]===null){if(key==='rise_to_450w_s')return 'Not reached in 25 s';if(key==='sprint_settling_s')return 'Not settled in 25 s';if(key==='recovery_settling_s')return 'Not settled in 30 s';}
 return typeof response?.[key]==='number'&&Number.isFinite(response[key])?number(response[key]):'Unavailable';
}
function renderSprints(row){
 clearSprints();if(!row||current.comparison.experiment!==sprintExperiment||row.scenario!=='long_ride')return;
 $('sprints').hidden=false;$('sprint-label').textContent=`90 min · ${initialState(row.initial_state??current.metadata.initial_state)} · ERG sensitivity ${row.sensitivity??current.metadata.sensitivity??'unrecorded'}`;
 tableHead($('sprint-metrics'),['Sprint / elapsed block','Firmware','Signal','Rise to 450 W (s)','Settle at 500 W (s)','Peak (W)','Overshoot (W)','Above 520 W (s)','Outside ±20 W (s)','Recovery settle (s)','Recovery peak (W)','Recovery above 120 W (s)']);
 tableHead($('sprint-hashes'),['Sprint','Firmware','Starting tested-grid support','Table SHA-256']);
 const sprint=(variant,name)=>{const values=row.scores?.[variant]?.sprints;return Array.isArray(values)?values.find(value=>value?.name===name):null;};
 const responseKeys=['rise_to_450w_s','sprint_settling_s','peak_power_w','peak_overshoot_w','above_520w_s','outside_20w_s','recovery_settling_s','recovery_peak_power_w','recovery_above_120w_s'];
 let present=0;
 for(const name of ['early','middle','late']){
  const comparison=row.sprint_comparisons?.[name],abs=pairDecision(comparison,'absolute_passed'),rel=pairDecision(comparison,'relative_passed');
  $('sprint-summary').append(card(name.toUpperCase()+' SPRINT BLOCK',`Absolute ${decision(abs)}`,`Relative ${decision(rel,true)} · both signals`,abs===false||rel===false?false:abs===true&&rel===true?true:null));
  const interval=sprint('candidate',name)||sprint('baseline',name),button=el('button',`Zoom to ${name} sprint`);button.type='button';
  button.disabled=!Number.isFinite(interval?.start_s)||!Number.isFinite(interval?.duration_s)||interval.duration_s<=0;
  button.addEventListener('click',()=>{if(button.disabled||chartRow!==row||!chartEnd)return;zoomWindow=clampWindow([interval.start_s,interval.start_s+interval.duration_s],chartEnd);selectMode=false;draw(row);});$('sprint-zoom').append(button);
  for(const [variant,label]of [['baseline','Baseline'],['candidate','Candidate']]){
   const block=sprint(variant,name);if(block)present++;
   const elapsed=Number.isFinite(block?.start_s)&&Number.isFinite(block?.duration_s)?`${number(block.start_s/60)}–${number((block.start_s+block.duration_s)/60)} min`:'time unavailable';
   for(const [signal,response]of [['Plant',block?.response],['Delivered sensor',block?.delivered_sensor_response]])tableRow($('sprint-metrics'),[`${name} · ${elapsed}`,label,signal,...responseKeys.map(key=>sprintResponse(response,key))]);
   tableRow($('sprint-hashes'),[name,label,testedCoverage(block?.starting_table),block?.table_sha256||'Not recorded']);
  }
  for(const [signal,score]of [['Plant',comparison],['Delivered sensor',comparison?.reported_power_comparison]]){
   $('sprint-decisions').append(el('p',`${name} · ${signal}: absolute ${decision(score?.absolute_passed)} · relative ${decision(score?.relative_passed,true)}`));
   const ul=el('ul');for(const failure of (score?.failures||[]).filter(f=>signal!=='Plant'||!f.startsWith('delivered sensor: ')))ul.append(el('li',failure,'bad'));$('sprint-decisions').append(ul);
  }
 }
 $('sprint-status').textContent=present===6?'All three sprint blocks are reported separately for both firmware revisions. Whole-ride averages cannot replace these phase-specific measurements.':`${present} / 6 firmware / sprint summaries available. Missing sprint evidence is not inferred.`;
}

function selectFilters(rows){return rows.find(r=>r.scenario===desiredScenario&&String(r.seed)===desiredSeed);}
function render(){const m=current.comparison;const longRide=isLongExperiment(m.experiment),withSprints=m.experiment===sprintExperiment;const checkScope=withSprints?'Whole ride + every probe + all 3 sprints':'Whole ride + every probe';const rows=(m.runs||[]).filter(r=>String(r.seed)===desiredSeed);const row=selectFilters(rows);const abs=rows.filter(r=>both(r,'absolute_passed')===true).length,rel=rows.filter(r=>both(r,'relative_passed')===true).length;$('overview').replaceChildren(card('EXPERIMENT STATUS',m.status,`${rows.length} recorded scenarios · seed 7`,m.status==='complete'),card('ABSOLUTE BANDS',`${abs} / ${rows.length}`,longRide?checkScope+'; both signals':'Plant AND delivered sensor',rows.length?abs===rows.length:null),card('RELATIVE REGRESSION',`${rel} / ${rows.length}`,longRide?checkScope+' vs pinned baseline':'Versus pinned baseline',rows.length?rel===rows.length:null),card('MODEL',String(m.profile_sha256||'Unavailable').slice(0,12),'SHA-256 · fitted bike profile'));
$('notice').textContent=m.status==='complete'?`${m.budget_status||'Provisional engineering budgets'}. ${rows.length-abs} pairs outside one or more absolute bands. This is a model result, not a hardware pass.`:`${m.status.toUpperCase()}: ${m.error||current.metadata.reason||'No complete result available.'}`;
$('notice').textContent+=` Tested candidate: ${(m.firmware?.candidate?.commit||history.find(r=>r.id===current.id)?.candidate_commit||'revision not recorded').slice(0,12)}. Branch snapshots can differ between tests.`;
$('metrics').replaceChildren();$('decisions').replaceChildren();renderLearning(row);renderSprints(row);if(row){$('chart-label').textContent=`${row.scenario} / seed ${row.seed}`+(withSprints?` / 90 min / ERG sensitivity ${row.sensitivity??current.metadata.sensitivity}`:'');draw(row);const head=el('tr');for(const t of ['Signal / metric','Baseline','Candidate','Delta','Relative allowance'])head.append(el('th',t));$('metrics').append(head);for(const [signal,sub] of [['Plant',null],['Delivered sensor','delivered_sensor_metrics']]){const base=sub?row.scores?.baseline?.[sub]:row.scores?.baseline,cand=sub?row.scores?.candidate?.[sub]:row.scores?.candidate,changes=sub?row.reported_power_comparison?.changes:row.changes;for(const metric of ['mae_w','p95_error_w','overshoot_w','undershoot_w','outside_band_percent','steady_rmse_w','steady_variation_w_per_s','unsettled_steps','worst_settling_s']){const tr=el('tr');for(const t of [`${signal} · ${metric.replaceAll('_',' ')}`,number(base?.[metric]),number(cand?.[metric]),number(changes?.[metric]?.delta),number(changes?.[metric]?.allowance)])tr.append(el('td',t));$('metrics').append(tr);}}
for(const [label,score] of [['Plant',row],['Delivered sensor',row.reported_power_comparison]]){const p=el('p',`${longRide?'Whole ride · ':''}${label}: absolute ${decision(score?.absolute_passed)} · relative ${decision(score?.relative_passed,true)}`);$('decisions').append(p);const ul=el('ul');for(const f of (score?.failures||[]).filter(f=>label!=='Plant'||!f.startsWith('delivered sensor: ')))ul.append(el('li',f,'bad'));$('decisions').append(ul);}}else{clearChartZoom(true);$('chart').replaceChildren();$('motor-note').textContent='';$('cadence-note').textContent='';$('chart-label').textContent='Selected scenario / seed unavailable';const explanation=`${desiredScenario||'No scenario'} / seed ${desiredSeed||'not selected'} is unavailable in this run. Your selection is kept; switch back or choose an available combination.`;$('notice').textContent+=' '+explanation;$('decisions').append(el('p',explanation));}
$('provenance').replaceChildren();const md=current.metadata;line('Tested firmware ref',history.find(r=>r.id===current.id)?.display_ref||md.candidate_ref||md.release_tag||'Not recorded');line('Run ID',current.id);line('Experiment version',m.experiment||'Short scenario suite');if(longRide)line('Shared training run ID',md.training_run_id);if(withSprints){line('Ride duration',`${md.experiment_duration_min} minutes`);line('ERG sensitivity',row?.sensitivity??md.sensitivity);}line('Displayed simulation seed',7);line('Evidence scope','Charts and summary cards use seed 7 only. Original downloads may also contain archived runs with other seeds.');line('Experiment completed (UTC)',md.run_completed_at||'Not recorded');line('Evidence imported (UTC)',md.imported_at);line('Candidate release',md.release_tag||'Development commit');line('Release published (UTC)',md.release_published_at||'Not a release / not recorded');line('Baseline release',md.baseline_release_tag);line('Baseline release published',md.baseline_release_published_at);line('Candidate commit',m.firmware?.candidate?.commit);line('Baseline commit',m.firmware?.baseline?.commit);line('Adapter commit',md.adapter_commit);line('Adapter SHA-256',m.adapter?.sha256);line('Adapter patch SHA-256',md.adapter_patch_sha256||'No compatibility patch');line('Simulator commit',md.simulator_commit);line('Simulator source SHA-256',m.simulator_sha256);line('Profile SHA-256',m.profile_sha256);line('Package config SHA-256',m.package_config_sha256);line('Candidate source SHA-256',m.firmware?.candidate?.source_sha256);line('Baseline source SHA-256',m.firmware?.baseline?.source_sha256);line('Source dirty flags',JSON.stringify(Object.fromEntries(Object.entries(m.firmware||{}).map(([k,v])=>[k,v.dirty]))));line('Coverage',m.coverage_level);line('Runtime toolchain',JSON.stringify(md.runtime_toolchain||'Not recorded; adapter-provenance toolchain, if present, describes original local validation only'));line('Provenance notes',md.notes);
$('downloads').replaceChildren(link('Full raw evidence ZIP',`runs/${current.id}/evidence.zip`),link('Comparison JSON',`runs/${current.id}/comparison.json`),link('File checksums',`runs/${current.id}/SHA256SUMS.txt`));if(/^https:\/\/github\.com\/doudar\/smartspin2k-simulator\/actions\/runs\/\d+$/.test(md.workflow_url||''))$('downloads').append(link('GitHub Actions run',md.workflow_url));$('json').textContent=JSON.stringify(m,null,2);}
async function load(){const id=$('history').value;if(!safeId(id))throw Error('Invalid run identifier');const token=++serial;try{clearRun();$('notice').textContent='Loading selected experiment…';const result=await fetch(`runs/${id}/data.json`);if(!result.ok)throw Error('Run data unavailable');const data=await result.json();try{const motor=await fetch(`motor-v1/${id}.json`);if(motor.ok)data.motor=await motor.json();}catch(e){data.motor=null;}try{const cadence=await fetch(`cadence-v1/${id}.json`);data.cadence=cadence.ok?await cadence.json():null;}catch(e){data.cadence=null;}if(token!==serial)return;current=data;$('scenario').disabled=false;render();location.hash=encodeURIComponent(id);}catch(e){if(token===serial)fail(e);}}
$('history').addEventListener('change',()=>choose($('history').value).catch(fail));
$('firmware').addEventListener('change',()=>choose().catch(fail));
$('test-type').addEventListener('change',()=>{if(isLongType($('test-type').value)){if(desiredScenario!=='long_ride')shortScenario=desiredScenario;desiredScenario='long_ride';}else desiredScenario=shortScenario;return choose().catch(fail);});
$('sensitivity').addEventListener('change',()=>{desiredSensitivity=$('sensitivity').value;return choose().catch(fail);});
$('duration').addEventListener('change',()=>{desiredDuration=$('duration').value;return choose().catch(fail);});
$('table').addEventListener('change',()=>{desiredTable=$('table').value;return choose().catch(fail);});
$('scenario').addEventListener('change',()=>{desiredScenario=$('scenario').value;return choose($('history').value).catch(fail);});
function clearRun(){clearChartZoom();for(const id of ['overview','chart','metrics','decisions','provenance','downloads','json','chart-label','motor-note','cadence-note'])$(id).replaceChildren();clearLearning();clearSprints();$('scenario').disabled=true;}
function fail(e){clearRun();clearChartZoom(true);$('notice').textContent=`Unable to load results: ${e.message}. No previous run is being displayed.`;}
(async()=>{const r=await fetch(`history.json?v=${Date.now()}`,{cache:'no-store'});if(!r.ok)throw Error('History unavailable');history=await r.json();history.sort((a,b)=>(b.metadata.run_completed_at||b.metadata.imported_at||'').localeCompare(a.metadata.run_completed_at||a.metadata.imported_at||''));
 const initial=history.find(r=>r.id===decodeURIComponent(location.hash.slice(1)))||history.find(r=>selectionRows(r).length)||history[0];if(!initial){$('notice').textContent='No experiments published yet.';return;}
 const groups=[...new Map(history.map(r=>[firmwareKey(r),firmwareName(r)])).entries()];options($('firmware'),groups,firmwareKey(initial));
 options($('test-type'),testTypes,testType(initial));
 desiredDuration=initial.metadata.experiment_duration_min?String(initial.metadata.experiment_duration_min):null;desiredTable=initial.metadata.initial_state||null;desiredSensitivity=initial.metadata.sensitivity?String(initial.metadata.sensitivity):null;
 const first=selectionRows(initial)[0];desiredScenario=first?.scenario||null;
 await choose(initial.id);
})().catch(fail);
