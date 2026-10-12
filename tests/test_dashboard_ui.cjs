// Dependency-free behavior checks against the actual browser JavaScript.
const assert=require('node:assert/strict'), fs=require('node:fs'),vm=require('node:vm');
class Element {
  constructor(tag){this.tagName=tag;this.children=[];this.events={};this._text='';this._value='';this.disabled=false;}
  set textContent(t){this._text=String(t);this.children=[];}get textContent(){return this._text+this.children.map(x=>x.textContent).join('');}
  set value(v){this._value=String(v);}get value(){return this._value;}
  append(...nodes){for(const n of nodes){n.parent=this;this.children.push(n);if(this.tagName==='select'&&this.children.length===1)this.value=n.value;}}
  replaceChildren(...nodes){this.children=[];this._text='';if(this.tagName==='select')this._value='';this.append(...nodes);}
  setAttribute(k,v){this[k]=v;}addEventListener(event,handler){this.events[event]=handler;}
  remove(){if(this.parent)this.parent.children=this.parent.children.filter(n=>n!==this);}
  setPointerCapture(id){this.capture=id;}hasPointerCapture(id){return this.capture===id;}releasePointerCapture(){this.capture=null;}
  createSVGPoint(){return {x:0,y:0,matrixTransform(){return {x:this.x,y:this.y};}};}getScreenCTM(){return {inverse(){return {};}};}
  async change(v){this.value=v;await this.events.change?.();}
}
const ids=['sensitivity','sensitivity-filter','learning-scope','sprints','sprint-label','sprint-status','sprint-summary','sprint-zoom','sprint-metrics','sprint-decisions','sprint-hashes','zoom-in','zoom-out','zoom-reset','zoom-earlier','zoom-later','zoom-select','zoom-range','firmware','test-type','duration','table','duration-filter','table-filter','history','scenario','notice','overview','chart','chart-label','metrics','decisions','provenance','downloads','json','motor-note','cadence-note','chart-readout','learning','learning-label','learning-coverage','learning-metrics','learning-events','learning-evidence','learning-status','learning-hashes','learning-decisions','learning-grid'];

const score={mae_w:1,p95_error_w:2};const row=(scenario,seed)=>({scenario,seed,absolute_passed:true,relative_passed:true,failures:[],scores:{baseline:score,candidate:score},reported_power_comparison:{absolute_passed:true,relative_passed:true,failures:[]}});
const make=(id,rows,date)=>({id,metadata:{run_completed_at:date},comparison:{status:'complete',runs:rows},traces:{}});
const runs={a:make('a',[row('steps',7),row('ramp',7),row('ramp',91)],'2026-10-12T17:00:00Z'),b:make('b',[row('steps',7),row('ramp',7),row('ramp',91)],'2026-10-11T17:00:00Z'),c:make('c',[row('steps',7)],'2026-10-10T17:00:00Z')};
// Nondefault seeds contain deliberately failing results and different traces.
for(const run of Object.values(runs)){
 for(const item of run.comparison.runs.filter(item=>item.seed!==7)){item.absolute_passed=false;item.relative_passed=false;}
 run.traces={'ramp-7':{candidate:[[0,25,24,23],[2,50,49,48],[4,75,74,73]],baseline:[[0,25,22,21],[2,50,47,46],[4,75,72,71]]},'ramp-91':{candidate:[[0,9000,9000,9000],[4,9000,9000,9000]]}};
}
const coverage=n=>({tested_range_supported:n,tested_range_required:25,supported_cells:200,total_cells:300,tested_range_cells:[75,80,85,90,95].flatMap(cadence_rpm=>[150,180,210,240,270].map(watts=>({cadence_rpm,watts})))});
for(const [minutes,state,support] of [[30,'empty',0],[60,'partial',7],[90,'full',25]]){
 const r=row('long_ride',7);r.minutes=minutes;r.initial_state=state;r.artifact_key=`long_${minutes}m_${state}-7`;
 r.scores={};r.metadata={};r.window_comparisons={};for(const name of ['early','middle','late'])r.window_comparisons[name]={absolute_passed:name!=='early',relative_passed:name!=='early',failures:name==='early'?['early plant error exceeds allowance']:[],reported_power_comparison:{absolute_passed:true,relative_passed:true,failures:[]}};
 for(const variant of ['baseline','candidate']){
  r.metadata[variant]={initial_coverage:coverage(support),final_coverage:coverage(25),initial_table_sha256:'f'.repeat(64)};
  r.scores[variant]={...score,delivered_sensor_metrics:{...score},windows:['early','middle','late'].map((name,i)=>({name,start_s:[0,minutes*30-180,minutes*60-360][i],duration_s:360,metrics:{mae_w:11+i,p95_error_w:12+i,worst_settling_s:13+i,unsettled_steps:1},delivered_sensor_metrics:{mae_w:21+i,p95_error_w:22+i,worst_settling_s:23+i,unsettled_steps:2},events:{learning_observation:120+i,table_insert_attempt:30+i},starting_table:coverage(Math.min(support+i,25)),seeking_seconds:4+i,table_sha256:String(i+1).repeat(64)}))};
 }
 r.overall_checks={absolute_passed:false,relative_passed:false,passed:false};
 const id=`long-${state}`,run=make(id,[r],'2026-10-09T17:00:00Z');
 Object.assign(run.metadata,{experiment:'continuous-long-ride-v1',experiment_duration_min:minutes,initial_state:state,training_run_id:'shared-training',candidate_ref:'erg-spike-gate'});
 run.comparison.experiment='continuous-long-ride-v1';run.traces={'long_ride-7':{candidate:[[0,150,151,152],[minutes*30,0,0,0],[minutes*60,180,179,178]],baseline:[[0,150,149,148],[minutes*30,0,0,0],[minutes*60,180,177,176]]}};runs[id]=run;
}
// Same branch, different commits, and repeated snapshots must stay separately selectable.
runs['a-old']=make('a-old',[row('steps',7),row('ramp',7),row('ramp',91)],'2026-10-08T17:00:00Z');
runs['long-full-old']=JSON.parse(JSON.stringify(runs['long-full']));runs['long-full-old'].id='long-full-old';runs['long-full-old'].metadata.run_completed_at='2026-10-07T17:00:00Z';
// A passing nondefault seed must not dilute the failed seed-7 long-ride summary.
runs['long-full'].comparison.runs.push({...row('long_ride',27),overall_checks:{absolute_passed:true,relative_passed:true,passed:true}});
const history=Object.values(runs).map((r,i)=>{
 const commit=(i+1).toString(16).repeat(40).slice(0,40);
 r.comparison.firmware={candidate:{commit},baseline:{commit:'0'.repeat(40)}};
 return {id:r.id,metadata:r.metadata,display_ref:['b','c'].includes(r.id)?'branch-'+r.id:'erg-spike-gate',candidate_commit:commit,selections:r.comparison.runs.map(({scenario,seed})=>({scenario,seed}))};
});
// A release remains distinct from a similarly named branch.
const release=make('release',[row('steps',7),row('foreign_seed_only',91)],'2026-10-06T17:00:00Z');runs.release=release;
history.push({id:'release',metadata:{...release.metadata,release_tag:'v25.1',release_published_at:'2025-01-01T00:00:00Z'},display_ref:'v25.1',candidate_commit:'f'.repeat(40),selections:[{scenario:'steps',seed:7},{scenario:'foreign_seed_only',seed:91}]});
// This newest record has no seed-7 result. Defaults must skip it; its deep link
// must preserve the long-ride filters and show unavailable, never substitute seed 27.
const legacy=make('legacy-27',[row('long_ride',27)],'2026-10-13T17:00:00Z');
Object.assign(legacy.metadata,{experiment:'continuous-long-ride-v1',experiment_duration_min:45,initial_state:'partial',candidate_ref:'erg-spike-gate'});
legacy.comparison.experiment='continuous-long-ride-v1';legacy.traces={'long_ride-27':{candidate:[[0,999,999,999],[2700,999,999,999]]}};runs[legacy.id]=legacy;
history.push({id:legacy.id,metadata:legacy.metadata,display_ref:'erg-spike-gate',candidate_commit:'e'.repeat(40),selections:[{scenario:'long_ride',seed:27}]});
// V2 keeps its new six-case sensitivity matrix separate from archived v1 rides.
for(const state of ['empty','full'])for(const sensitivity of [3,5,10]){
 const run=JSON.parse(JSON.stringify(runs['long-full'])),id=`sprint-${state}-${sensitivity}`;run.id=id;
 Object.assign(run.metadata,{experiment:'continuous-long-ride-sprints-v2',experiment_duration_min:90,initial_state:state,sensitivity,training_run_id:'sprint-training',run_completed_at:'2026-10-05T17:00:00Z'});
 run.comparison.experiment=run.metadata.experiment;run.comparison.runs=run.comparison.runs.slice(0,1);
 const r=run.comparison.runs[0];Object.assign(r,{initial_state:state,sensitivity,artifact_key:`long_90m_${state}_sensitivity${sensitivity}-7`,overall_checks:{absolute_passed:true,relative_passed:true,passed:true}});
 for(const probe of Object.values(r.window_comparisons))Object.assign(probe,{absolute_passed:true,relative_passed:true,failures:[]});
 r.sprint_comparisons={};
 for(const name of ['early','middle','late'])r.sprint_comparisons[name]={absolute_passed:true,relative_passed:true,failures:[],reported_power_comparison:{absolute_passed:!(sensitivity===3&&name==='late'),relative_passed:!(sensitivity===3&&name==='late'),failures:sensitivity===3&&name==='late'?['sprint sensor miss exceeds allowance']:[]}};
 const response={rise_to_450w_s:null,sprint_settling_s:null,peak_power_w:440,peak_overshoot_w:0,above_520w_s:0,outside_20w_s:25,recovery_settling_s:null,recovery_peak_power_w:431,recovery_above_120w_s:22};
 const grid={tested_range_supported:state==='full'?45:0,tested_range_required:45,tested_range_cells:[75,80,85,90,95].flatMap(cadence_rpm=>[90,120,150,180,210,240,270,480,510].map(watts=>({cadence_rpm,watts})))};
 for(const variant of ['baseline','candidate']){
  r.metadata[variant].initial_coverage=grid;
  r.scores[variant].sprints=['early','middle','late'].map((name,i)=>({name,start_s:[360,2880,4955][i],duration_s:85,sprint_start_s:[390,2910,4985][i],recovery_start_s:[415,2935,5010][i],cadence_rpm:85,response:{...response},delivered_sensor_response:{...response,peak_power_w:435},starting_table:grid,table_sha256:'a'.repeat(64)}));
 }
 runs[id]=run;history.push({id,metadata:run.metadata,display_ref:'erg-spike-gate',candidate_commit:'d'.repeat(40),selections:[{scenario:'long_ride',seed:7}]});
}
const source=fs.readFileSync(require('node:path').join(__dirname,'../dashboard/app.js'),'utf8');
const tick=()=>new Promise(setImmediate);
function harness(hash=''){
 const nodes=Object.fromEntries(ids.map(id=>[id,new Element(['firmware','test-type','duration','sensitivity','table','history','scenario'].includes(id)?'select':'div')]));
 const pending=new Map(),requests=[],lookups=[];
 const hover={initCalls:[],clearCalls:0,updates:[],data:null,init(config){this.initCalls.push(config);},clear(){this.clearCalls++;this.data=null;},update(data){this.data=data;this.updates.push(data);}};
 const ctx={ChartHover:hover,document:{events:{},addEventListener(event,handler){this.events[event]=handler;},getElementById:id=>{lookups.push(id);return nodes[id];},createElement:tag=>new Element(tag),createElementNS:(_,tag)=>new Element(tag)},location:{hash},Intl,Date,console,fetch:async url=>{
  requests.push(url);
  if(url.startsWith('history.json'))return {ok:true,json:async()=>history.slice()};
  if(pending.has(url))return pending.get(url).promise;
  if(url.startsWith('cadence-v1/'))return {ok:true,json:async()=>({traces:{'ramp-7':[[0,80,79],[1,0,80],[2,null,null],[3,90,88],[4,100,99]],'long_ride-7':[[0,80,79],[2700,0,0],[5400,90,89]]}})};
  if(url.startsWith('motor-v1/'))return {ok:true,json:async()=>({traces:{'ramp-7':[[0,10000],[1,11000],[2,null],[3,12000],[4,13000]],'long_ride-7':[[0,10000],[5400,11000]]}})};
  const id=url.split('/')[1];return {ok:!!runs[id],json:async()=>runs[id]};
 }};
 vm.createContext(ctx);vm.runInContext(source,ctx);
 return {nodes,ctx,requests,lookups,hover,delay(url){let resolve,reject;const promise=new Promise((yes,no)=>{resolve=yes;reject=no;});pending.set(url,{promise});return {resolve(value){pending.delete(url);resolve(value);},reject(error){pending.delete(url);reject(error);}};}};
}
const main=harness(),{nodes,ctx}=main;
const cleared=(all=true)=>{assert.equal(main.hover.data,null);assert.equal(nodes.chart.children.length,0);assert.ok(nodes['zoom-in'].disabled);assert.ok(nodes['zoom-select'].disabled);assert.equal(nodes.metrics.children.length,0);assert.equal(nodes.learning.hidden,true);assert.equal(nodes.sprints.hidden,true);assert.equal(nodes['sprint-metrics'].children.length,0);assert.equal(nodes['learning-metrics'].children.length,0);assert.equal(nodes['learning-evidence'].children.length,0);if(all)assert.equal(nodes.downloads.children.length,0);else assert.ok(nodes.downloads.children.every(n=>n.href.includes(`runs/${nodes.history.value}/`)));};
(async()=>{
 await tick();assert.equal(main.hover.initCalls.length,1);assert.equal(main.hover.initCalls[0].svg,nodes.chart);assert.equal(main.hover.initCalls[0].readout,nodes['chart-readout']);assert.equal(nodes.firmware.value,'branch:erg-spike-gate');assert.equal(nodes['test-type'].value,'short');assert.equal(nodes.scenario.value,'steps');assert.equal(nodes.history.value,'a');assert.equal(main.lookups.includes('seed'),false);
 assert.deepEqual(nodes.history.children.map(n=>n.value),['a','a-old']);assert.equal(nodes.firmware.children.filter(n=>n.value==='branch:erg-spike-gate').length,1);assert.ok(nodes.firmware.children.some(n=>n.value==='release:v25.1'&&n.textContent.includes('2025-01-01')));
 assert.equal(nodes['duration-filter'].hidden,true);assert.equal(nodes['table-filter'].hidden,true);
 assert.match(nodes.overview.children[0].children[2].textContent,/seed.?7/i);assert.deepEqual(nodes.scenario.children.map(n=>n.value),['steps','ramp']);assert.match(nodes.notice.textContent,/0 pairs outside/);assert.equal(nodes.overview.children[1].children[1].textContent,'2 / 2');assert.equal(nodes.overview.children[2].children[1].textContent,'2 / 2');
 await nodes.scenario.change('ramp');assert.equal(nodes['chart-label'].textContent,'ramp / seed 7');
 await nodes.history.change('a-old');assert.equal(nodes.history.value,'a-old');assert.match(nodes.notice.textContent,/Tested candidate: 777777777777/);assert.match(nodes.provenance.textContent,/7777777777777777777777777777777777777777/);
 await nodes.scenario.change('steps');assert.equal(nodes.history.value,'a-old');await nodes.scenario.change('ramp');assert.equal(nodes.history.value,'a-old');
 await nodes.firmware.change('branch:branch-b');assert.equal(nodes.scenario.value,'ramp');assert.equal(nodes['chart-label'].textContent,'ramp / seed 7');assert.deepEqual(nodes.history.children.map(n=>n.value),['b']);
 await nodes.firmware.change('branch:branch-c');assert.equal(nodes.scenario.value,'ramp');assert.match(nodes.notice.textContent,/unavailable/i);cleared(false);
 await nodes.firmware.change('branch:erg-spike-gate');assert.equal(nodes.history.value,'a');assert.equal(nodes.scenario.value,'ramp');assert.ok(nodes.metrics.children.length>0);
 const delayed=main.delay('runs/a-old/data.json');const stale=nodes.history.change('a-old');await tick();cleared();await nodes.firmware.change('branch:branch-b');delayed.reject(Error('old failed request'));await stale;assert.equal(nodes['chart-label'].textContent,'ramp / seed 7');assert.equal(nodes.history.value,'b');
 assert.equal(nodes.chart.children.filter(n=>n['data-series']==='actual-motor').length,2);assert.ok(nodes.chart.children.some(n=>n.textContent==='100 W'));assert.ok(nodes.chart.children.some(n=>n.textContent==='Motor (steps)'));assert.match(nodes['motor-note'].textContent,/Missing position samples/);
 assert.equal(nodes.chart.children.filter(n=>n['data-series']==='modeled-cadence').length,2);assert.equal(nodes.chart.children.filter(n=>n['data-series']==='received-cadence').length,2);
 assert.ok(nodes.chart.children.filter(n=>n['data-series']==='modeled-cadence').some(n=>n.points.includes(',440.00'))); // zero cadence remains visible
 assert.ok(nodes.chart.children.some(n=>n.textContent==='Cadence (RPM) · candidate'));
 assert.equal(main.hover.data.from,0);assert.equal(main.hover.data.to,4);assert.equal(main.hover.data.end,4);assert.equal(main.hover.data.series.length,7);
 const hoverSeries=Object.fromEntries(main.hover.data.series.map(series=>[series.label,series]));
 assert.equal(hoverSeries['Target power'].units,'W');assert.equal(hoverSeries['Candidate actual motor'].units,'steps');assert.equal(hoverSeries['Candidate modeled rider cadence'].units,'RPM');assert.equal(hoverSeries['Candidate firmware-received cadence'].valueIndex,2);
 assert.equal(hoverSeries['Candidate modeled rider cadence'].rows[1][1],0);assert.equal(hoverSeries['Candidate modeled rider cadence'].rows[2][1],null);
 assert.equal(hoverSeries['Candidate plant power'].rows,runs.b.traces['ramp-7'].candidate);
 const target=nodes.chart.children.find(n=>n.stroke==='#b2c1cc');assert.ok(target.points.includes('470.00,160.00')); // time 2 s uses the same x transform as cadence
 assert.equal(nodes.chart.children.filter(n=>n['data-plot-hit']==='true').length,1);
 runs.b.motor={traces:{}};vm.runInContext('current.motor={traces:{}};render()',ctx);assert.match(nodes['motor-note'].textContent,/unavailable/);assert.equal(nodes.chart.children.filter(n=>n['data-series']==='actual-motor').length,0);
 assert.equal(nodes.learning.hidden,true);assert.equal(nodes.sprints.hidden,true);assert.equal(nodes['sprint-metrics'].children.length,0);assert.equal(nodes['learning-metrics'].children.length,0);
 // Missing received cadence stays missing; an explicit zero remains a recorded value.
 vm.runInContext("current.cadence={traces:{'ramp-7':[[0,0,null],[4,90,null]]}};render()",ctx);
 assert.match(nodes['cadence-note'].textContent,/Firmware-received cadence is not available/);assert.equal(nodes.chart.children.filter(n=>n['data-series']==='received-cadence').length,0);assert.equal(nodes.chart.children.filter(n=>n['data-series']==='modeled-cadence').length,1);assert.ok(nodes.chart.children.find(n=>n['data-series']==='modeled-cadence').points.includes('65.00,440.00'));
 // Failed optional sidecars must clear stale signal data without losing the power result.
 const absentMotor=main.delay('motor-v1/b.json'),absentCadence=main.delay('cadence-v1/b.json'),withoutSidecars=nodes.history.change('b');await tick();absentMotor.reject(Error('motor unavailable'));await tick();absentCadence.resolve({ok:false});await withoutSidecars;
 assert.equal(nodes['chart-label'].textContent,'ramp / seed 7');assert.match(nodes['motor-note'].textContent,/unavailable/);assert.match(nodes['cadence-note'].textContent,/Cadence unavailable/);assert.equal(nodes.chart.children.filter(n=>['actual-motor','modeled-cadence','received-cadence'].includes(n['data-series'])).length,0);assert.ok(nodes.chart.children.some(n=>n.textContent==='Cadence not recorded'));assert.ok(nodes.chart.children.some(n=>n.stroke==='#58dec8'));assert.equal(main.hover.data.series.find(series=>series.units==='RPM').rows.length,0);assert.ok(nodes.metrics.children.length>0);
 await nodes.firmware.change('branch:erg-spike-gate');await nodes['test-type'].change('long');assert.equal(nodes['duration-filter'].hidden,false);assert.equal(nodes['table-filter'].hidden,false);assert.equal(nodes.scenario.value,'long_ride');assert.equal(nodes.history.value,'long-empty');assert.equal(nodes.learning.hidden,false);
 await nodes.duration.change('90');cleared();await nodes.table.change('full');assert.deepEqual(nodes.history.children.map(n=>n.value),['long-full','long-full-old']);
 await nodes.history.change('long-full-old');assert.equal(nodes.history.value,'long-full-old');await nodes.scenario.change('long_ride');assert.equal(nodes.history.value,'long-full-old');await nodes.history.change('long-full');
 assert.equal(nodes.learning.hidden,false);assert.equal(nodes['learning-label'].textContent,'90 min · fully learned TESTED RANGE');
 assert.equal(nodes['learning-metrics'].children.length,13);assert.equal(nodes['learning-events'].children.length,7);assert.equal(nodes['learning-hashes'].children.length,9);
 assert.match(nodes['learning-metrics'].textContent,/early · 0.00–6.00 minBaselinePlant11.0012.0013.001.00/);
 assert.match(nodes['learning-metrics'].textContent,/late · 84.00–90.00 minCandidateDelivered sensor23.0024.0025.002.00/);
 assert.match(nodes['learning-coverage'].textContent,/25 \/ 25 tested cells → 25 \/ 25 tested cells/);assert.doesNotMatch(nodes['learning-coverage'].textContent,/200|300/);
 assert.match(nodes['learning-grid'].textContent,/75, 80, 85, 90, 95 rpm/);assert.match(nodes['learning-grid'].textContent,/80–90 rpm operational cues/);assert.equal(vm.runInContext('testedCoverage({tested_range_supported:15,tested_range_required:15})',ctx),'15 / 15 tested cells');assert.equal(vm.runInContext('testedCoverage({tested_range_supported:30,tested_range_required:25})',ctx),'Tested-range coverage unavailable');
 assert.match(nodes['learning-events'].textContent,/Insertion attempts/);assert.match(nodes['learning-hashes'].textContent,/ffffffff/);
 assert.equal(nodes['learning-evidence'].children[0].href,'runs/shared-training/evidence.zip');
 assert.match(nodes.overview.children[0].textContent,/seed.?7/i);assert.doesNotMatch(nodes.overview.children[0].textContent,/seed.?27/i);
 assert.match(nodes.decisions.textContent,/Whole ride · Plant: absolute PASS · relative PASS/);assert.equal(nodes.overview.children[1].children[1].textContent,'0 / 1');assert.equal(nodes.overview.children[2].children[1].textContent,'0 / 1');assert.match(nodes['learning-decisions'].textContent,/early · Plant: absolute OUTSIDE BAND · relative REGRESSION/);assert.match(nodes['learning-decisions'].textContent,/early plant error exceeds allowance/);assert.match(nodes['learning-decisions'].textContent,/middle · Delivered sensor: absolute PASS · relative PASS/);assert.ok(nodes.chart.children.some(n=>n.textContent==='200 W'));assert.ok(nodes.chart.children.some(n=>n['data-series']==='actual-motor'));
 // Unsafe evidence IDs never become URLs; absent event kinds count as zero only when events were recorded.
 runs['long-full'].metadata.training_run_id='../outside';delete runs['long-full'].comparison.runs[0].scores.baseline.windows[0].events;
 vm.runInContext('render()',ctx);assert.equal(nodes['learning-evidence'].children.some(n=>n.tagName==='a'),false);assert.match(nodes['learning-events'].children[1].textContent,/n\/a/);
 // Selection survives both directions, while stale learning data is hidden and cleared.
 await nodes.firmware.change('branch:branch-b');assert.equal(nodes.scenario.value,'long_ride');assert.equal(nodes.duration.value,'90');assert.equal(nodes.table.value,'full');assert.equal(nodes.history.disabled,true);cleared();assert.equal(nodes['learning-decisions'].children.length,0);assert.match(nodes.notice.textContent,/UNAVAILABLE/);
 await nodes.firmware.change('branch:erg-spike-gate');assert.equal(nodes.history.value,'long-full');assert.equal(nodes.learning.hidden,false);
 await nodes.duration.change('60');cleared();assert.equal(nodes.table.value,'full');await nodes.table.change('partial');assert.equal(nodes.learning.hidden,false);assert.match(nodes['learning-coverage'].textContent,/7 \/ 25 tested cells → 25 \/ 25 tested cells/);
 await nodes.duration.change('30');cleared();await nodes.table.change('empty');assert.equal(nodes.learning.hidden,false);assert.match(nodes['learning-coverage'].textContent,/0 \/ 25 tested cells/);
 runs['long-empty'].comparison.runs[0].scores.baseline.windows=[];
 vm.runInContext('render()',ctx);assert.match(nodes['learning-status'].textContent,/3 \/ 6/);assert.equal(nodes['learning-metrics'].children.length,7);
 // A stale successful data request and stale motor response cannot resurrect old results.
 const slow=main.delay('runs/long-empty/data.json');const pending=nodes.history.change('long-empty');await tick();cleared();await nodes.duration.change('60');await nodes.table.change('partial');slow.resolve({ok:true,json:async()=>runs['long-empty']});await pending;assert.equal(nodes.history.value,'long-partial');assert.match(nodes['learning-label'].textContent,/partially learned/);
 const slowMotor=main.delay('motor-v1/long-partial.json');const motorPending=nodes.history.change('long-partial');await tick();await nodes.firmware.change('branch:branch-b');slowMotor.resolve({ok:true,json:async()=>({traces:{}})});await motorPending;cleared();assert.match(nodes.notice.textContent,/UNAVAILABLE/);
 await nodes.firmware.change('branch:erg-spike-gate');await nodes.duration.change('60');await nodes.table.change('partial');const slowCadence=main.delay('cadence-v1/long-partial.json');const cadencePending=nodes.history.change('long-partial');await tick();await nodes.firmware.change('branch:branch-b');slowCadence.resolve({ok:true,json:async()=>({traces:{}})});await cadencePending;cleared();assert.equal(nodes['cadence-note'].textContent,'');
 await nodes['test-type'].change('short');assert.equal(nodes.scenario.value,'ramp');assert.equal(nodes['chart-label'].textContent,'ramp / seed 7');assert.equal(nodes.learning.hidden,true);
 // Deep links select firmware, type, duration, starting table, exact experiment and seed-7 scenario.
 const linked=harness('#long-full-old');await tick();assert.equal(linked.nodes.firmware.value,'branch:erg-spike-gate');assert.equal(linked.nodes['test-type'].value,'long');assert.equal(linked.nodes.duration.value,'90');assert.equal(linked.nodes.table.value,'full');assert.equal(linked.nodes.history.value,'long-full-old');assert.equal(linked.nodes.scenario.value,'long_ride');assert.equal(linked.nodes['chart-label'].textContent,'long_ride / seed 7');assert.equal(linked.nodes.learning.hidden,false);
 const oldLinked=harness('#legacy-27');await tick();assert.equal(oldLinked.nodes.firmware.value,'branch:erg-spike-gate');assert.equal(oldLinked.nodes['test-type'].value,'long');assert.equal(oldLinked.nodes.duration.value,'45');assert.equal(oldLinked.nodes.table.value,'partial');assert.equal(oldLinked.nodes.scenario.value,'long_ride');assert.equal(oldLinked.nodes.history.disabled,true);assert.equal(oldLinked.nodes.learning.hidden,true);assert.equal(oldLinked.nodes.chart.children.length,0);assert.equal(oldLinked.nodes.metrics.children.length,0);assert.match(oldLinked.nodes.notice.textContent,/unavailable/i);assert.equal(oldLinked.requests.includes('runs/legacy-27/data.json'),false);assert.equal(oldLinked.lookups.includes('seed'),false);
 const missing=harness('#not-a-run');await tick();assert.equal(missing.nodes.history.value,'a');
 const failure=main.delay('runs/b/data.json');const failed=nodes.history.change('b');failure.resolve({ok:false});await failed;cleared();assert.match(nodes.notice.textContent,/No previous run/);
 await nodes.firmware.change('branch:erg-spike-gate');assert.equal(nodes['chart-label'].textContent,'ramp / seed 7');
 // Zoom runs against actual pointer handlers, including touch opt-in and cancellations.
 const z=harness('#long-full'),zn=z.nodes,run=code=>vm.runInContext(code,z.ctx);await tick();
 const click=id=>zn[id].events.click();
 const pointer=(kind,x,extra={})=>zn.chart.events[kind]({pointerId:1,pointerType:'mouse',button:0,isPrimary:true,clientX:x,clientY:100,preventDefault(){},...extra});
 const range=()=>JSON.parse(run('JSON.stringify(zoomWindow)'));
 assert.match(zn['zoom-range'].textContent,/Full ride: 0–5400 s/);assert.ok(zn['zoom-reset'].disabled);
 pointer('pointerdown',713);pointer('pointermove',227);pointer('pointerup',227);assert.deepEqual(range(),[1080,4320]);assert.equal(z.hover.data.from,1080);assert.equal(z.hover.data.to,4320);assert.equal(z.hover.data.end,5400); // reverse drag
 assert.ok(zn.chart.children.filter(n=>n.tagName==='polyline').every(n=>['url(#plot-clip)','url(#cadence-clip)'].includes(n['clip-path'])));
 assert.ok(zn.chart.children.some(n=>n.textContent==='1080s'));assert.ok(zn.chart.children.some(n=>n.textContent==='4320s'));
 const modeled=zn.chart.children.find(n=>n['data-series']==='modeled-cadence');assert.ok(modeled.points.includes('470.00,440.00')); // pause at 2700 s shares center x
 const power=zn.chart.children.find(n=>n.stroke==='#58dec8');assert.ok(power.points.includes('470.00,280.00'));assert.equal(z.hover.data.series.find(series=>series.label==='Candidate plant power').rows.length,3); // raw samples retained for hover
 click('zoom-in');assert.deepEqual(range(),[1890,3510]);click('zoom-out');assert.deepEqual(range(),[1080,4320]);
 click('zoom-earlier');assert.deepEqual(range(),[0,3240]);assert.ok(zn['zoom-earlier'].disabled);click('zoom-later');assert.deepEqual(range(),[1620,4860]);click('zoom-reset');assert.equal(range(),null);
 pointer('pointerdown',227,{clientY:380});pointer('pointermove',713,{clientY:380});pointer('pointerup',713,{clientY:380});assert.deepEqual(range(),[1080,4320]);click('zoom-reset');
 pointer('pointerdown',227);pointer('pointermove',230);pointer('pointerup',230);assert.equal(range(),null); // tiny gesture
 pointer('pointerdown',227);pointer('pointermove',713);pointer('pointercancel',713);assert.equal(range(),null);assert.equal(run('selection'),null);
 pointer('pointerdown',227);pointer('pointermove',713);pointer('lostpointercapture',713);assert.equal(range(),null);
 pointer('pointerdown',227,{pointerType:'touch'});assert.equal(run('selection'),null); // normal touch scroll
 click('zoom-select');assert.equal(zn.chart['data-select-mode'],'true');pointer('pointerdown',227,{pointerType:'touch'});pointer('pointermove',713,{pointerType:'touch'});pointer('pointerup',713,{pointerType:'touch'});assert.deepEqual(range(),[1080,4320]);assert.equal(zn.chart['data-select-mode'],'false');
 click('zoom-select');pointer('pointerdown',227,{pointerType:'touch'});pointer('pointermove',713,{pointerId:2,pointerType:'touch',isPrimary:false});assert.equal(run('selection.last'),227);pointer('pointercancel',713,{pointerType:'touch'});assert.deepEqual(range(),[1080,4320]);
 click('zoom-select');pointer('pointerdown',227);z.ctx.document.events.keydown({key:'Escape'});assert.equal(run('selection'),null);assert.equal(zn.chart['data-select-mode'],'false');
 // Every sample shares the same time transform. No interpolation adds new samples.
 assert.equal(run('windowRows([[0,1],[1,2],[2,3],[3,4]],1.2,1.8).length'),2);
 click('zoom-reset');for(let i=0;i<20;i++)click('zoom-in');assert.equal(range()[1]-range()[0],1);assert.ok(zn['zoom-in'].disabled);
 for(let i=0;i<20;i++)click('zoom-out');assert.equal(range(),null);
 run('zoomWindow=[4000,5000];render()');assert.deepEqual(range(),[4000,5000]);
 // Available shorter runs clamp the window; unavailable data clears it and cannot be resurrected by stale fetches.
 const short=JSON.parse(JSON.stringify(runs['long-full']));short.traces={'long_ride-7':{candidate:[[0,150,151,152],[1800,180,179,178]]}};short.motor={traces:{}};short.cadence={traces:{}};
 z.ctx.shortRun=short;run('current=shortRun;render()');assert.deepEqual(range(),[800,1800]);
 const zslow=z.delay('runs/long-full-old/data.json');const zp=zn.history.change('long-full-old');await tick();assert.ok(zn['zoom-in'].disabled);pointer('pointerdown',227);assert.equal(run('selection'),null);
 await zn.firmware.change('branch:branch-b');zslow.resolve({ok:true,json:async()=>runs['long-full-old']});await zp;assert.equal(range(),null);assert.equal(zn.chart.children.length,0);assert.ok(zn['zoom-select'].disabled);
 await zn.firmware.change('branch:erg-spike-gate');assert.equal(range(),null);
 run('current.traces={};current.motor={traces:{}};current.cadence={traces:{}};render()');assert.ok(zn['zoom-in'].disabled);assert.equal(range(),null);
 assert.equal(main.lookups.includes('seed'),false);assert.equal(z.lookups.includes('seed'),false);assert.ok(main.hover.clearCalls>0);
 // V2 deep links initialize sensitivity, keep v1 isolated, and never offer partial tables or other durations.
 const sp=harness('#sprint-full-3'),sn=sp.nodes,srun=code=>vm.runInContext(code,sp.ctx);await tick();
 assert.equal(sn['test-type'].value,'long-sprints');assert.equal(sn.sensitivity.value,'3');assert.equal(sn['sensitivity-filter'].hidden,false);assert.equal(sn['duration-filter'].hidden,true);
 assert.deepEqual(sn.table.children.map(n=>n.value),['empty','full']);assert.deepEqual(sn.sensitivity.children.map(n=>n.value),['3','5','10']);assert.equal(sn.history.value,'sprint-full-3');assert.equal(sn.sprints.hidden,false);
 assert.match(sn['sprint-label'].textContent,/90 min.*fully learned TESTED RANGE.*ERG sensitivity 3/);assert.match(sn['learning-grid'].textContent,/90, 120, 150, 180, 210, 240, 270, 480, 510 W/);
 assert.match(sn['learning-coverage'].textContent,/45 \/ 45 tested cells/);assert.match(sn['learning-scope'].textContent,/all three sprint blocks/);assert.equal(sn['learning-evidence'].children[0].href,'runs/sprint-training/evidence.zip');
 assert.match(sn.provenance.textContent,/continuous-long-ride-sprints-v2/);assert.match(sn.provenance.textContent,/Shared training run IDsprint-training/);assert.match(sn.provenance.textContent,/ERG sensitivity3/);
 assert.equal(sn['sprint-metrics'].children.length,13);assert.equal(sn['sprint-hashes'].children.length,7);assert.equal(sn['sprint-summary'].children.length,3);assert.equal(sn['sprint-zoom'].children.length,3);
 assert.match(sn['sprint-status'].textContent,/All three sprint blocks/);assert.match(sn['sprint-metrics'].textContent,/Not reached in 25 s/);assert.match(sn['sprint-metrics'].textContent,/Not settled in 25 s/);assert.match(sn['sprint-metrics'].textContent,/Not settled in 30 s/);assert.match(sn['sprint-metrics'].textContent,/435.00/);
 assert.match(sn['sprint-decisions'].textContent,/late · Delivered sensor: absolute OUTSIDE BAND · relative REGRESSION/);assert.match(sn['sprint-decisions'].textContent,/sprint sensor miss exceeds allowance/);
 // A false sprint signal overrides even a stale true overall decision; whole-ride averages still pass.
 assert.match(sn.decisions.textContent,/Whole ride · Plant: absolute PASS/);assert.equal(sn.overview.children[1].children[1].textContent,'0 / 1');assert.equal(sn.overview.children[2].children[1].textContent,'0 / 1');
 assert.match(sn.overview.children[1].textContent,/all 3 sprints/);const oldZoom=sn['sprint-zoom'].children[0];oldZoom.events.click();
 assert.deepEqual(JSON.parse(srun('JSON.stringify(zoomWindow)')),[360,445]);assert.equal(sp.hover.data.from,360);assert.equal(sp.hover.data.to,445);assert.equal(sp.hover.data.series.length,7);
 assert.ok(sn.chart.children.some(n=>n['data-series']==='actual-motor'));assert.ok(sn.chart.children.some(n=>n['data-series']==='modeled-cadence'));
 sn['sprint-zoom'].children[2].events.click();assert.deepEqual(JSON.parse(srun('JSON.stringify(zoomWindow)')),[4955,5040]);
 await sn.sensitivity.change('5');assert.equal(sn.history.value,'sprint-full-5');assert.equal(sn.overview.children[1].children[1].textContent,'1 / 1');assert.match(sn['sprint-label'].textContent,/ERG sensitivity 5/);
 oldZoom.events.click();assert.deepEqual(JSON.parse(srun('JSON.stringify(zoomWindow)')),[4955,5040]); // Detached old controls cannot move the new run.
 await sn.sensitivity.change('10');assert.equal(sn.history.value,'sprint-full-10');await sn.table.change('empty');assert.equal(sn.history.value,'sprint-empty-10');assert.match(sn['learning-coverage'].textContent,/0 \/ 45 tested cells/);
 // Missing phase metrics remain explicit. Missing decisions must not produce a pass.
 const missingSprint=runs['sprint-empty-10'].comparison.runs[0];delete missingSprint.scores.candidate.sprints[0].response;missingSprint.scores.baseline.sprints.pop();delete missingSprint.sprint_comparisons.middle;
 srun('render()');assert.match(sn['sprint-status'].textContent,/5 \/ 6/);assert.match(sn['sprint-metrics'].textContent,/Unavailable/);assert.match(sn['sprint-summary'].children[1].textContent,/UNAVAILABLE/);assert.equal(sn.overview.children[1].children[1].textContent,'0 / 1');
 // Sensitivity changes and unavailable firmware clear old sprint evidence immediately, including pending fetches.
 const spSlow=sp.delay('runs/sprint-empty-5/data.json'),spPending=sn.sensitivity.change('5');await tick();assert.equal(sn.sprints.hidden,true);assert.equal(sn['sprint-metrics'].children.length,0);
 await sn.sensitivity.change('3');spSlow.resolve({ok:true,json:async()=>runs['sprint-empty-5']});await spPending;assert.equal(sn.history.value,'sprint-empty-3');assert.match(sn['sprint-label'].textContent,/ERG sensitivity 3/);
 await sn.firmware.change('branch:branch-b');assert.equal(sn.sensitivity.value,'3');assert.equal(sn.sprints.hidden,true);assert.equal(sn['sprint-metrics'].children.length,0);assert.equal(sn.chart.children.length,0);assert.match(sn.notice.textContent,/90-minute sprint ride.*ERG sensitivity 3/);
 await sn.firmware.change('branch:erg-spike-gate');assert.equal(sn.history.value,'sprint-empty-3');await sn['test-type'].change('long');assert.equal(sn.sprints.hidden,true);assert.equal(sn['sprint-hashes'].children.length,0);assert.equal(sn['sensitivity-filter'].hidden,true);assert.equal(sn['duration-filter'].hidden,false);assert.deepEqual(sn.table.children.map(n=>n.value),['empty','partial','full']);
 assert.ok(sn['test-type'].children.some(n=>n.value==='long'&&n.textContent.includes('v1 archive')));await sn.duration.change('30');assert.equal(sn.history.value,'long-empty');assert.doesNotMatch(sn['learning-scope'].textContent,/all three sprint blocks/);
 const html=fs.readFileSync(require('node:path').join(__dirname,'../dashboard/index.html'),'utf8');assert.doesNotMatch(html,/id=["']seed["']/);assert.match(html,/not accepted insertions/);assert.match(html,/loaded into RAM; flash persistence is not tested/);assert.match(html,/do not establish that learning causes an improvement/);
 console.log('PASS: v2 sensitivity matrix, independent sprint decisions/response/zoom and archive isolation; fixed seed 7, seed-filtered summaries and default/deep-link selection, chart zoom region/buttons/touch/cancellation/bounds/async/unavailable, firmware grouping, exact snapshots, deep links, absent combinations, preserved filters, motor axes/gaps, long-ride learning evidence, safe links, unavailable recovery, and stale-fetch isolation');
})().catch(e=>{console.error(e);process.exitCode=1;});

