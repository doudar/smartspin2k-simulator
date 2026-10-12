// Real dashboard startup/rendering with local and Release-backed evidence.
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../dashboard/app.js'),'utf8');
const digest='a'.repeat(64),root='https://github.com/doudar/smartspin2k-simulator/releases/download/evidence-12345678901-2/';
const url=id=>`${root}${id}-${digest}.zip`;
class Element{
 constructor(tag){this.tagName=tag;this.children=[];this.events={};this.value='';this._text='';}
 set textContent(value){this._text=String(value);this.children=[];}get textContent(){return this._text+this.children.map(n=>n.textContent).join('');}
 append(...children){for(const child of children){this.children.push(child);if(this.tagName==='select'&&this.children.length===1)this.value=child.value;}}
 replaceChildren(...children){this.children=[];this._text='';this.append(...children);}
 addEventListener(name,handler){this.events[name]=handler;}setAttribute(name,value){this[name]=value;}
}
function harness(index,status=200){
 const nodes={},requests=[],selects=['firmware','test-type','duration','sensitivity','table','history','scenario'];
 const node=id=>nodes[id]||(nodes[id]=new Element(selects.includes(id)?'select':'div'));
 const metadata={experiment:'continuous-long-ride-v1',experiment_duration_min:30,initial_state:'empty',training_run_id:'training'};
 const data={id:'new',metadata,comparison:{status:'complete',experiment:metadata.experiment,runs:[{scenario:'long_ride',seed:7}]},traces:{}};
 const history=[{id:'new',metadata,display_ref:'develop',selections:[{scenario:'long_ride',seed:7}]}];
 const ctx={ChartHover:{init(){},clear(){},update(){}},document:{getElementById:node,createElement:tag=>new Element(tag),createElementNS:(_,tag)=>new Element(tag),addEventListener(){}},location:{hash:''},console,Intl,Date,fetch:async request=>{
  requests.push(request);
  if(request.startsWith('history.json'))return {ok:true,json:async()=>history};
  if(request.startsWith('evidence-index.json'))return {ok:status===200,status,json:async()=>index};
  if(request==='runs/new/data.json')return {ok:true,json:async()=>data};
  return {ok:false,status:404};
 }};
 vm.createContext(ctx);vm.runInContext(source,ctx);return {ctx,nodes,requests};
}
const tick=()=>new Promise(setImmediate);
(async()=>{
 const external=harness({new:url('new'),training:url('training')});await tick();
 assert.equal(external.nodes.downloads.children[0].href,url('new'));
 assert.equal(external.nodes['learning-evidence'].children[0].href,url('training'));
 assert.equal(external.nodes.downloads.children[1].href,'runs/new/comparison.json');
 assert.equal(external.nodes.downloads.children[2].href,'runs/new/SHA256SUMS.txt');
 assert.equal(external.requests.filter(r=>r.startsWith('evidence-index.json')).length,1);
 await vm.runInContext('load()',external.ctx);
 assert.equal(external.requests.filter(r=>r.startsWith('evidence-index.json')).length,1);
 for(const bad of [url('new').replace('github.com','github.com.evil.test'),url('new').replace('doudar/','other/'),url('new').replace('https:','http:'),url('new')+'?x=1',url('new')+'\n',url('new').replace('/new-','/training-'),url('new').replace('evidence-12345678901-2','evidence-12345678901-0'),'javascript:alert(1)']){
  external.ctx.badURL=bad;assert.equal(vm.runInContext('validEvidenceURL("new",badURL)',external.ctx),false,bad);
 }
 assert.throws(()=>vm.runInContext('evidenceURL("../unsafe")',external.ctx),/Invalid evidence identifier/);
 const local=harness({},404);await tick();
 assert.equal(local.nodes.downloads.children[0].href,'runs/new/evidence.zip');
 assert.equal(local.nodes['learning-evidence'].children[0].href,'runs/training/evidence.zip');
 const corrupt=harness({new:'https://evil.test/evidence.zip'});await tick();
 assert.match(corrupt.nodes.notice.textContent,/Invalid evidence URL/);assert.equal(corrupt.nodes.downloads.children.length,0);
 console.log('PASS: Release current/training downloads, once-only index fetch, local compatibility, exact-repository URL validation, and malformed-index rejection');
})().catch(error=>{console.error(error);process.exitCode=1;});
