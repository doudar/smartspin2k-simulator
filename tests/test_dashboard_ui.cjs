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
const ids=['history','scenario','seed','notice','overview','chart','chart-label','metrics','decisions','provenance','downloads','json','motor-note'];
const nodes=Object.fromEntries(ids.map(id=>[id,new Element(['history','scenario','seed'].includes(id)?'select':'div')]));
const score={mae_w:1,p95_error_w:2};const row=(scenario,seed)=>({scenario,seed,absolute_passed:true,relative_passed:true,failures:[],scores:{baseline:score,candidate:score},reported_power_comparison:{absolute_passed:true,relative_passed:true,failures:[]}});
const make=(id,rows,date)=>({id,metadata:{run_completed_at:date},comparison:{status:'complete',runs:rows},traces:{}});
const runs={a:make('a',[row('steps',7),row('ramp',7),row('ramp',91)],'2026-10-12T17:00:00Z'),b:make('b',[row('steps',7),row('ramp',7),row('ramp',91)],'2026-10-11T17:00:00Z'),c:make('c',[row('steps',7)],'2026-10-10T17:00:00Z')};
const history=Object.values(runs).map(r=>({id:r.id,metadata:r.metadata,display_ref:'branch-'+r.id}));
let delayedReject=null;
const ctx={document:{getElementById:id=>nodes[id],createElement:tag=>new Element(tag),createElementNS:(_,tag)=>new Element(tag)},location:{hash:''},Intl,Date,console,fetch:async url=>{
  if(url.startsWith('history.json'))return {ok:true,json:async()=>history};
  if(url.startsWith('motor-v1/'))return {ok:true,json:async()=>({traces:{'ramp-91':[[0,10000],[1,11000],[2,null],[3,12000],[4,13000]]}})};
  const id=url.split('/')[1];if(id==='broken')return new Promise((_,reject)=>delayedReject=reject);
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
 console.log('PASS: history preserves scenario/seed, explicit unavailable state, recovery, and stale-fetch isolation');
})().catch(e=>{console.error(e);process.exitCode=1;});
