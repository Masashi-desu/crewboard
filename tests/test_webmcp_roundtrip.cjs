const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
const base=process.env.CREWBOARD_TEST_BASE;
test('WebMCP shares schemas and roundtrips all migration fields through REST',{skip:!base},async()=>{
 const source=fs.readFileSync(path.join(__dirname,'..','static','app.js'),'utf8');
 const page=await (await fetch(base+'/')).text();
 const schemas=JSON.parse(page.match(/<script type="application\/json" id="tool-schemas">(.*?)<\/script>/s)[1]);
 const context=vm.createContext({Headers,URLSearchParams,Response,encodeURIComponent,
  document:{querySelector:()=>({textContent:JSON.stringify(schemas)})},
  localStorage:{getItem:()=>process.env.CREWBOARD_TEST_API_TOKEN},window:{prompt:()=>{throw Error('unexpected auth prompt');}},
  fetch:(url,options)=>fetch(base+'/'+url,options),load:async()=>{}});
 const auth=source.slice(source.indexOf('const API_AUTH='),source.indexOf('\nfunction toast'));
 const tools=source.slice(source.indexOf('const L3='),source.indexOf('(function registerWebMCP()'));
 vm.runInContext(auth+'\n'+tools+'\nglobalThis.tools=WEBMCP_TOOLS;',context);
 async function call(name,args){const result=await context.tools.find(t=>t.name===name).execute(args);assert.equal(result.isError,undefined,JSON.stringify(result));return JSON.parse(result.content[0].text);}
 for(const [name,schema] of Object.entries(schemas))assert.deepEqual(JSON.parse(JSON.stringify(context.tools.find(t=>t.name===name).inputSchema)),schema);
 await call('add_group_tag',{name:'Web TagA'});await call('add_group_tag',{name:'Web TagB'});
 const src={system:'web-contract',uuid:'job',number:'#0001',created_at:'2020-01-01T00:00:00+09:00',version:17};
 const job=await call('create_job',{title:'Web contract',status:'ready',sort:-7.5,priority:'urgent',importance:'high',group_tags:['Web TagA','Web TagB'],description:'# raw\r\n',session_urls:['https://example.com/session'],source:src});
 assert.equal(job.sort,-7.5);assert.deepEqual(job.source,src);
 const values={title:'blocked',status:'wait',sort:0.5,priority:'high',importance:'low',assignee:null,description:'**raw**\r\n',wait_reason:'why',wait_for:'reviewer',wait_note:'note',resume_condition:'approval',source:{system:'web-contract',uuid:'task',number:'#0001-01'},source_history:[{id:'wh1',occurred_at:'2020-01-01T00:00:00+09:00',task_uuid:'task',recorder:null,source:'mcp',details:{raw:'原文'}}],session_urls:['https://example.com/task']};
 const task=await call('add_task',{job_id:job.id,...values});
 for(const [key,value] of Object.entries(values))assert.deepEqual(task[key],value);
 const edited=await call('update_task',{task_id:task.id,sort:2.5,priority:'low',importance:'high',wait_note:'changed'});
 assert.equal(edited.sort,2.5);assert.equal(edited.priority,'low');assert.equal(edited.importance,'high');assert.equal(edited.assignee,null);
 const found=await call('list_jobs',{priority:'urgent',group_tags:['Web TagA','Web TagB']});assert.ok(found.some(j=>j.id===job.id));
 await call('move_job',{job_id:job.id,status:'wait',sort:1.25});
 const saved=await call('get_job',{job_id:job.id});assert.equal(saved.sort,1.25);assert.equal(saved.tasks[0].wait_note,'changed');
 const refs=await call('source_refs',{system:'web-contract',uuid:'job'});assert.equal(refs[0].new_id,job.id);
 const invalid=await context.tools.find(t=>t.name==='update_task').execute({task_id:task.id,ignored:1});assert.equal(invalid.isError,true);
 const rules=await call('get_rules',{});assert.ok(rules.includes('未割当'));
});
