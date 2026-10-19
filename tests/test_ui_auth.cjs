const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const source=fs.readFileSync(path.join(__dirname,'..','static','app.js'),'utf8');
const authSource=source.slice(source.indexOf('const API_AUTH='),source.indexOf('\nfunction toast'));
const liveSource=source.slice(source.indexOf('async function liveConnect()'),source.indexOf('\nload().then(liveConnect)'));

function harness({saved='',answer='test-api-token',accept='test-api-token',storageFails=false}={}){
 const calls=[],events=[],storage=new Map(saved?[['crewboard-api-token',saved]]:[]);
 let prompts=0;
 const context=vm.createContext({Headers,URLSearchParams,Response,encodeURIComponent,
  localStorage:{getItem:key=>{if(storageFails)throw new Error('disabled');return storage.get(key)||null;},
   setItem:(key,value)=>{if(storageFails)throw new Error('disabled');storage.set(key,value);}},
  window:{prompt:()=>{prompts++;return answer;},EventSource:true},
  fetch:async(url,options)=>{const authorization=options.headers.get('Authorization');calls.push({url,authorization,options});
   return new Response(JSON.stringify({ok:true}),{status:authorization==='Bearer '+accept?200:401});},
  EventSource:class{constructor(url){this.url=url;events.push(this);}addEventListener(){}close(){this.closed=true;}},
  setTimeout:()=>0,liveQueue:()=>{},load:async()=>{}});
 vm.runInContext("const LIVE={es:null,lost:false,full:false};\n"+authSource+'\n'+liveSource+'\n'+
  'globalThis.apiFetch=apiFetch;globalThis.api=api;globalThis.liveConnect=liveConnect;globalThis.auth=API_AUTH;',context);
 return {context,calls,events,storage,prompts:()=>prompts};
}

test('a 401 prompts once and retries with the saved bearer token',async()=>{
 const h=harness();
 const result=await h.context.api('/jobs');
 assert.equal(result.ok,true);
 assert.equal(h.prompts(),1);
 assert.equal(h.calls.length,2);
 assert.equal(h.calls[1].authorization,'Bearer test-api-token');
 assert.equal(h.storage.get('crewboard-api-token'),'test-api-token');
});

test('parallel initial requests share one prompt and all retry',async()=>{
 const h=harness();
 const results=await Promise.all(['/jobs','/assignees','/group_tags'].map(p=>h.context.api(p)));
 assert.ok(results.every(result=>result.ok));
 assert.equal(h.prompts(),1);
 assert.equal(h.calls.length,6);
});

test('a saved token is sent immediately without prompting',async()=>{
 const h=harness({saved:'test-api-token'});
 await h.context.api('/jobs');
 assert.equal(h.calls.length,1);
 assert.equal(h.prompts(),0);
});

test('a rejected token never causes a repeated prompt or retry loop',async()=>{
 const h=harness({answer:'wrong-token'});
 await assert.rejects(h.context.api('/jobs'));
 await assert.rejects(h.context.api('/jobs'));
 assert.equal(h.prompts(),1);
 assert.equal(h.calls.length,3);
});

test('cancelled input is not requested again',async()=>{
 const h=harness({answer:null});
 await assert.rejects(h.context.api('/jobs'));
 await assert.rejects(h.context.api('/jobs'));
 assert.equal(h.prompts(),1);
 assert.equal(h.calls.length,2);
});

test('authentication still works when localStorage is unavailable',async()=>{
 const h=harness({storageFails:true});
 await h.context.api('/jobs');
 await h.context.api('/assignees');
 assert.equal(h.prompts(),1);
 assert.equal(h.calls.at(-1).authorization,'Bearer test-api-token');
});

test('SSE uses an encoded query token after an authenticated probe',async()=>{
 const h=harness({answer:'test+token/&',accept:'test+token/&'});
 await h.context.liveConnect();
 assert.equal(h.prompts(),1);
 assert.equal(h.calls.at(-1).url,'api/rules');
 assert.equal(h.events.length,1);
 assert.equal(h.events[0].url,'api/events?token=test%2Btoken%2F%26');
});

test('trusted-network API and SSE work without prompting or a query token',async()=>{
 const h=harness();
 h.context.fetch=async()=>new Response('{}',{status:200});
 await h.context.api('/jobs');
 await h.context.liveConnect();
 assert.equal(h.prompts(),0);
 assert.equal(h.events[0].url,'api/events');
});

test('WebMCP get_rules uses the same authenticated fetch',async()=>{
 const h=harness();
 const toolsSource=source.slice(source.indexOf('const L3='),source.indexOf('(function registerWebMCP()'));
 vm.runInContext(toolsSource+'\nglobalThis.tools=WEBMCP_TOOLS;',h.context);
 const result=await h.context.tools.find(tool=>tool.name==='get_rules').execute({});
 assert.equal(result.isError,undefined);
 assert.equal(h.prompts(),1);
 assert.equal(h.calls.at(-1).url,'api/rules?format=md');
 assert.equal(h.calls.at(-1).authorization,'Bearer test-api-token');
 assert.equal(h.context.tools.length,21);
});

test('card text and attribute values escape stored XSS payloads',()=>{
 const context=vm.createContext({});
 const cardSource=source.slice(0,source.indexOf('const API_AUTH='))+
  source.slice(source.indexOf('const I='),source.indexOf('\nfunction filtered'));
 vm.runInContext(cardSource+'\nglobalThis.card=card;',context);
 const payload='<img src=x onerror="alert(1)"><script>alert(1)</script>\'&';
 const html=context.card({id:1,title:payload,conditions:payload,tags:[payload],priority:'normal',importance:'normal',
  status:'wait',task_counts:{done:0,doing:0,total:0},tasks:[],current_assignee:payload,assignees:[],sample:false});
 assert.ok(html.includes('&lt;img'));
 assert.ok(html.includes('&quot;alert(1)&quot;'));
 assert.ok(!html.includes('<script>'));
 assert.ok(!html.includes('<img src=x'));
});

test('unchanged textareas preserve original CRLF and leading or trailing newlines',()=>{
 const context=vm.createContext({});
 const line=source.match(/const originalText=.*?;/)[0];
 vm.runInContext(line+'\nglobalThis.originalText=originalText;',context);
 const original='\r\n# raw\r\n```code```\r\n';
 assert.equal(context.originalText(original.replace(/\r\n/g,'\n'),original),original);
 assert.equal(context.originalText('edited\n',original),'edited\n');
});

test('session links display codex URLs safely and never link unsupported schemes',()=>{
 const context=vm.createContext({});
 const escSource=source.slice(source.indexOf('const $='),source.indexOf('\nconst av='));
 const sessionSource=source.slice(source.indexOf('const sessionView='),source.indexOf('\nconst referenceView='));
 vm.runInContext(escSource+'\n'+sessionSource+'\nglobalThis.sessionView=sessionView;',context);
 const html=context.sessionView(['codex://threads/id?x="quoted"&y=1','javascript:alert(1)','data:text/html,<script>x</script>']);
 assert.ok(html.includes('href="codex://threads/id?x=&quot;quoted&quot;&amp;y=1"'));
 assert.ok(!html.includes('href="javascript:'));
 assert.ok(!html.includes('href="data:'));
 assert.ok(!html.includes('<script>'));
 assert.ok(html.includes('rel="noopener noreferrer"'));
});

test('job wait editors use fixed slots and preserve unchanged source newlines',()=>{
 const context=vm.createContext({});
 const escSource=source.slice(source.indexOf('const $='),source.indexOf('\nconst av='));
 const waitSource=source.slice(source.indexOf('const JOB_WAIT_FIELDS='),source.indexOf('\nconst sourceView='));
 vm.runInContext(escSource+'\n'+waitSource+'\nglobalThis.jobWaitFields=jobWaitFields;globalThis.jobWaitValues=jobWaitValues;',context);
 const original={wait_reason:'判断待ち',wait_for:'確認先',wait_note:'\r\n原文\r\n<img src=x>\r\n'};
 const html=context.jobWaitFields(original);
 assert.equal((html.match(/class="job-wait-slot"/g)||[]).length,3);
 assert.equal((html.match(/class="v"/g)||[]).length,3);
 assert.equal((html.match(/class="e inplace"/g)||[]).length,3);
 assert.ok(!html.includes('<img src=x>'));
 const form=new Map(Object.entries(original).map(([key,value])=>[key,value.replace(/\r\n/g,'\n')]));
 const values=context.jobWaitValues(form,original);
 assert.equal(values.wait_note,original.wait_note);
 const css=fs.readFileSync(path.join(__dirname,'..','static','style.css'),'utf8');
 assert.match(css,/\.job-wait-slot\{height:[^}]+\}/);
});

test('overlay scrollbar hides native bars and computes thumb geometry without layout width',()=>{
 const css=fs.readFileSync(path.join(__dirname,'..','static','style.css'),'utf8');
 assert.match(css,/\*\{scrollbar-width:none/);
 assert.match(css,/::-webkit-scrollbar\{width:0;height:0/);
 assert.match(css,/\.osb\{position:fixed[^}]*pointer-events:none/);
 assert.match(css,/\[data-theme=dark\] \.osb\{background:rgba\(/);
 assert.match(css,/\.app\{height:100vh;height:100dvh\}/);
 const osbSource=source.slice(source.indexOf('const OSB='));
 const context=vm.createContext({});
 vm.runInContext(osbSource+'\nglobalThis.OSB=OSB;',context);
 const {geom}=context.OSB;
 assert.equal(geom(500,500,0,496),null);
 const top=geom(500,1000,0,496);assert.equal(top.off,0);assert.equal(top.size,248);
 const end=geom(500,1000,500,496);assert.equal(end.off+end.size,496);
 assert.equal(geom(100,100000,0,96).size,24);
 assert.equal(geom(500,1000,250,496).ratio*(496-248),500);
});
