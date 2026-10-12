'use strict';
const $=id=>document.getElementById(id);
const el=(tag,text,cls)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n;};
const number=v=>typeof v==='number'&&Number.isFinite(v)?v.toFixed(2):'n/a';
const safeId=s=>typeof s==='string'&&/^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,100}$/.test(s);
const decision=(v,relative=false)=>v===true?'PASS':v===false?(relative?'REGRESSION':'OUTSIDE BAND'):'UNAVAILABLE';
let current, history, serial=0, desiredScenario=null, desiredSeed=null, desiredDuration=null, desiredTable=null, shortScenario=null;
function runDate(md){const value=md.run_completed_at||md.imported_at;if(!value||!Number.isFinite(Date.parse(value)))return 'time not recorded';return new Intl.DateTimeFormat('en-US',{timeZone:'Etc/GMT+5',year:'numeric',month:'short',day:'numeric',hour:'2-digit',minute:'2-digit',second:'2-digit',hour12:false}).format(new Date(value))+' UTC−05:00';}
const initialState=s=>({empty:'empty starting table',partial:'partially learned TESTED RANGE',full:'fully learned TESTED RANGE'})[s]||'starting state not recorded';
function rideLabel(minutes,state){return `${[30,60,90].includes(minutes)?minutes+' min':'duration not recorded'} · ${initialState(state)}`;}
function runName(r){return `${runDate(r.metadata)} · ${(r.candidate_commit||'revision not recorded').slice(0,12)} · ${r.id}`;}
// A branch is a navigation group, never a claim that its snapshots are equivalent.
function firmwareKey(r){return r.metadata.release_tag?'release:'+r.metadata.release_tag:r.display_ref&&r.display_ref!=='Unrecorded ref'&&!r.display_ref.startsWith('commit ')?'branch:'+r.display_ref:'commit:'+(r.candidate_commit||r.id);}
function firmwareName(r){return r.metadata.release_tag?`${r.metadata.release_tag} · release${r.metadata.release_published_at?' · '+r.metadata.release_published_at.slice(0,10):''}`:r.display_ref||r.candidate_commit||'Unrecorded firmware';}
const testType=r=>r.metadata.experiment==='continuous-long-ride-v1'?'long':'short';
const selectionRows=r=>r.selections||[];
function selectedRuns(){return history.filter(r=>firmwareKey(r)===$('firmware').value&&testType(r)===$('test-type').value&&($('test-type').value!=='long'||String(r.metadata.experiment_duration_min)===desiredDuration&&r.metadata.initial_state===desiredTable));}
function updateSelectors(preferredId){
 const type=$('test-type').value;options($('test-type'),[['short','Short scenario tests'],['long','Continuous long rides']].map(([v,t])=>[v,t+(history.some(r=>firmwareKey(r)===$('firmware').value&&testType(r)===v)?'':' (unavailable)')]),type);
 const long=type==='long';$('duration-filter').hidden=!long;$('table-filter').hidden=!long;
 const family=history.filter(r=>testType(r)===$('test-type').value),group=family.filter(r=>firmwareKey(r)===$('firmware').value);
 const durations=[...new Set(family.map(r=>String(r.metadata.experiment_duration_min)))].filter(x=>x!=='undefined').sort((a,b)=>Number(a)-Number(b));
 if(!desiredDuration)desiredDuration=durations[0]||'30';if(!desiredTable)desiredTable='empty';
 options($('duration'),durations.map(v=>[v,`${v} min${group.some(r=>String(r.metadata.experiment_duration_min)===v)?'':' (unavailable)'}`]),desiredDuration);
 options($('table'),['empty','partial','full'].map(v=>[v,initialState(v)+(group.some(r=>r.metadata.initial_state===v&&String(r.metadata.experiment_duration_min)===desiredDuration)?'':' (unavailable)')]),desiredTable);
 const names=[...new Set(family.flatMap(r=>selectionRows(r).map(x=>x.scenario)))];
 if(!desiredScenario)desiredScenario=names[0]|| (long?'long_ride':'');
 if(desiredScenario&&!names.includes(desiredScenario))names.unshift(desiredScenario);
 const matches=selectedRuns(),chosen=matches.find(r=>r.id===preferredId)||matches.find(r=>selectionRows(r).some(x=>x.scenario===desiredScenario&&String(x.seed)===desiredSeed))||matches[0],available=chosen?selectionRows(chosen):[];
 options($('scenario'),names.map(v=>[v,v+(available.some(x=>x.scenario===v)?'':' (unavailable)')]),desiredScenario);
 const seeds=[...new Set(family.flatMap(r=>selectionRows(r).filter(x=>x.scenario===desiredScenario).map(x=>String(x.seed))))].sort((a,b)=>Number(a)-Number(b));
 if(!desiredSeed)desiredSeed=seeds[0]||'';if(desiredSeed&&!seeds.includes(desiredSeed))seeds.unshift(desiredSeed);
 options($('seed'),seeds.map(v=>[v,v+(available.some(x=>x.scenario===desiredScenario&&String(x.seed)===v)?'':' (unavailable)')]),desiredSeed);
 // Keep a chosen snapshot within a test; switching firmware selects its newest
 // matching experiment, visibly naming its exact revision rather than substituting it.
 options($('history'),matches.length?matches.map(r=>[r.id,runName(r)]):[['','No recorded experiment for this combination']],chosen?.id);
 $('history').disabled=!matches.length;$('scenario').disabled=false;$('seed').disabled=false;
 return matches.length>0;
}
async function choose(preferredId){
 if(updateSelectors(preferredId))return load();
 ++serial;current=null;clearRun();$('scenario').disabled=false;$('seed').disabled=false;
 $('notice').textContent='UNAVAILABLE: No recorded '+($('test-type').value==='long'?`${desiredDuration}-minute long ride with ${initialState(desiredTable)}`:'short scenario test')+' for this firmware. Your scenario and seed selections are kept. Choose another test or firmware; no previous chart or baseline-only result is shown.';
 $('chart-label').textContent='Selected test unavailable';location.hash='';
}
function options(node,items,value){node.replaceChildren();for(const [v,t]of items){const o=el('option',t);o.value=v;node.append(o);}if(value&&items.some(x=>x[0]===value))node.value=value;}
function card(label,value,note,ok){const d=el('div',undefined,'card');d.append(el('span',label),el('strong',value,ok===true?'good':ok===false?'bad':''),el('span',note));return d;}
function both(row,key){const overall=row.overall_checks?.[key];if(typeof overall==='boolean')return overall;const v=row[key],sensor=row.reported_power_comparison?.[key];return v===false||sensor===false?false:v===true&&sensor===true?true:null;}
function line(label,value){$('provenance').append(el('dt',label),el('dd',String(value??'Not recorded')));}
function link(text,path){const a=el('a',text);a.href=path;return a;}
function draw(row){
const svg=$('chart');svg.replaceChildren();const ns='http://www.w3.org/2000/svg';
const add=(tag,attrs,text)=>{const n=document.createElementNS(ns,tag);for(const[k,v]of Object.entries(attrs))n.setAttribute(k,v);if(text)n.textContent=text;svg.append(n);};
const key=`${row.scenario}-${row.seed}`,artifactKey=safeId(row.artifact_key)?row.artifact_key:key,traces=current.traces?.[key]||current.traces?.[artifactKey]||{};
const c=traces.candidate||[],b=traces.baseline||[],motor=current.motor?.traces?.[key]||current.motor?.traces?.[artifactKey]||[];
const validMotor=motor.filter(r=>typeof r[1]==='number'&&Number.isFinite(r[1]));
$('motor-note').textContent=validMotor.length?'Red: candidate simulated actual motor position (motor_steps), right axis in steps. This is the virtual motor counter; commanded target and physical bike position are separate signals.'+(validMotor.length<motor.length?' Missing position samples are shown as gaps.':''):'Actual motor position unavailable for this run / scenario / seed; no position values are inferred.';
if(!c.length&&!b.length){add('text',{x:65,y:140},'No power trace available for this run.');if(!validMotor.length)return;}
const all=[...c,...b],end=Math.max(...all.map(r=>r[0]),...motor.map(r=>r[0]),1);
// Watts and steps have independent scales. Motor values must never inflate watts.
const top=Math.ceil(Math.max(...all.flatMap(r=>r.slice(1,4)),100)/100)*100;
const left=65,right=875,x=t=>left+t/end*(right-left),y=w=>280-w/top*240;
for(let i=0;i<=4;i++){const w=top*i/4;add('line',{x1:left,x2:right,y1:y(w),y2:y(w),stroke:'#304255'});add('text',{x:10,y:y(w)+4},`${w} W`);const t=end*i/4;add('text',{x:x(t)-10,y:306},`${Math.round(t)}s`);}
for(const[rows,col,color]of [[c.length?c:b,1,'#b2c1cc'],[b,2,'#639de8'],[c,2,'#58dec8'],[c,3,'#f5c16c']]){if(!rows.length)continue;add('polyline',{points:rows.map(r=>`${x(r[0]).toFixed(2)},${y(r[col]).toFixed(2)}`).join(' '),fill:'none',stroke:color,'stroke-width':col===3?1:1.6,opacity:col===3?.6:1});}
if(validMotor.length){
const values=validMotor.map(r=>r[1]),lo=Math.min(...values),hi=Math.max(...values),pad=Math.max((hi-lo)*.08,1);
const bottom=Math.floor(lo-pad),topStep=Math.ceil(hi+pad),ym=p=>280-(p-bottom)/(topStep-bottom)*240;
add('line',{x1:right,x2:right,y1:40,y2:280,stroke:'#ff646b'});add('text',{x:right+10,y:22,class:'motor-axis'},'Motor (steps)');
for(let i=0;i<=4;i++){const p=bottom+(topStep-bottom)*i/4;add('text',{x:right+10,y:ym(p)+4,class:'motor-axis'},String(Math.round(p)));}
let segment=[];const flush=()=>{if(segment.length===1)add('circle',{cx:x(segment[0][0]),cy:ym(segment[0][1]),r:2,fill:'#ff646b','data-series':'actual-motor'});else if(segment.length)add('polyline',{points:segment.map(r=>`${x(r[0]).toFixed(2)},${ym(r[1]).toFixed(2)}`).join(' '),fill:'none',stroke:'#ff646b','stroke-width':1.8,'data-series':'actual-motor'});segment=[];};
for(const r of motor){if(typeof r[1]==='number'&&Number.isFinite(r[1]))segment.push(r);else flush();}flush();
}}

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
clearLearning();if(!row||current.comparison.experiment!=='continuous-long-ride-v1'||row.scenario!=='long_ride')return;
$('learning-grid').textContent=gridDescription(row.metadata?.candidate?.initial_coverage||row.metadata?.baseline?.initial_coverage);
$('learning').hidden=false;$('learning-label').textContent=rideLabel(row.minutes??current.metadata.experiment_duration_min,row.initial_state??current.metadata.initial_state);
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

function selectFilters(rows){return rows.find(r=>r.scenario===desiredScenario&&String(r.seed)===desiredSeed);}
function render(){const m=current.comparison;const longRide=m.experiment==='continuous-long-ride-v1';const rows=m.runs||[];const row=selectFilters(rows);const abs=rows.filter(r=>both(r,'absolute_passed')===true).length,rel=rows.filter(r=>both(r,'relative_passed')===true).length;$('overview').replaceChildren(card('EXPERIMENT STATUS',m.status,`${rows.length} recorded scenario / seed pairs`,m.status==='complete'),card('ABSOLUTE BANDS',`${abs} / ${rows.length}`,longRide?'Whole ride + every probe; both signals':'Plant AND delivered sensor',rows.length?abs===rows.length:null),card('RELATIVE REGRESSION',`${rel} / ${rows.length}`,longRide?'Whole ride + every probe vs pinned baseline':'Versus pinned baseline',rows.length?rel===rows.length:null),card('MODEL',String(m.profile_sha256||'Unavailable').slice(0,12),'SHA-256 · fitted bike profile'));
$('notice').textContent=m.status==='complete'?`${m.budget_status||'Provisional engineering budgets'}. ${rows.length-abs} pairs outside one or more absolute bands. This is a model result, not a hardware pass.`:`${m.status.toUpperCase()}: ${m.error||current.metadata.reason||'No complete result available.'}`;
$('notice').textContent+=` Tested candidate: ${(m.firmware?.candidate?.commit||history.find(r=>r.id===current.id)?.candidate_commit||'revision not recorded').slice(0,12)}. Branch snapshots can differ between tests.`;
$('metrics').replaceChildren();$('decisions').replaceChildren();renderLearning(row);if(row){$('chart-label').textContent=`${row.scenario} / seed ${row.seed}`;draw(row);const head=el('tr');for(const t of ['Signal / metric','Baseline','Candidate','Delta','Relative allowance'])head.append(el('th',t));$('metrics').append(head);for(const [signal,sub] of [['Plant',null],['Delivered sensor','delivered_sensor_metrics']]){const base=sub?row.scores?.baseline?.[sub]:row.scores?.baseline,cand=sub?row.scores?.candidate?.[sub]:row.scores?.candidate,changes=sub?row.reported_power_comparison?.changes:row.changes;for(const metric of ['mae_w','p95_error_w','overshoot_w','undershoot_w','outside_band_percent','steady_rmse_w','steady_variation_w_per_s','unsettled_steps','worst_settling_s']){const tr=el('tr');for(const t of [`${signal} · ${metric.replaceAll('_',' ')}`,number(base?.[metric]),number(cand?.[metric]),number(changes?.[metric]?.delta),number(changes?.[metric]?.allowance)])tr.append(el('td',t));$('metrics').append(tr);}}
for(const [label,score] of [['Plant',row],['Delivered sensor',row.reported_power_comparison]]){const p=el('p',`${longRide?'Whole ride · ':''}${label}: absolute ${decision(score?.absolute_passed)} · relative ${decision(score?.relative_passed,true)}`);$('decisions').append(p);const ul=el('ul');for(const f of (score?.failures||[]).filter(f=>label!=='Plant'||!f.startsWith('delivered sensor: ')))ul.append(el('li',f,'bad'));$('decisions').append(ul);}}else{$('chart').replaceChildren();$('motor-note').textContent='';$('chart-label').textContent='Selected scenario / seed unavailable';const explanation=`${desiredScenario||'No scenario'} / seed ${desiredSeed||'not selected'} is unavailable in this run. Your selection is kept; switch back or choose an available combination.`;$('notice').textContent+=' '+explanation;$('decisions').append(el('p',explanation));}
$('provenance').replaceChildren();const md=current.metadata;line('Tested firmware ref',history.find(r=>r.id===current.id)?.display_ref||md.candidate_ref||md.release_tag||'Not recorded');line('Run ID',current.id);line('Experiment completed (UTC)',md.run_completed_at||'Not recorded');line('Evidence imported (UTC)',md.imported_at);line('Candidate release',md.release_tag||'Development commit');line('Release published (UTC)',md.release_published_at||'Not a release / not recorded');line('Baseline release',md.baseline_release_tag);line('Baseline release published',md.baseline_release_published_at);line('Candidate commit',m.firmware?.candidate?.commit);line('Baseline commit',m.firmware?.baseline?.commit);line('Adapter commit',md.adapter_commit);line('Adapter SHA-256',m.adapter?.sha256);line('Adapter patch SHA-256',md.adapter_patch_sha256||'No compatibility patch');line('Simulator commit',md.simulator_commit);line('Simulator source SHA-256',m.simulator_sha256);line('Profile SHA-256',m.profile_sha256);line('Package config SHA-256',m.package_config_sha256);line('Candidate source SHA-256',m.firmware?.candidate?.source_sha256);line('Baseline source SHA-256',m.firmware?.baseline?.source_sha256);line('Source dirty flags',JSON.stringify(Object.fromEntries(Object.entries(m.firmware||{}).map(([k,v])=>[k,v.dirty]))));line('Coverage',m.coverage_level);line('Runtime toolchain',JSON.stringify(md.runtime_toolchain||'Not recorded; adapter-provenance toolchain, if present, describes original local validation only'));line('Provenance notes',md.notes);
$('downloads').replaceChildren(link('Full raw evidence ZIP',`runs/${current.id}/evidence.zip`),link('Comparison JSON',`runs/${current.id}/comparison.json`),link('File checksums',`runs/${current.id}/SHA256SUMS.txt`));if(/^https:\/\/github\.com\/doudar\/smartspin2k-simulator\/actions\/runs\/\d+$/.test(md.workflow_url||''))$('downloads').append(link('GitHub Actions run',md.workflow_url));$('json').textContent=JSON.stringify(m,null,2);}
async function load(){const id=$('history').value;if(!safeId(id))throw Error('Invalid run identifier');const token=++serial;try{clearRun();$('notice').textContent='Loading selected experiment…';const result=await fetch(`runs/${id}/data.json`);if(!result.ok)throw Error('Run data unavailable');const data=await result.json();try{const motor=await fetch(`motor-v1/${id}.json`);if(motor.ok)data.motor=await motor.json();}catch(e){data.motor=null;}if(token!==serial)return;current=data;$('scenario').disabled=false;$('seed').disabled=false;render();location.hash=encodeURIComponent(id);}catch(e){if(token===serial)fail(e);}}
$('history').addEventListener('change',()=>choose($('history').value).catch(fail));
$('firmware').addEventListener('change',()=>choose().catch(fail));
$('test-type').addEventListener('change',()=>{if($('test-type').value==='long'){shortScenario=desiredScenario;desiredScenario='long_ride';}else desiredScenario=shortScenario;return choose().catch(fail);});
$('duration').addEventListener('change',()=>{desiredDuration=$('duration').value;return choose().catch(fail);});
$('table').addEventListener('change',()=>{desiredTable=$('table').value;return choose().catch(fail);});
$('scenario').addEventListener('change',()=>{desiredScenario=$('scenario').value;return choose($('history').value).catch(fail);});
$('seed').addEventListener('change',()=>{desiredSeed=$('seed').value;return choose($('history').value).catch(fail);});
function clearRun(){for(const id of ['overview','chart','metrics','decisions','provenance','downloads','json','chart-label','motor-note'])$(id).replaceChildren();clearLearning();$('scenario').disabled=true;$('seed').disabled=true;}
function fail(e){clearRun();$('notice').textContent=`Unable to load results: ${e.message}. No previous run is being displayed.`;}
(async()=>{const r=await fetch(`history.json?v=${Date.now()}`,{cache:'no-store'});if(!r.ok)throw Error('History unavailable');history=await r.json();history.sort((a,b)=>(b.metadata.run_completed_at||b.metadata.imported_at||'').localeCompare(a.metadata.run_completed_at||a.metadata.imported_at||''));
 const initial=history.find(r=>r.id===decodeURIComponent(location.hash.slice(1)))||history[0];if(!initial){$('notice').textContent='No experiments published yet.';return;}
 const groups=[...new Map(history.map(r=>[firmwareKey(r),firmwareName(r)])).entries()];options($('firmware'),groups,firmwareKey(initial));
 options($('test-type'),[['short','Short scenario tests'],['long','Continuous long rides']],testType(initial));
 desiredDuration=initial.metadata.experiment_duration_min?String(initial.metadata.experiment_duration_min):null;desiredTable=initial.metadata.initial_state||null;
 const first=selectionRows(initial)[0];desiredScenario=first?.scenario||null;desiredSeed=first?String(first.seed):null;
 await choose(initial.id);
})().catch(fail);
