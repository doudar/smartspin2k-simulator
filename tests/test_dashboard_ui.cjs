// Dependency-free behavior checks against the actual browser JavaScript.
const assert=require('node:assert/strict'), fs=require('node:fs'),vm=require('node:vm');
class Element {
  constructor(tag){this.tagName=tag;this.children=[];this.events={};this._text='';this._value='';this.disabled=false;}
  set textContent(t){this._text=String(t);this.children=[];}get textContent(){return this._text+this.children.map(x=>x.textContent).join('');}
  set value(v){this._value=String(v);}get value(){return this._value;}
  append(...nodes){for(const n of nodes){this.children.push(n);if(this.tagName==='select'&&this.children.length===1)this.value=n.value;}}
  replaceChildren(...nodes){this.children=[];this._text='';if(this.tagName==='select')this._value='';this.append(...nodes);}
  setAttribute(k,v){this[k]=v;}addEventListener(event,handler){this.events[event]=handler;}
  async change(v){this.value=v;await this.events.change?.();}
}
const ids=['history','scenario','seed','notice','overview','chart','chart-label','metrics','decisions','provenance','downloads','json','motor-note','learning','learning-label','learning-coverage','learning-metrics','learning-events','learning-evidence','learning-status','learning-hashes','learning-decisions','learning-grid'];
const nodes=Object.fromEntries(ids.map(id=>[id,new Element(['history','scenario','seed'].includes(id)?'select':'div')]));
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
 Object.assign(run.metadata,{experiment_duration_min:minutes,initial_state:state,training_run_id:'shared-training',candidate_ref:'erg-spike-gate'});
 run.comparison.experiment='continuous-long-ride-v1';run.traces={'long_ride-27':{candidate:[[0,150,151,152],[minutes*60,180,179,178]]}};runs[id]=run;
}
const history=Object.values(runs).map(r=>({id:r.id,metadata:r.metadata,display_ref:'branch-'+r.id}));
let delayedReject=null;
const ctx={document:{getElementById:id=>nodes[id],createElement:tag=>new Element(tag),createElementNS:(_,tag)=>new Element(tag)},location:{hash:''},Intl,Date,console,fetch:async url=>{
  if(url.startsWith('history.json'))return {ok:true,json:async()=>history};
  if(url.startsWith('motor-v1/'))return {ok:true,json:async()=>({traces:{'ramp-91':[[0,10000],[1,11000],[2,null],[3,12000],[4,13000]],'long_ride-27':[[0,10000],[5400,11000]]}})};
  const id=url.split('/')[1];if(id==='broken')return new Promise((_,reject)=>delayedReject=reject);
  if(id==='unavailable')return {ok:false};
  return {ok:true,json:async()=>runs[id]};
}};
vm.createContext(ctx);vm.runInContext(fs.readFileSync(require('node:path').join(__dirname,'../dashboard/app.js'),'utf8'),ctx);
(async()=>{
 await new Promise(setImmediate);assert.equal(nodes.scenario.value,'steps');assert.equal(nodes.seed.value,'7');
 await nodes.scenario.change('ramp');await nodes.seed.change('91');assert.equal(nodes['chart-label'].textContent,'ramp / seed 91');
 await nodes.history.change('b');assert.equal(nodes.scenario.value,'ramp');assert.equal(nodes.seed.value,'91');assert.equal(nodes['chart-label'].textContent,'ramp / seed 91');
 await nodes.history.change('c');assert.equal(nodes.scenario.value,'ramp');assert.equal(nodes.seed.value,'91');assert.match(nodes.notice.textContent,/unavailable/);assert.equal(nodes.metrics.children.length,0);assert.equal(nodes.chart.children.length,0);
 await nodes.history.change('a');assert.equal(nodes.scenario.value,'ramp');assert.equal(nodes.seed.value,'91');assert.equal(nodes['chart-label'].textContent,'ramp / seed 91');assert.ok(nodes.metrics.children.length>0);
 const stale=nodes.history.change('broken');await new Promise(setImmediate);await nodes.history.change('b');delayedReject(Error('old failed request'));await stale;assert.equal(nodes['chart-label'].textContent,'ramp / seed 91');
 assert.equal(nodes.chart.children.filter(n=>n['data-series']==='actual-motor').length,2);assert.ok(nodes.chart.children.some(n=>n.textContent==='100 W'));assert.ok(nodes.chart.children.some(n=>n.textContent==='Motor (steps)'));assert.match(nodes['motor-note'].textContent,/Missing position samples/);
 runs.b.motor={traces:{}};vm.runInContext('current.motor={traces:{}};render()',ctx);assert.match(nodes['motor-note'].textContent,/unavailable/);assert.equal(nodes.chart.children.filter(n=>n['data-series']==='actual-motor').length,0);
 assert.equal(nodes.learning.hidden,true);assert.equal(nodes['learning-metrics'].children.length,0);
 for(const [state,label]of [['empty','30 min · empty starting table'],['partial','60 min · partially learned TESTED RANGE'],['full','90 min · fully learned TESTED RANGE']])assert.ok(nodes.history.children.some(n=>n.value===`long-${state}`&&n.textContent.endsWith(label)));
 await nodes.history.change('long-full');assert.equal(nodes.scenario.value,'ramp');assert.equal(nodes.seed.value,'91');assert.equal(nodes.learning.hidden,true);
 await nodes.scenario.change('long_ride');assert.equal(nodes.learning.hidden,true);await nodes.seed.change('27');
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
 await nodes.history.change('b');assert.equal(nodes.scenario.value,'long_ride');assert.equal(nodes.seed.value,'27');assert.equal(nodes.learning.hidden,true);assert.equal(nodes['learning-metrics'].children.length,0);assert.equal(nodes['learning-evidence'].children.length,0);assert.equal(nodes['learning-decisions'].children.length,0);
 await nodes.history.change('long-partial');assert.equal(nodes.learning.hidden,false);assert.match(nodes['learning-coverage'].textContent,/7 \/ 25 tested cells → 25 \/ 25 tested cells/);
 await nodes.history.change('long-empty');assert.equal(nodes.learning.hidden,false);assert.match(nodes['learning-coverage'].textContent,/0 \/ 25 tested cells/);
 runs['long-empty'].comparison.runs[0].scores.baseline.windows=[];
 vm.runInContext('render()',ctx);assert.match(nodes['learning-status'].textContent,/3 \/ 6/);assert.equal(nodes['learning-metrics'].children.length,7);
 const pending=nodes.history.change('broken');await new Promise(setImmediate);assert.equal(nodes.learning.hidden,true);assert.equal(nodes['learning-hashes'].children.length,0);
 await nodes.history.change('long-partial');delayedReject(Error('late old failure'));await pending;assert.equal(nodes.learning.hidden,false);assert.match(nodes['learning-label'].textContent,/partially learned/);
 await nodes.history.change('unavailable');assert.equal(nodes.learning.hidden,true);assert.equal(nodes['learning-evidence'].children.length,0);assert.match(nodes.notice.textContent,/No previous run/);
 await nodes.history.change('a');await nodes.scenario.change('ramp');await nodes.seed.change('91');assert.equal(nodes['chart-label'].textContent,'ramp / seed 91');assert.equal(nodes.learning.hidden,true);
 const html=fs.readFileSync(require('node:path').join(__dirname,'../dashboard/index.html'),'utf8');assert.match(html,/not accepted insertions/);assert.match(html,/loaded into RAM; flash persistence is not tested/);assert.match(html,/do not establish that learning causes an improvement/);
 console.log('PASS: preserved filters, motor axes/gaps, long-ride learning evidence, safe links, unavailable recovery, and stale-fetch isolation');
})().catch(e=>{console.error(e);process.exitCode=1;});
