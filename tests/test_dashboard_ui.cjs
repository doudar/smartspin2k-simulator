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
const ids=['zoom-in','zoom-out','zoom-reset','zoom-earlier','zoom-later','zoom-select','zoom-range','firmware','test-type','duration','table','duration-filter','table-filter','history','scenario','seed','notice','overview','chart','chart-label','metrics','decisions','provenance','downloads','json','motor-note','learning','learning-label','learning-coverage','learning-metrics','learning-events','learning-evidence','learning-status','learning-hashes','learning-decisions','learning-grid'];

const score={mae_w:1,p95_error_w:2};const row=(scenario,seed)=>({scenario,seed,absolute_passed:true,relative_passed:true,failures:[],scores:{baseline:score,candidate:score},reported_power_comparison:{absolute_passed:true,relative_passed:true,failures:[]}});
const make=(id,rows,date)=>({id,metadata:{run_completed_at:date},comparison:{status:'complete',runs:rows},traces:{}});
const runs={a:make('a',[row('steps',7),row('ramp',7),row('ramp',91)],'2026-10-12T17:00:00Z'),b:make('b',[row('steps',7),row('ramp',7),row('ramp',91)],'2026-10-11T17:00:00Z'),c:make('c',[row('steps',7)],'2026-10-10T17:00:00Z')};
const coverage=n=>({tested_range_supported:n,tested_range_required:25,supported_cells:200,total_cells:300,tested_range_cells:[75,80,85,90,95].flatMap(cadence_rpm=>[150,180,210,240,270].map(watts=>({cadence_rpm,watts})))});
for(const [minutes,state,support] of [[30,'empty',0],[60,'partial',7],[90,'full',25]]){
 const r=row('long_ride',27);r.minutes=minutes;r.initial_state=state;r.artifact_key=`long_${minutes}m_${state}-27`;
 r.scores={};r.metadata={};r.window_comparisons={};for(const name of ['early','middle','late'])r.window_comparisons[name]={absolute_passed:name!=='early',relative_passed:name!=='early',failures:name==='early'?['early plant error exceeds allowance']:[],reported_power_comparison:{absolute_passed:true,relative_passed:true,failures:[]}};
 for(const variant of ['baseline','candidate']){
  r.metadata[variant]={initial_coverage:coverage(support),final_coverage:coverage(25),initial_table_sha256:'f'.repeat(64)};
  r.scores[variant]={...score,delivered_sensor_metrics:{...score},windows:['early','middle','late'].map((name,i)=>({name,start_s:[0,minutes*30-180,minutes*60-360][i],duration_s:360,metrics:{mae_w:11+i,p95_error_w:12+i,worst_settling_s:13+i,unsettled_steps:1},delivered_sensor_metrics:{mae_w:21+i,p95_error_w:22+i,worst_settling_s:23+i,unsettled_steps:2},events:{learning_observation:120+i,table_insert_attempt:30+i},starting_table:coverage(Math.min(support+i,25)),seeking_seconds:4+i,table_sha256:String(i+1).repeat(64)}))};
 }
 r.overall_checks={absolute_passed:false,relative_passed:false,passed:false};
 const id=`long-${state}`,run=make(id,[r],'2026-10-09T17:00:00Z');
 Object.assign(run.metadata,{experiment:'continuous-long-ride-v1',experiment_duration_min:minutes,initial_state:state,training_run_id:'shared-training',candidate_ref:'erg-spike-gate'});
 run.comparison.experiment='continuous-long-ride-v1';run.traces={'long_ride-27':{candidate:[[0,150,151,152],[minutes*60,180,179,178]]}};runs[id]=run;
}
// Same branch, different commits, and repeated snapshots must stay separately selectable.
runs['a-old']=make('a-old',[row('steps',7),row('ramp',7),row('ramp',91)],'2026-10-08T17:00:00Z');
runs['long-full-old']=JSON.parse(JSON.stringify(runs['long-full']));runs['long-full-old'].id='long-full-old';runs['long-full-old'].metadata.run_completed_at='2026-10-07T17:00:00Z';
const history=Object.values(runs).map((r,i)=>{
 const commit=(i+1).toString(16).repeat(40).slice(0,40);
 r.comparison.firmware={candidate:{commit},baseline:{commit:'0'.repeat(40)}};
 return {id:r.id,metadata:r.metadata,display_ref:['b','c'].includes(r.id)?'branch-'+r.id:'erg-spike-gate',candidate_commit:commit,selections:r.comparison.runs.map(({scenario,seed})=>({scenario,seed}))};
});
// A release remains distinct from a similarly named branch.
const release=make('release',[row('steps',7)],'2026-10-06T17:00:00Z');runs.release=release;
history.push({id:'release',metadata:{...release.metadata,release_tag:'v25.1',release_published_at:'2025-01-01T00:00:00Z'},display_ref:'v25.1',candidate_commit:'f'.repeat(40),selections:[{scenario:'steps',seed:7}]});
const source=fs.readFileSync(require('node:path').join(__dirname,'../dashboard/app.js'),'utf8');
const tick=()=>new Promise(setImmediate);
function harness(hash=''){
 const nodes=Object.fromEntries(ids.map(id=>[id,new Element(['firmware','test-type','duration','table','history','scenario','seed'].includes(id)?'select':'div')]));
 const pending=new Map(),requests=[];
 const ctx={document:{getElementById:id=>nodes[id],createElement:tag=>new Element(tag),createElementNS:(_,tag)=>new Element(tag)},location:{hash},Intl,Date,console,fetch:async url=>{
  requests.push(url);
  if(url.startsWith('history.json'))return {ok:true,json:async()=>history.slice()};
  if(pending.has(url))return pending.get(url).promise;
  if(url.startsWith('motor-v1/'))return {ok:true,json:async()=>({traces:{'ramp-91':[[0,10000],[1,11000],[2,null],[3,12000],[4,13000]],'long_ride-27':[[0,10000],[5400,11000]]}})};
  const id=url.split('/')[1];return {ok:!!runs[id],json:async()=>runs[id]};
 }};
 vm.createContext(ctx);vm.runInContext(source,ctx);
 return {nodes,ctx,requests,delay(url){let resolve,reject;const promise=new Promise((yes,no)=>{resolve=yes;reject=no;});pending.set(url,{promise});return {resolve(value){pending.delete(url);resolve(value);},reject(error){pending.delete(url);reject(error);}};}};
}
const main=harness(),{nodes,ctx}=main;
const cleared=(all=true)=>{assert.equal(nodes.chart.children.length,0);assert.ok(nodes['zoom-in'].disabled);assert.ok(nodes['zoom-select'].disabled);assert.equal(nodes.metrics.children.length,0);assert.equal(nodes.learning.hidden,true);assert.equal(nodes['learning-metrics'].children.length,0);assert.equal(nodes['learning-evidence'].children.length,0);if(all)assert.equal(nodes.downloads.children.length,0);else assert.ok(nodes.downloads.children.every(n=>n.href.includes(`runs/${nodes.history.value}/`)));};
(async()=>{
 await tick();assert.equal(nodes.firmware.value,'branch:erg-spike-gate');assert.equal(nodes['test-type'].value,'short');assert.equal(nodes.scenario.value,'steps');assert.equal(nodes.seed.value,'7');
 assert.deepEqual(nodes.history.children.map(n=>n.value),['a','a-old']);assert.equal(nodes.firmware.children.filter(n=>n.value==='branch:erg-spike-gate').length,1);assert.ok(nodes.firmware.children.some(n=>n.value==='release:v25.1'&&n.textContent.includes('2025-01-01')));
 assert.equal(nodes['duration-filter'].hidden,true);assert.equal(nodes['table-filter'].hidden,true);
 await nodes.scenario.change('ramp');await nodes.seed.change('91');assert.equal(nodes['chart-label'].textContent,'ramp / seed 91');
 await nodes.history.change('a-old');assert.equal(nodes.history.value,'a-old');assert.match(nodes.notice.textContent,/Tested candidate: 777777777777/);assert.match(nodes.provenance.textContent,/7777777777777777777777777777777777777777/);
 await nodes.seed.change('7');assert.equal(nodes.history.value,'a-old');await nodes.seed.change('91');
 await nodes.firmware.change('branch:branch-b');assert.equal(nodes.scenario.value,'ramp');assert.equal(nodes.seed.value,'91');assert.equal(nodes['chart-label'].textContent,'ramp / seed 91');assert.deepEqual(nodes.history.children.map(n=>n.value),['b']);
 await nodes.firmware.change('branch:branch-c');assert.equal(nodes.scenario.value,'ramp');assert.equal(nodes.seed.value,'91');assert.match(nodes.notice.textContent,/unavailable/i);cleared(false);
 await nodes.firmware.change('branch:erg-spike-gate');assert.equal(nodes.history.value,'a');assert.equal(nodes.scenario.value,'ramp');assert.equal(nodes.seed.value,'91');assert.ok(nodes.metrics.children.length>0);
 const delayed=main.delay('runs/a-old/data.json');const stale=nodes.history.change('a-old');await tick();cleared();await nodes.firmware.change('branch:branch-b');delayed.reject(Error('old failed request'));await stale;assert.equal(nodes['chart-label'].textContent,'ramp / seed 91');assert.equal(nodes.history.value,'b');
 assert.equal(nodes.chart.children.filter(n=>n['data-series']==='actual-motor').length,2);assert.ok(nodes.chart.children.some(n=>n.textContent==='100 W'));assert.ok(nodes.chart.children.some(n=>n.textContent==='Motor (steps)'));assert.match(nodes['motor-note'].textContent,/Missing position samples/);
 runs.b.motor={traces:{}};vm.runInContext('current.motor={traces:{}};render()',ctx);assert.match(nodes['motor-note'].textContent,/unavailable/);assert.equal(nodes.chart.children.filter(n=>n['data-series']==='actual-motor').length,0);
 assert.equal(nodes.learning.hidden,true);assert.equal(nodes['learning-metrics'].children.length,0);
 await nodes.firmware.change('branch:erg-spike-gate');await nodes['test-type'].change('long');assert.equal(nodes['duration-filter'].hidden,false);assert.equal(nodes['table-filter'].hidden,false);assert.equal(nodes.scenario.value,'long_ride');assert.equal(nodes.seed.value,'91');cleared(false);
 await nodes.duration.change('90');await nodes.table.change('full');assert.equal(nodes.seed.value,'91');cleared(false);await nodes.seed.change('27');assert.deepEqual(nodes.history.children.map(n=>n.value),['long-full','long-full-old']);
 await nodes.history.change('long-full-old');assert.equal(nodes.history.value,'long-full-old');await nodes.seed.change('27');assert.equal(nodes.history.value,'long-full-old');await nodes.history.change('long-full');
 assert.equal(nodes.learning.hidden,false);assert.equal(nodes['learning-label'].textContent,'90 min · fully learned TESTED RANGE');
 assert.equal(nodes['learning-metrics'].children.length,13);assert.equal(nodes['learning-events'].children.length,7);assert.equal(nodes['learning-hashes'].children.length,9);
 assert.match(nodes['learning-metrics'].textContent,/early · 0.00–6.00 minBaselinePlant11.0012.0013.001.00/);
 assert.match(nodes['learning-metrics'].textContent,/late · 84.00–90.00 minCandidateDelivered sensor23.0024.0025.002.00/);
 assert.match(nodes['learning-coverage'].textContent,/25 \/ 25 tested cells → 25 \/ 25 tested cells/);assert.doesNotMatch(nodes['learning-coverage'].textContent,/200|300/);
 assert.match(nodes['learning-grid'].textContent,/75, 80, 85, 90, 95 rpm/);assert.match(nodes['learning-grid'].textContent,/80–90 rpm operational cues/);assert.equal(vm.runInContext('testedCoverage({tested_range_supported:15,tested_range_required:15})',ctx),'15 / 15 tested cells');assert.equal(vm.runInContext('testedCoverage({tested_range_supported:30,tested_range_required:25})',ctx),'Tested-range coverage unavailable');
 assert.match(nodes['learning-events'].textContent,/Insertion attempts/);assert.match(nodes['learning-hashes'].textContent,/ffffffff/);
 assert.equal(nodes['learning-evidence'].children[0].href,'runs/shared-training/evidence.zip');
 assert.match(nodes.decisions.textContent,/Whole ride · Plant: absolute PASS · relative PASS/);assert.equal(nodes.overview.children[1].children[1].textContent,'0 / 1');assert.equal(nodes.overview.children[2].children[1].textContent,'0 / 1');assert.match(nodes['learning-decisions'].textContent,/early · Plant: absolute OUTSIDE BAND · relative REGRESSION/);assert.match(nodes['learning-decisions'].textContent,/early plant error exceeds allowance/);assert.match(nodes['learning-decisions'].textContent,/middle · Delivered sensor: absolute PASS · relative PASS/);assert.ok(nodes.chart.children.some(n=>n.textContent==='200 W'));assert.ok(nodes.chart.children.some(n=>n['data-series']==='actual-motor'));
 // Unsafe evidence IDs never become URLs; absent event kinds count as zero only when events were recorded.
 runs['long-full'].metadata.training_run_id='../outside';delete runs['long-full'].comparison.runs[0].scores.baseline.windows[0].events;
 vm.runInContext('render()',ctx);assert.equal(nodes['learning-evidence'].children.some(n=>n.tagName==='a'),false);assert.match(nodes['learning-events'].children[1].textContent,/n\/a/);
 // Selection survives both directions, while stale learning data is hidden and cleared.
 await nodes.firmware.change('branch:branch-b');assert.equal(nodes.scenario.value,'long_ride');assert.equal(nodes.seed.value,'27');assert.equal(nodes.duration.value,'90');assert.equal(nodes.table.value,'full');assert.equal(nodes.history.disabled,true);cleared();assert.equal(nodes['learning-decisions'].children.length,0);assert.match(nodes.notice.textContent,/UNAVAILABLE/);
 await nodes.firmware.change('branch:erg-spike-gate');assert.equal(nodes.history.value,'long-full');assert.equal(nodes.learning.hidden,false);
 await nodes.duration.change('60');cleared();assert.equal(nodes.table.value,'full');await nodes.table.change('partial');assert.equal(nodes.learning.hidden,false);assert.match(nodes['learning-coverage'].textContent,/7 \/ 25 tested cells → 25 \/ 25 tested cells/);
 await nodes.duration.change('30');cleared();await nodes.table.change('empty');assert.equal(nodes.learning.hidden,false);assert.match(nodes['learning-coverage'].textContent,/0 \/ 25 tested cells/);
 runs['long-empty'].comparison.runs[0].scores.baseline.windows=[];
 vm.runInContext('render()',ctx);assert.match(nodes['learning-status'].textContent,/3 \/ 6/);assert.equal(nodes['learning-metrics'].children.length,7);
 // A stale successful data request and stale motor response cannot resurrect old results.
 const slow=main.delay('runs/long-empty/data.json');const pending=nodes.history.change('long-empty');await tick();cleared();await nodes.duration.change('60');await nodes.table.change('partial');slow.resolve({ok:true,json:async()=>runs['long-empty']});await pending;assert.equal(nodes.history.value,'long-partial');assert.match(nodes['learning-label'].textContent,/partially learned/);
 const slowMotor=main.delay('motor-v1/long-partial.json');const motorPending=nodes.history.change('long-partial');await tick();await nodes.firmware.change('branch:branch-b');slowMotor.resolve({ok:true,json:async()=>({traces:{}})});await motorPending;cleared();assert.match(nodes.notice.textContent,/UNAVAILABLE/);
 await nodes['test-type'].change('short');assert.equal(nodes.scenario.value,'ramp');assert.equal(nodes.seed.value,'27');cleared(false);await nodes.seed.change('91');assert.equal(nodes['chart-label'].textContent,'ramp / seed 91');assert.equal(nodes.learning.hidden,true);
 // Deep links select firmware, type, duration, starting table, exact experiment and its first pair.
 const linked=harness('#long-full-old');await tick();assert.equal(linked.nodes.firmware.value,'branch:erg-spike-gate');assert.equal(linked.nodes['test-type'].value,'long');assert.equal(linked.nodes.duration.value,'90');assert.equal(linked.nodes.table.value,'full');assert.equal(linked.nodes.history.value,'long-full-old');assert.equal(linked.nodes.scenario.value,'long_ride');assert.equal(linked.nodes.seed.value,'27');assert.equal(linked.nodes.learning.hidden,false);
 const missing=harness('#not-a-run');await tick();assert.equal(missing.nodes.history.value,'a');
 const failure=main.delay('runs/b/data.json');const failed=nodes.history.change('b');failure.resolve({ok:false});await failed;cleared();assert.match(nodes.notice.textContent,/No previous run/);
 await nodes.firmware.change('branch:erg-spike-gate');assert.equal(nodes['chart-label'].textContent,'ramp / seed 91');
 // Zoom runs against actual pointer handlers, including touch opt-in and cancellations.
 const z=harness('#long-full'),zn=z.nodes,run=code=>vm.runInContext(code,z.ctx);await tick();
 const click=id=>zn[id].events.click();
 const pointer=(kind,x,extra={})=>zn.chart.events[kind]({pointerId:1,pointerType:'mouse',button:0,isPrimary:true,clientX:x,clientY:100,preventDefault(){},...extra});
 const range=()=>JSON.parse(run('JSON.stringify(zoomWindow)'));
 assert.match(zn['zoom-range'].textContent,/Full ride: 0–5400 s/);assert.ok(zn['zoom-reset'].disabled);
 pointer('pointerdown',713);pointer('pointermove',227);pointer('pointerup',227);assert.deepEqual(range(),[1080,4320]); // reverse drag
 assert.ok(zn.chart.children.filter(n=>n.tagName==='polyline').every(n=>n['clip-path']==='url(#plot-clip)'));
 assert.ok(zn.chart.children.some(n=>n.textContent==='1080s'));assert.ok(zn.chart.children.some(n=>n.textContent==='4320s'));
 click('zoom-in');assert.deepEqual(range(),[1890,3510]);click('zoom-out');assert.deepEqual(range(),[1080,4320]);
 click('zoom-earlier');assert.deepEqual(range(),[0,3240]);assert.ok(zn['zoom-earlier'].disabled);click('zoom-later');assert.deepEqual(range(),[1620,4860]);click('zoom-reset');assert.equal(range(),null);
 pointer('pointerdown',227);pointer('pointermove',230);pointer('pointerup',230);assert.equal(range(),null); // tiny gesture
 pointer('pointerdown',227);pointer('pointermove',713);pointer('pointercancel',713);assert.equal(range(),null);assert.equal(run('selection'),null);
 pointer('pointerdown',227);pointer('pointermove',713);pointer('lostpointercapture',713);assert.equal(range(),null);
 pointer('pointerdown',227,{pointerType:'touch'});assert.equal(run('selection'),null); // normal touch scroll
 click('zoom-select');assert.equal(zn.chart['data-select-mode'],'true');pointer('pointerdown',227,{pointerType:'touch'});pointer('pointermove',713,{pointerType:'touch'});pointer('pointerup',713,{pointerType:'touch'});assert.deepEqual(range(),[1080,4320]);assert.equal(zn.chart['data-select-mode'],'false');
 click('zoom-select');pointer('pointerdown',227,{pointerType:'touch'});pointer('pointermove',713,{pointerId:2,pointerType:'touch',isPrimary:false});assert.equal(run('selection.last'),227);pointer('pointercancel',713,{pointerType:'touch'});assert.deepEqual(range(),[1080,4320]);
 click('zoom-select');pointer('pointerdown',227);zn.chart.events.keydown({key:'Escape'});assert.equal(run('selection'),null);assert.equal(zn.chart['data-select-mode'],'false');
 // Every sample shares the same time transform. No interpolation adds new samples.
 assert.equal(run('windowRows([[0,1],[1,2],[2,3],[3,4]],1.2,1.8).length'),2);
 click('zoom-reset');for(let i=0;i<20;i++)click('zoom-in');assert.equal(range()[1]-range()[0],1);assert.ok(zn['zoom-in'].disabled);
 for(let i=0;i<20;i++)click('zoom-out');assert.equal(range(),null);
 run('zoomWindow=[4000,5000];render()');assert.deepEqual(range(),[4000,5000]);
 // Available shorter runs clamp the window; unavailable data clears it and cannot be resurrected by stale fetches.
 const short=JSON.parse(JSON.stringify(runs['long-full']));short.traces={'long_ride-27':{candidate:[[0,150,151,152],[1800,180,179,178]]}};short.motor={traces:{}};
 z.ctx.shortRun=short;run('current=shortRun;render()');assert.deepEqual(range(),[800,1800]);
 const zslow=z.delay('runs/long-full-old/data.json');const zp=zn.history.change('long-full-old');await tick();assert.ok(zn['zoom-in'].disabled);pointer('pointerdown',227);assert.equal(run('selection'),null);
 await zn.firmware.change('branch:branch-b');zslow.resolve({ok:true,json:async()=>runs['long-full-old']});await zp;assert.equal(range(),null);assert.equal(zn.chart.children.length,0);assert.ok(zn['zoom-select'].disabled);
 await zn.firmware.change('branch:erg-spike-gate');assert.equal(range(),null);
 run('current.traces={};current.motor={traces:{}};render()');assert.ok(zn['zoom-in'].disabled);assert.equal(range(),null);
 const html=fs.readFileSync(require('node:path').join(__dirname,'../dashboard/index.html'),'utf8');assert.match(html,/not accepted insertions/);assert.match(html,/loaded into RAM; flash persistence is not tested/);assert.match(html,/do not establish that learning causes an improvement/);
 console.log('PASS: chart zoom region/buttons/touch/cancellation/bounds/async/unavailable,  firmware grouping, exact snapshots, deep links, absent combinations, preserved filters, motor axes/gaps, long-ride learning evidence, safe links, unavailable recovery, and stale-fetch isolation');
})().catch(e=>{console.error(e);process.exitCode=1;});

