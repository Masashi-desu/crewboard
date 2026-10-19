'use strict';
const LV={low:'低',normal:'通常',high:'高',urgent:'最優先'}, TS={todo:'未着手',doing:'進行中',wait:'待機（ブロック中）',done:'完了'}, COLS=['wait','ready','run'];
const S={jobs:[],assignees:[],tags:[],mseg:'assignees',view:'kanban'/* matrix toggle removed; saved prefs ignored */,q:'',prio:'',group:[],who:''};
const $=(s,r=document)=>r.querySelector(s), esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const av=(n,cls='av')=>{const a=S.assignees.find(x=>x.name===n);return a&&a.icon?`<img class="${cls}" src="${esc(String(a.icon).replace(/^\//,''))}" alt="" aria-hidden="true" loading="lazy">`:'';};
const setEd=(el,on)=>{el.classList.toggle('editing',on);el.querySelectorAll('.v').forEach(x=>x.hidden=on);el.querySelectorAll('.e').forEach(x=>x.hidden=!on);};
const pad=n=>String(n).padStart(4,'0'), two=n=>String(n).padStart(2,'0');
const API_AUTH={token:'',prompted:false};
try{API_AUTH.token=localStorage.getItem('crewboard-api-token')||'';}catch(e){}
async function apiFetch(url,o={}){
 const attempted=API_AUTH.token;
 const send=()=>{const headers=new Headers(o.headers);if(API_AUTH.token)headers.set('Authorization','Bearer '+API_AUTH.token);return fetch(url,{...o,headers});};
 let r=await send();
 if(r.status===401){
  if(!API_AUTH.prompted){API_AUTH.prompted=true;const token=window.prompt('Crewboard API トークンを入力してください');
   if(token&&token.trim()){API_AUTH.token=token.trim();try{localStorage.setItem('crewboard-api-token',API_AUTH.token);}catch(e){}}}
  if(API_AUTH.token&&API_AUTH.token!==attempted){r=await send();if(LIVE.es)liveConnect();}
 }
 return r;
}
async function api(p,o={}){const r=await apiFetch('api'+p,{headers:{'content-type':'application/json'},...o,body:o.body?JSON.stringify(o.body):undefined});
  if(!r.ok)throw new Error((await r.json().catch(()=>({}))).detail||r.status);return r.json();}
function toast(m){const t=$('#toast');t.textContent=m;t.classList.add('show');clearTimeout(t._h);t._h=setTimeout(()=>t.classList.remove('show'),1600);}
function copy(text,msg='コピーしました'){navigator.clipboard?.writeText(text).then(()=>toast(msg),()=>toast(text));}
async function load(){[S.jobs,S.assignees,S.tags]=await Promise.all([api('/jobs'),api('/assignees'),api('/group_tags')]);counts();renderAsg();route();}
function counts(){const a=S.jobs.filter(j=>j.status!=='done');$('#cnt-board').textContent=a.length;
  $('#cnt-draft').textContent=a.filter(j=>!j.task_counts.total).length;$('#cnt-done').textContent=S.jobs.length-a.length;}
const I={copy:'<svg viewBox="0 0 24 24"><rect x="9" y="9" width="12" height="12" rx="2"/><path d="M5 15V5a2 2 0 0 1 2-2h10"/></svg>',
 sig:'<svg viewBox="0 0 24 24" style="width:11px;height:11px"><path d="M4 20v-4M10 20v-8M16 20V8"/></svg>',
 wait:'<svg viewBox="0 0 24 24" class="ic-wait"><rect x="6" y="4" width="4" height="16" rx="1"/><rect x="14" y="4" width="4" height="16" rx="1"/></svg>',
 ready:'<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/></svg>',run:'<svg viewBox="0 0 24 24" class="ic-run"><path d="M7 4l12 8-12 8z"/></svg>',
 search:'<svg viewBox="0 0 24 24"><circle cx="11" cy="11" r="7"/><path d="M21 21l-4.3-4.3"/></svg>',user:'<svg viewBox="0 0 24 24" style="width:12px;height:12px"><circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/></svg>'};
const meta=(j,onCard)=>`${onCard?(j.current_assignee?`<span class="cur" data-current-assignee="${esc(j.current_assignee)}" title="現在の担当">${av(j.current_assignee)||I.user}${esc(j.current_assignee)}</span>`:''):j.assignees?.length?`<span data-job-assignees class="jas">${j.assignees.some(n=>av(n))?j.assignees.map(n=>av(n)).join('')+' ':I.user+' '}${j.assignees.map(esc).join(', ')}</span>`:''}<span>${I.sig} 優先度 <span class="lv-${j.priority}">${LV[j.priority]}</span></span><span>重要度 <span class="lv-${j.importance}">${LV[j.importance]}</span></span><span class="id">#${pad(j.id)}</span>${j.sample?'<span class="sample">サンプル</span>':''}`;
const bar=j=>`<div class="bar" role="img" aria-label="タスク ${j.task_counts.done}/${j.task_counts.total} 完了, 進行中 ${j.task_counts.doing}">${(j.tasks||[]).map(t=>`<i class="${t.status}" title="${esc(t.title)}（${esc(t.assignee)}）" data-task-status="${t.status}" data-assignee="${esc(t.assignee)}"></i>`).join('')}</div>`;
function card(j){return `<article class="card" draggable="true" data-job-id="${j.id}" data-status="${j.status}" data-priority="${j.priority}" data-importance="${j.importance}" aria-label="ジョブ #${j.id} ${esc(j.title)}" tabindex="0">
 <div class="meta">${meta(j,true)}</div><button class="icon copy" data-copy="${j.id}" aria-label="リンクをコピー" title="リンクをコピー">${I.copy}</button>
 <h3>${esc(j.title)}</h3>${j.blocked?'<strong class="blocked">待機中・着手不可</strong>':''}${j.tags.length?`<div class="tags">${j.tags.map(t=>`<span class="tag">${esc(t)}</span>`).join('')}</div>`:''}
 ${j.task_counts.total?bar(j):''}${j.conditions?`<p>${esc(j.conditions)}</p>`:''}</article>`;}
function filtered(list){const q=S.q.toLowerCase();return list.filter(j=>(!S.who||j.assignees.includes(S.who)||(j.tasks||[]).some(t=>t.assignee===S.who))&&(!S.prio||j.priority===S.prio)&&S.group.every(g=>(j.group_tags||[]).includes(g))&&
  (!q||[j.title,j.conditions,j.policy,j.note,j.description,j.source?j.source.system+':'+j.source.number:''].join(' ').toLowerCase().includes(q)));}
const DD_OPEN=new Set();
const tagDDLabel=(sel,empty)=>sel.length?sel.join(', '):empty;
const tagDD=(id,names,sel,empty,label)=>{const t=esc(tagDDLabel(sel,empty));return `<details class="tagdd" id="${id}" data-empty="${esc(empty)}"${DD_OPEN.has(id)?' open':''}><summary aria-label="${esc(label)}" title="${t}"><span class="tagdd-l">${t}</span><svg class="chev" viewBox="0 0 24 24"><path d="M6 9l6 6 6-6"/></svg></summary><div class="tagdd-m" role="group" aria-label="${esc(label)}"><label><input type="checkbox" data-all ${sel.length?'':'checked'}>${esc(empty)}</label>${names.map(n=>`<label><input type="checkbox" value="${esc(n)}" ${sel.includes(n)?'checked':''}>${esc(n)}</label>`).join('')}</div></details>`;};
const tagDDValue=(dd,changed)=>{const all=dd.querySelector('[data-all]'),boxes=[...dd.querySelectorAll('input[value]')];if(changed===all){if(all.checked)boxes.forEach(b=>b.checked=false);else if(!boxes.some(b=>b.checked))all.checked=true;}else all.checked=!boxes.some(b=>b.checked);return boxes.filter(b=>b.checked).map(b=>b.value);};
function bindTagDD(dd,onChange){if(!dd)return;dd.ontoggle=()=>{if(dd.open)DD_OPEN.add(dd.id);else DD_OPEN.delete(dd.id);};
 dd.onchange=e=>{const v=tagDDValue(dd,e.target),t=tagDDLabel(v,dd.dataset.empty);dd.querySelector('.tagdd-l').textContent=t;dd.querySelector('summary').title=t;onChange(v);};}
if(typeof document!=='undefined'){document.addEventListener('click',e=>document.querySelectorAll('details.tagdd[open]').forEach(d=>{if(!d.contains(e.target))d.open=false;}));
 document.addEventListener('keydown',e=>{if(e.key==='Escape')document.querySelectorAll('details.tagdd[open]').forEach(d=>{d.open=false;d.querySelector('summary').focus();});});}
function topbar(mode){const groups=S.tags.map(g=>g.name);
 return `<header class="top" role="toolbar" aria-label="ツールバー">  <label class="search">${I.search}<input type="search" id="q" placeholder="タイトル・内容を検索" aria-label="タイトル・内容を検索" value="${esc(S.q)}"></label>
  <select id="prio" aria-label="優先度フィルタ"><option value="">すべての優先度</option>${Object.entries(LV).map(([k,v])=>`<option value="${k}" ${S.prio===k?'selected':''}>優先度 ${v}</option>`).join('')}</select>
  ${tagDD('group',groups,S.group,'すべて','グループタグ ANDフィルタ')}
  <button class="primary" id="new" data-action="create-job"${mode==='done'?' aria-hidden="true" disabled tabindex="-1" style="display:inline-flex;visibility:hidden"':''}>＋ ジョブを作成</button></header>`;}
function renderBoard(mode){const m=$('#main');let list=filtered(S.jobs),body;
 if(mode==='done'||mode==='draft'){list=mode==='done'?list.filter(j=>j.status==='done'):list.filter(j=>j.status!=='done'&&!j.task_counts.total);
  const ttl=mode==='done'?'完了履歴':'仮タスク';
  body=`<section class="joblist" data-list="${mode}" aria-label="${ttl} ${list.length}件">${list.length?list.map(card).join(''):'<div class="empty">ジョブはありません</div>'}</section>`;}
 else if(S.view==='matrix'){list=list.filter(j=>j.status!=='done');const P=['low','normal','high','urgent'],IM=['high','normal','low'];
  body=`<section class="mx" aria-label="マトリクス（横:優先度 縦:重要度）"><div class="mxh"><span class="legend">${COLS.map(c=>`<span>${I[c]}${c==='wait'?'wait':c[0].toUpperCase()+c.slice(1)}</span>`).join('')}</span><span class="hint">ホバー・フォーカスでカード表示、クリックで詳細</span></div>
  <div class="mxw"><div class="ylab">重要度 ↑</div><div class="yax">${IM.map(i=>`<span>${LV[i]}</span>`).join('')}</div>
  <div class="plot"><i class="axx"></i><i class="axy"></i>${IM.map(i=>P.map(p=>`<div class="mcell" data-priority="${p}" data-importance="${i}">${(js=>js.length>1?`<div class="stk" data-count="${js.length}" data-statuses="${js.map(j=>j.status).join(',')}" aria-label="${js.length}件のジョブ">`:'<div class="one">')(list.filter(j=>j.priority===p&&j.importance===i))}${list.filter(j=>j.priority===p&&j.importance===i).map(j=>
   `<div class="bub"><a class="bb ${j.status}" href="#/job/${j.id}" data-job-id="${j.id}" data-status="${j.status}" aria-label="#${j.id} ${esc(j.title)}（${j.status}）">${I[j.status]}</a><div class="pop" role="tooltip">${card(j)}</div></div>`).join('')}</div></div>`).join('')).join('')}</div>
  <div></div><div class="xax">${P.map(p=>`<span>${LV[p]}</span>`).join('')}</div><div></div><div class="xlab">優先度 →</div></div>
  <p class="foot">同じ区画のジョブは同じ優先度・重要度です</p></section>`;}
 else body=`<section class="board" aria-label="カンバン">${COLS.map(c=>{const cs=list.filter(j=>j.status===c);
  return `<section class="col" data-column="${c}" aria-label="${c} 列 ${cs.length}件"><h2>${I[c]}${c==='wait'?'wait':c[0].toUpperCase()+c.slice(1)} <span class="n">${cs.length}</span></h2>
  <div class="colbody">${cs.map(card).join('')||'<div class="empty">ジョブはありません</div>'}</div></section>`}).join('')}</section>`;
 disposeStacks();m.classList.toggle('kb',mode!=='board'||S.view==='kanban');m.innerHTML=topbar(mode)+body;bindBoard();if(S.view==='matrix'&&mode==='board')initStacks();}
function bindBoard(){const m=$('#main');
 m.querySelectorAll('[data-view]').forEach(b=>b.onclick=()=>{S.view=b.dataset.view;localStorage.setItem('jb-view',S.view);route();});
 const q=$('#q');q.oninput=()=>{S.q=q.value;const p=q.selectionStart;route();const n=$('#q');n.focus();n.setSelectionRange(p,p);};
 $('#prio').onchange=e=>{S.prio=e.target.value;route();};bindTagDD($('#group'),v=>{S.group=v;route();});
 $('#new').onclick=()=>{$('#new-form').reset();$('#new-dlg').showModal();};
 m.querySelectorAll('.pop .card').forEach(c=>c.removeAttribute('draggable'));
 m.querySelectorAll('.card').forEach(c=>{c.onclick=e=>{const cp=e.target.closest('[data-copy]');if(cp){e.stopPropagation();copy(location.origin+location.pathname+'#/job/'+cp.dataset.copy,'リンクをコピーしました');return;}location.hash='#/job/'+c.dataset.jobId;};
  c.onkeydown=e=>{if(e.key==='Enter')location.hash='#/job/'+c.dataset.jobId;};
  c.ondragstart=e=>{e.dataTransfer.setData('text/plain',c.dataset.jobId);c.classList.add('dragging');};c.ondragend=()=>c.classList.remove('dragging');});
 m.querySelectorAll('.col').forEach(col=>{col.ondragover=e=>{e.preventDefault();col.classList.add('over');};col.ondragleave=()=>col.classList.remove('over');
  col.ondrop=async e=>{e.preventDefault();col.classList.remove('over');const id=+e.dataTransfer.getData('text/plain');await moveJob(id,col.dataset.column);};});}
async function moveJob(id,status){await api('/jobs/'+id,{method:'PATCH',body:{status}});toast(`#${pad(id)} → ${status}`);await load();}
function sel(name,opts,val,label,attrs=''){return `<select name="${name}" aria-label="${label}" ${attrs}>${opts.map(([k,v])=>`<option value="${esc(k)}" ${k===val?'selected':''}>${esc(v)}</option>`).join('')}</select>`;}
let editing=false;
const WAIT_FIELDS={wait_reason:'待ち理由',wait_for:'待ち先',wait_note:'待ち補足',resume_condition:'再開条件'};
const waitFields=(t,edit=false)=>Object.entries(WAIT_FIELDS).map(([k,label])=>`${edit?`<div class="v">${label}: ${esc(t[k])}</div>`:''}<label class="${edit?'e':''}" ${edit?'hidden':''}>${label}<textarea name="${k}" rows="2">
${esc(t[k]||'')}</textarea></label>`).join('');
const waitValues=f=>Object.fromEntries(Object.keys(WAIT_FIELDS).map(k=>[k,f.elements[k].value]));
const JOB_WAIT_FIELDS={wait_reason:'待ち理由',wait_for:'待ち先',wait_note:'待機メモ'};
const jobWaitFields=j=>`<section class="job-wait" aria-label="ジョブの待機情報">${Object.entries(JOB_WAIT_FIELDS).map(([k,label])=>`<label class="job-wait-field"><span>${label}</span><div class="job-wait-slot"><div class="v">${esc(j[k])}</div><textarea class="e inplace" name="${k}" rows="2" hidden>
${esc(j[k])}</textarea></div></label>`).join('')}</section>`;
const jobWaitValues=(form,j)=>Object.fromEntries(Object.keys(JOB_WAIT_FIELDS).map(k=>[k,originalText(form.get(k),j[k])]));
const originalText=(value,original)=>value===String(original??'').replace(/\r\n?/g,'\n')?original:value;
const sourceView=s=>s?`<div class="source-ref">移管元 ${esc(s.system)}:${esc(s.number)} / UUID ${esc(s.uuid)}<details><summary>元日時・元version</summary>${Object.entries({created_at:'元作成日時',updated_at:'元更新日時',completed_at:'元完了日時',version:'元version'}).map(([k,label])=>`<div>${label}: ${esc(s[k]??'不明')}</div>`).join('')}</details></div>`:'';
const sourceHistoryView=events=>events?.length?`<details><summary>移管元履歴 ${events.length}件（記録者不明は推測しません）</summary>${events.map(h=>`<pre>${esc(JSON.stringify(h,null,2))}</pre>`).join('')}</details>`:'';
const sessionView=urls=>`<div>${(urls||[]).map(u=>/^(https?|codex):\/\//i.test(u)?`<a href="${esc(u)}" target="_blank" rel="noopener noreferrer">${esc(u)}</a>`:esc(u)).join('<br>')}</div>`;
const referenceView=refs=>(refs||[]).map(r=>`<div>旧参照 ${esc(JSON.stringify(r.reference))}: ${r.resolved?r.matches.map(m=>`<a href="#/job/${m.job_id}">${m.kind} #${m.new_id}</a>`).join(''):'未解決または複数候補'}</div>`).join('');
async function renderMarkdown(root){await Promise.all(Array.from(root.querySelectorAll('[data-markdown]'),async el=>{try{const result=await api('/markdown',{method:'POST',body:{text:el.textContent}});el.innerHTML=result.html;}catch(e){/* Escaped source stays readable if rendering fails. */}}));}
async function renderDetail(id){let j;try{j=await api('/jobs/'+id);}catch(e){$('#main').innerHTML='<div class="empty">ジョブが見つかりません</div>';return;}
 const tc=j.task_counts, byA={};j.tasks.forEach(t=>{const a=t.assignee||'未割当';byA[a]=byA[a]||{done:0,total:0};byA[a].total++;if(t.status==='done')byA[a].done++;});
 const asg=[['','未割当'],...S.assignees.map(a=>[a.name,a.name])], link=location.origin+location.pathname+'#/job/'+j.id;
 const sec=(h,name,val,rows)=>`<h2 class="${val?'':'e'}" ${val?'':'hidden'}>${h}</h2><div class="txt v" data-markdown>${esc(val)}</div><textarea class="e inplace txt" name="${name}" rows="${rows}" hidden aria-label="${h}">
${esc(val)}</textarea>`;
 const left=`<form id="edit-form" class="jleft"><div class="meta"><span class="badge ${j.status}">${j.status}</span>${meta(j)}<span>更新version ${j.version}</span><span class="edact">
   <button type="button" class="icon v" id="edit" aria-label="ジョブを編集"><svg viewBox="0 0 24 24"><path d="M12 20h9M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z"/></svg></button>
   <button type="button" class="e sm" id="cancel-edit" hidden>キャンセル</button><button class="e sm primary" hidden>保存</button></span></div>
  <h1 class="v">${esc(j.title)}</h1>${sourceView(j.source)}<textarea class="e inplace h1" name="title" rows="2" required hidden aria-label="タイトル">
${esc(j.title)}</textarea>
  <div class="tags ${j.tags.length?'v':''}" ${j.tags.length?'':'hidden'}>${j.tags.map(t=>`<span class="tag">${esc(t)}</span>`).join('')}</div><input class="e inplace tagsin" name="tags" value="${esc(j.tags.join(', '))}" placeholder="タグ（カンマ区切り）" hidden aria-label="タグ">
  <div class="links"><a href="${link}">#${pad(j.id)}</a><button type="button" data-c="${esc(link)}">${I.copy}リンクをコピー</button><button type="button" data-c="${esc(j.title+' '+link)}">${I.copy}名前とリンクをコピー</button></div>
  ${jobWaitFields(j)}${sec('説明（原文）','description',j.description,4)}${sec('完了条件','conditions',j.conditions,4)}${sec('方針','policy',j.policy,4)}${referenceView(j.resolved_references)}${sessionView(j.session_urls)}<label class="e" hidden>関連セッションURL（1行1件）<textarea name="session_urls">
${esc((j.session_urls||[]).join('\n'))}</textarea></label>
  <div class="note ${j.note?'':'e'}" ${j.note?'':'hidden'}><b>その他</b><span class="v" data-markdown>${esc(j.note)}</span><textarea class="e inplace" name="note" rows="3" hidden aria-label="その他">
${esc(j.note)}</textarea></div></form>`;
 $('#main').innerHTML=`<article class="detail" data-job-id="${j.id}" data-status="${j.status}" aria-label="ジョブ詳細 #${j.id}">
 <div class="dtop"><button onclick="history.length>1?history.back():location.hash='#/'">← 戻る</button>ジョブ</div>
 <section class="panel" aria-label="タスクの進捗"><div class="hd"><span>タスクの進捗</span><span><b>${tc.done}</b> / ${tc.total} 完了</span></div>${bar(j)}
  <div class="chips">${j.tasks.map((t,i)=>`<span class="chip" data-task-id="${t.id}" data-task-status="${t.status}" title="${esc(t.title)}"><span class="dot ${t.status}">${t.status==='done'?'✓':t.status==='doing'?'▶':''}</span>${two(i+1)} ・ ${av(t.assignee)}${esc(t.assignee||'未割当')} <span style="color:var(--mut)">${TS[t.status]}</span></span>`).join('')||'<span style="color:var(--mut);font-size:12px">タスクはまだありません</span>'}</div>
  <div class="counts" aria-label="担当者別">${Object.entries(byA).map(([a,c])=>`<span data-assignee="${esc(a)}" class="cnt-a">${av(a)}${esc(a)} ${c.done}/${c.total}</span>`).join('')}</div></section>
 <div class="dgrid"><section class="dleft">${left}
  <div class="fields"><label>ステータス${sel('status',[['wait','wait'],['ready','ready'],['run','run'],['done','完了']],j.status,'ステータス','data-job-field')}</label>
   <label>優先度${sel('priority',Object.entries(LV),j.priority,'優先度','data-job-field')}</label><label>重要度${sel('importance',Object.entries(LV).slice(0,3),j.importance,'重要度','data-job-field')}</label><label>実施順<input type="number" step="any" name="sort" data-job-field value="${j.sort}"></label>
   <div class="jasg" style="grid-column:1/-1" role="group" aria-label="ジョブ担当者">ジョブ担当<div>${S.assignees.map(a=>`<button class="pill ${j.assignees.includes(a.name)?'on':''}" data-jasg="${esc(a.name)}" aria-pressed="${j.assignees.includes(a.name)}">${av(a.name)}${esc(a.name)}</button>`).join('')}</div></div>
   <span></span><div class="flabel" style="grid-column:span 2">グループタグ（複数選択）${tagDD('job-group-tags',S.tags.map(g=>g.name),j.group_tags||[],'なし','グループタグ')}<a href="#/master" class="mlink" data-mseg="tags">＋ マスタで管理</a></div></div>
  <section class="dz" aria-label="危険ゾーン"><h3><button class="dz-h" id="dz-toggle" aria-expanded="false" aria-controls="dz-body">危険ゾーン<svg class="chev" viewBox="0 0 24 24"><path d="M6 9l6 6 6-6"/></svg></button></h3>
   <div class="dz-wrap" id="dz-body" hidden inert><div class="dz-in"><div class="dz-row"><span>ジョブとタスク・履歴を完全に削除します。</span><button class="danger-outline" id="del-job" data-action="delete-job">このジョブを削除</button></div></div></div></section>
  ${sourceHistoryView(j.source_history)}<details class="hist"><summary>移管先操作履歴 ${j.history.length}</summary><ul>${j.history.map(h=>`<li>${esc(h.at.replace('T',' ').slice(0,16))} [${esc(h.category||'operation')}] ${esc(h.batch_id)} — ${esc(h.text)}</li>`).join('')}</ul></details></section>
 <section aria-label="タスク一覧"><div class="tasks-h"><h2>タスク <span class="n">${tc.done} / ${tc.total}</span></h2><button class="addlink" id="add-task" data-action="add-task">＋ 追加</button></div>
  <form class="addform" id="add-form" hidden aria-label="タスクを追加"><input name="title" placeholder="タイトル" aria-label="タスクタイトル" required autocomplete="off"><textarea name="body" rows="2" placeholder="本文（任意）" aria-label="タスク本文" style="flex-basis:100%"></textarea>
   <textarea name="description" aria-label="説明（原文）" placeholder="説明（原文）"></textarea><textarea name="session_urls" aria-label="関連セッションURL" placeholder="関連セッションURL（1行1件）"></textarea>
   ${sel('assignee',asg,'','担当')}${sel('status',Object.entries(TS),'todo','状態')}${sel('priority',Object.entries(LV).slice(0,3),'normal','タスク優先度')}${sel('importance',Object.entries(LV).slice(0,3),'normal','タスク重要度')}<input name="sort" type="number" step="any" placeholder="実施順（省略可）" aria-label="実施順">${waitFields({})}<button class="primary">追加</button></form>
  <ul style="list-style:none;margin:0;padding:0">${j.tasks.map((t,i)=>`<li class="task ${t.status}" data-task-id="${t.id}" data-task-status="${t.status}" data-assignee="${esc(t.assignee)}" aria-label="タスク ${i+1} ${TS[t.status]} 担当 ${esc(t.assignee)}">
   <div class="thead"><span class="num">${two(i+1)}</span>${sel('status',Object.entries(TS),t.status,'タスク状態')}<label>優先度${sel('priority',Object.entries(LV).slice(0,3),t.priority,'タスク優先度')}</label><label>重要度${sel('importance',Object.entries(LV).slice(0,3),t.importance,'タスク重要度')}</label><label>順序<input type="number" step="any" data-task-order value="${t.sort}" aria-label="タスク実施順"></label>
   <span class="who">${av(t.assignee)||I.user} 担当：${sel('assignee',asg,t.assignee||'','担当')}</span>
   <span class="tidw"><span class="tid">#${pad(j.id)}-#${t.id} / 更新version ${t.version}</span> <button class="icon" data-c="#${pad(j.id)}-#${t.id}" aria-label="タスクIDをコピー">${I.copy}</button></span></div>
   <form class="tbody" data-task-form="${t.id}" aria-label="タスク ${i+1}"><div class="tline"><b class="ttitle v">${esc(t.title)||'<span style="color:var(--mut)">（タイトルなし）</span>'}</b><input class="e inplace ttitle" name="title" value="${esc(t.title)}" aria-label="タスクタイトル" placeholder="タイトル" hidden>
    <span class="tact"><button type="button" class="addlink v" data-edit-task>編集</button><button type="button" class="addlink e" data-cancel hidden>キャンセル</button><button class="addlink e strong" hidden>保存</button></span></div>
    ${t.body?`<details class="tbd v"><summary>${esc(t.body)}</summary><div class="full" data-markdown>${esc(t.body)}</div></details>`:''}<textarea class="e inplace tbd-in" name="body" rows="2" aria-label="タスク本文" placeholder="本文" hidden>
${esc(t.body)}</textarea>
    <div class="v" data-markdown>${esc(t.description)}</div><label class="e" hidden>説明（原文）<textarea name="description">
${esc(t.description)}</textarea></label>${sessionView(t.session_urls)}<label class="e" hidden>関連セッションURL（1行1件）<textarea name="session_urls">
${esc((t.session_urls||[]).join('\n'))}</textarea></label>${referenceView(t.resolved_references)}
    ${sourceView(t.source)}${sourceHistoryView(t.source_history)}${t.status==='wait'?'<strong class="blocked">待機中・着手不可</strong>':''}${waitFields(t,true)}</form></li>`).join('')}</ul></section></div></article>`;
 const m=$('#main');
 m.querySelectorAll('[data-c]').forEach(b=>b.onclick=()=>copy(b.dataset.c));
 m.querySelectorAll('[data-job-field]').forEach(el=>el.onchange=async()=>{await api('/jobs/'+j.id,{method:'PATCH',body:{[el.name]:el.multiple?Array.from(el.selectedOptions,x=>x.value):el.type==='number'?Number(el.value):el.value}});toast('保存しました');await load();});
  bindTagDD(m.querySelector('#job-group-tags'),async v=>{await api('/jobs/'+j.id,{method:'PATCH',body:{group_tags:v}});toast('保存しました');await load();});
 m.querySelectorAll('[data-task-order]').forEach(el=>el.onchange=async()=>{await api('/tasks/'+el.closest('.task').dataset.taskId,{method:'PATCH',body:{sort:Number(el.value)}});await load();});
 m.querySelectorAll('.task select').forEach(el=>el.onchange=async()=>{await api('/tasks/'+el.closest('.task').dataset.taskId,{method:'PATCH',body:{[el.name]:el.value}});toast('保存しました');await load();});
 m.querySelectorAll('form.tbody').forEach(f=>{f.querySelector('[data-edit-task]').onclick=()=>{setEd(f,true);f.title.focus();};
  f.querySelector('[data-cancel]').onclick=()=>{f.reset();setEd(f,false);};
  f.onsubmit=async e=>{e.preventDefault();const original=j.tasks.find(t=>t.id===+f.dataset.taskForm);await api('/tasks/'+f.dataset.taskForm,{method:'PATCH',body:{title:f.title.value,body:originalText(f.body.value,original.body),description:originalText(f.elements.description.value,original.description),session_urls:f.elements.session_urls.value.split('\n').filter(Boolean),...Object.fromEntries(Object.entries(waitValues(f)).map(([k,v])=>[k,originalText(v,original[k])]))}});toast('保存しました');await load();};});
 m.querySelectorAll('[data-jasg]').forEach(b=>b.onclick=async()=>{const n=b.dataset.jasg,cur=j.assignees.includes(n)?j.assignees.filter(x=>x!==n):[...j.assignees,n];await api(`/jobs/${j.id}/assignees`,{method:'PUT',body:{assignees:cur}});toast('保存しました');await load();});
 m.querySelectorAll('.tbd .full').forEach(x=>x.onclick=()=>x.parentElement.open=false);
 m.querySelectorAll('[data-mseg]').forEach(a=>a.onclick=()=>{S.mseg=a.dataset.mseg;});
 $('#del-job').onclick=()=>openDelete(j);
 const dzt=$('#dz-toggle'),dzb=$('#dz-body'),dz=dzt.closest('.dz');
 const setDz=(o,anim=true)=>{dzt.setAttribute('aria-expanded',o);dz.classList.toggle('open',o);
  const motion=anim&&!RM.matches&&dzb.animate;
  if(o){dzb.hidden=false;dzb.removeAttribute('inert');if(motion){const h=dzb.scrollHeight;dzb.animate([{height:'0px',opacity:0},{height:h+'px',opacity:1}],{duration:220,easing:'ease'});}}
  else{dzb.setAttribute('inert','');if(motion){const h=dzb.scrollHeight;dzb.animate([{height:h+'px',opacity:1},{height:'0px',opacity:0}],{duration:200,easing:'ease'}).onfinish=()=>{if(dzt.getAttribute('aria-expanded')!=='true')dzb.hidden=true;};}else dzb.hidden=true;}};
 dzt.onclick=()=>setDz(dzt.getAttribute('aria-expanded')!=='true');
 if(/\/(danger|delete)$/.test(location.hash))setDz(true,false);
 if(/\/delete$/.test(location.hash))openDelete(j);
 $('#add-task').onclick=()=>{const f=$('#add-form');f.hidden=!f.hidden;if(!f.hidden)f.title.focus();};
 $('#add-form').onsubmit=async e=>{e.preventDefault();const f=e.target;await api(`/jobs/${j.id}/tasks`,{method:'POST',body:{title:f.title.value,body:f.body.value,description:f.elements.description.value,session_urls:f.elements.session_urls.value.split('\n').filter(Boolean),assignee:f.assignee.value,status:f.status.value,priority:f.priority.value,importance:f.importance.value,...(f.sort.value===''?{}:{sort:Number(f.sort.value)}),...waitValues(f)}});toast('タスクを追加しました');await load();};
 const ef=$('#edit-form');setEd(ef,editing);
 $('#edit').onclick=()=>{editing=true;setEd(ef,true);ef.title.focus();};$('#cancel-edit').onclick=()=>{editing=false;ef.reset();setEd(ef,false);};
 ef.onsubmit=async e=>{e.preventDefault();const f=new FormData(ef);await api('/jobs/'+j.id,{method:'PATCH',body:{title:originalText(f.get('title'),j.title),description:originalText(f.get('description'),j.description),session_urls:f.get('session_urls').split('\n').filter(Boolean),conditions:originalText(f.get('conditions'),j.conditions),policy:originalText(f.get('policy'),j.policy),note:originalText(f.get('note'),j.note),tags:f.get('tags').split(',').map(s=>s.trim()).filter(Boolean),...jobWaitValues(f,j)}});editing=false;toast('保存しました');await load();};
 await renderMarkdown(m);}
function openDelete(j){const d=$('#del-dlg'),f=$('#del-form'),ok=$('#del-ok');f.reset();ok.disabled=true;
 $('#del-num').textContent='#'+pad(j.id)+' 「'+j.title+'」';$('#del-num2').textContent=String(j.id);
 f.confirm.oninput=()=>{ok.disabled=f.confirm.value.replace(/^#?0*/,'')!==String(j.id);};
 f.onsubmit=async e=>{if(e.submitter?.value!=='ok'||ok.disabled)return;try{await api('/jobs/'+j.id,{method:'DELETE'});toast('削除しました');location.hash='#/';await load();}catch(x){toast(x.message);}};
 if(!d.open)d.showModal();f.confirm.focus();}
function route(){$('#main').classList.remove('kb');const h=location.hash||'#/',mm=h.match(/^#\/job\/(\d+)/);
 document.querySelectorAll('[data-nav]').forEach(a=>a.classList.toggle('on',a.dataset.nav===(h.startsWith('#/master')?'master':h.startsWith('#/done')?'done':h.startsWith('#/draft')?'draft':mm?'':'board')));
 if(mm)renderDetail(+mm[1]);else if(h.startsWith('#/master'))renderMaster();else{editing=false;renderBoard(h.startsWith('#/done')?'done':h.startsWith('#/draft')?'draft':'board');}}
function renderAsg(){}
$('#new-form').onsubmit=async e=>{if(e.submitter?.value!=='ok')return;const f=new FormData(e.target);
 const j=await api('/jobs',{method:'POST',body:{title:f.get('title'),conditions:f.get('conditions'),policy:f.get('policy'),tags:f.get('tags').split(',').map(s=>s.trim()).filter(Boolean)}});await load();toast('作成しました');};
function setTheme(t){document.documentElement.dataset.theme=t;localStorage.setItem('jb-theme',t);document.querySelectorAll('[data-theme-set]').forEach(b=>{b.classList.toggle('on',b.dataset.themeSet===t);b.setAttribute('aria-pressed',b.dataset.themeSet===t);});}
document.querySelectorAll('[data-theme-set]').forEach(b=>b.onclick=()=>setTheme(b.dataset.themeSet));setTheme(document.documentElement.dataset.theme);
addEventListener('hashchange',route);

/* ---- マスタ管理 (segments are data-driven so more can be added) ---- */
const MASTERS={assignees:{label:'担当者',path:'/assignees',list:()=>S.assignees,extra:a=>`${a.kind==='bot'?'Bot':'人'} ・ ジョブ ${a.job_count} ・ 未完了タスク ${a.open_task_count}`,
   field:a=>sel('kind',[['bot','Bot'],['human','人']],a?.kind||'bot','種別'),body:f=>({kind:f.kind.value})},
 tags:{label:'グループタグ',path:'/group_tags',list:()=>S.tags,extra:g=>`ジョブ ${g.job_count}`,
   field:g=>`<input type="color" name="color" value="${esc(g?.color||'#3b82f6')}" aria-label="色">`,body:f=>({color:f.color.value})}};
function renderMaster(){const M=MASTERS[S.mseg],items=M.list(),key=S.mseg;
 $('#main').innerHTML=`<section class="master" aria-label="マスタ管理"><header class="top"><div class="seg" role="tablist" aria-label="マスタ種別">${Object.entries(MASTERS).map(([k,v])=>`<button role="tab" data-seg="${k}" class="${k===key?'on':''}" aria-selected="${k===key}">${v.label}</button>`).join('')}</div></header>
 <form class="mrow madd" id="madd" aria-label="${M.label}を追加"><input name="name" placeholder="新しい${M.label}" aria-label="名前" required>${M.field()}<button class="primary">追加</button></form>
 <ul class="mlist">${items.map(it=>`<li class="mrow" data-master="${key}" data-name="${esc(it.name)}"><form class="mline">
  ${key==='tags'?`<span class="slot"><span class="sw v" style="background:${esc(it.color||'var(--mut)')}"></span><input class="e" type="color" name="color" value="${esc(it.color||'#3b82f6')}" aria-label="色" hidden></span>`
   :`<span class="slot"><label class="avslot" title="クリックでアイコン変更">${av(it.name,'av av-lg')||'<span class="avph e" hidden>＋</span>'}<input type="file" name="icon" accept="image/png,image/jpeg,image/webp,image/svg+xml" hidden></label>${it.icon?'<button type="button" class="avrm e" data-icon-rm aria-label="アイコン削除" title="アイコン削除" hidden>×</button>':''}</span>`}
  <b class="mname v">${esc(it.name)}</b><input class="mname e inplace" name="name" value="${esc(it.name)}" aria-label="名前" required hidden>
  <span class="mx-ex">${key==='assignees'?`<span class="v">${it.kind==='bot'?'Bot':'人'}</span><span class="e" hidden>${sel('kind',[['bot','Bot'],['human','人']],it.kind,'種別','class="inplace"')}</span> ・ `:''}${key==='assignees'?`ジョブ ${it.job_count} ・ 未完了タスク ${it.open_task_count}`:`ジョブ ${it.job_count}`}</span>
  <span class="mact"><button type="button" class="addlink v" data-medit>編集</button><button type="button" class="addlink del v" data-mdel>削除</button><button type="button" class="addlink e" data-mcancel hidden>キャンセル</button><button class="addlink e strong" hidden>保存</button></span></form></li>`).join('')||'<li class="empty">登録がありません</li>'}</ul></section>`;
 const m=$('#main');
 m.querySelectorAll('[data-seg]').forEach(b=>b.onclick=()=>{S.mseg=b.dataset.seg;renderMaster();});
 $('#madd').onsubmit=async e=>{e.preventDefault();const f=e.target;try{await api(M.path,{method:'POST',body:{name:f.name.value.trim(),...M.body(f)}});toast('追加しました');await load();}catch(x){toast(x.message);}};
 m.querySelectorAll('.mrow[data-name]').forEach(li=>{const n=li.dataset.name,f=li.querySelector('form');
  li.querySelector('[data-medit]').onclick=()=>{setEd(f,true);f.name.focus();};
  li.querySelector('[data-mcancel]').onclick=()=>{f.reset();setEd(f,false);};
  const lab=f.querySelector('.avslot');if(lab)lab.onclick=e=>{if(!f.classList.contains('editing'))e.preventDefault();};
  f.onsubmit=async e=>{e.preventDefault();const body={new_name:f.name.value.trim()};if(f.kind)body.kind=f.kind.value;if(f.color)body.color=f.color.value;
   try{await api(M.path+'/'+encodeURIComponent(n),{method:'PATCH',body});toast('保存しました');await load();}catch(x){toast(x.message);}};
  const fi=f.querySelector('input[name=icon]');if(fi)fi.onchange=()=>{const file=fi.files[0];if(!file)return;if(file.size>5e6){toast('5MBまでです');return;}
   const rd=new FileReader();rd.onload=async()=>{try{await api('/assignees/'+encodeURIComponent(n)+'/icon',{method:'PUT',body:{data_base64:rd.result}});toast('アイコンを更新しました');await load();}catch(x){toast(x.message);}};rd.readAsDataURL(file);};
  const ir=f.querySelector('[data-icon-rm]');if(ir)ir.onclick=async()=>{await api('/assignees/'+encodeURIComponent(n)+'/icon',{method:'DELETE'});toast('アイコンを削除しました');await load();};
  li.querySelector('[data-mdel]').onclick=async()=>{if(!confirm(key==='tags'?`「${n}」を削除しますか？使用中のジョブはグループタグなしになります。`:`「${n}」を削除しますか？`))return;
   try{await api(M.path+'/'+encodeURIComponent(n),{method:'DELETE'});toast('削除しました');await load();}catch(x){toast(x.message);}};});}

/* ---- WebMCP (navigator.modelContext) : feature-detected, harmless if absent ---- */
const L3={type:'string',enum:['low','normal','high']},P4={type:'string',enum:['low','normal','high','urgent']};
const ok=d=>({content:[{type:'text',text:JSON.stringify(d,null,1)}]});
const tool=(name,description,props,req,fn,ro)=>({name,description,inputSchema:{type:'object',properties:props,required:req||[]},annotations:ro?{readOnlyHint:true}:undefined,
 async execute(a){try{a=a||{};if(this.inputSchema.additionalProperties===false&&Object.keys(a).some(k=>!Object.hasOwn(this.inputSchema.properties,k)))throw new Error('未対応の項目です');const r=await fn(a);if(!ro)await load();return ok(r);}catch(e){return {content:[{type:'text',text:'Error: '+e.message}],isError:true};}}});
const R_JOB='ルール: status は wait(着手不可/待ち)/ready(着手可)/run(進行中)/done(完了→完了履歴)。priority low|normal|high|urgent, importance low|normal|high。group_tags は登録済み名の配列。複数指定はAND検索。group_tagは先頭タグの互換値。自動完了: 全タスクが完了するとジョブは自動で done になる（自分でジョブのステータスを変える必要はない）。done のジョブに未完了タスクが生じる（タスクを todo/doing/wait に戻す・未完了タスクを追加）と自動で run に戻る。詳細は get_rules。',R_TASK='ルール: タスクは上から順に実行（先頭の未完了タスクの担当=現在の担当）。title必須・body任意。assignee は登録済み名または未割当(null/空文字)。自動補完しない。waitは着手不可。待ち理由・待ち先・補足・再開条件を保持する。完了は status=done。全タスクが完了するとジョブは自動で done になる（自分でジョブのステータスを変える必要はない）。done のジョブに未完了タスクが生じる（タスクを todo/doing/wait に戻す・未完了タスクを追加）と自動で run に戻る。詳細は get_rules。';
const WEBMCP_TOOLS=[
 tool('get_rules','Crewboard の運用ルール（日本語 Markdown）。操作前に一度読むこと',{},[],()=>apiFetch('api/rules?format=md').then(r=>{if(!r.ok)throw new Error(r.status);return r.text();}),true),
 tool('list_jobs','ジョブ一覧（タスク含む。current_assignee=先頭の未完了タスクの担当）。status: wait|ready|run|done',{status:{type:'string',enum:['wait','ready','run','done']},query:{type:'string'},group_tags:{type:'array',items:{type:'string'}}},[],a=>api('/jobs?'+new URLSearchParams([...Object.entries({status:a.status,q:a.query,priority:a.priority,group_tag:a.group_tag}).filter(e=>e[1]!==undefined),...(a.group_tags||[]).map(g=>['group_tags',g])])),true),
 tool('get_job','ジョブ詳細（タスク本文・履歴含む）',{job_id:{type:'integer'}},['job_id'],a=>api('/jobs/'+a.job_id),true),
 tool('create_job','ジョブを作成。conditions=完了条件, policy=方針, note=その他\n'+R_JOB,{title:{type:'string'},status:{type:'string',enum:['wait','ready','run']},priority:P4,importance:L3,tags:{type:'array',items:{type:'string'}},group_tag:{type:'string'},group_tags:{type:'array',items:{type:'string'}},conditions:{type:'string'},policy:{type:'string'},note:{type:'string'}},['title'],a=>api('/jobs',{method:'POST',body:a})),
 tool('update_job','ジョブの項目を更新（指定した項目のみ）\n'+R_JOB,{job_id:{type:'integer'},assignees:{type:'array',items:{type:'string'}},title:{type:'string'},status:{type:'string',enum:['wait','ready','run','done']},priority:P4,importance:L3,tags:{type:'array',items:{type:'string'}},group_tag:{type:'string'},group_tags:{type:'array',items:{type:'string'}},conditions:{type:'string'},policy:{type:'string'},note:{type:'string'}},['job_id'],({job_id,...b})=>api('/jobs/'+job_id,{method:'PATCH',body:b})),
 tool('move_job','ジョブを列移動（wait|ready|run|done）\n'+R_JOB,{job_id:{type:'integer'},status:{type:'string',enum:['wait','ready','run','done']}},['job_id','status'],({job_id,...b})=>api('/jobs/'+job_id,{method:'PATCH',body:b})),
 tool('delete_job','ジョブとそのタスク・履歴を完全削除（元に戻せません）。誤操作防止のため confirm:true が必須',{job_id:{type:'integer'},confirm:{type:'boolean',description:'true を指定した場合のみ削除'}},['job_id','confirm'],a=>{if(a.confirm!==true)throw new Error('confirm:true が必要です');return api('/jobs/'+a.job_id,{method:'DELETE'});}),
 tool('add_task','ジョブにタスク（title, body）を追加\n'+R_TASK,{job_id:{type:'integer'},title:{type:'string'},body:{type:'string'},status:{type:'string',enum:['todo','doing','done']},assignee:{type:'string'}},['job_id','title'],({job_id,...b})=>api(`/jobs/${job_id}/tasks`,{method:'POST',body:b})),
 tool('update_task','タスクの title/body/status/assignee を更新（status=doneで完了）\n'+R_TASK,{task_id:{type:'integer'},title:{type:'string'},body:{type:'string'},status:{type:'string',enum:['todo','doing','done']},assignee:{type:'string'}},['task_id'],({task_id,...b})=>api('/tasks/'+task_id,{method:'PATCH',body:b})),
 tool('get_matrix','マトリクス表示の配置（優先度×重要度ごとのジョブ）。位置変更は update_job の priority/importance',{include_done:{type:'boolean'}},[],a=>api('/matrix'+(a.include_done?'?include_done=true':'')),true),
 tool('assign_job','ジョブ単位の担当者を設定（リスト置換）。ジョブ担当は任意の概要情報、実際の担当はタスクの assignee',{job_id:{type:'integer'},assignees:{type:'array',items:{type:'string'}}},['job_id','assignees'],a=>api(`/jobs/${a.job_id}/assignees`,{method:'PUT',body:{assignees:a.assignees}})),
 tool('list_assignees','担当者一覧（job_count, open_task_count 付き）',{},[],()=>api('/assignees'),true),
 tool('add_assignee','担当者（新しいBot）を追加',{name:{type:'string'},kind:{type:'string',enum:['bot','human']}},['name'],a=>api('/assignees',{method:'POST',body:{name:a.name,kind:a.kind||'bot'}})),
 tool('update_assignee','担当者の名前変更（参照も更新）・種別変更・アイコン設定（icon_url または icon_base64、remove_icon:true で削除）',{name:{type:'string'},new_name:{type:'string'},kind:{type:'string',enum:['bot','human']},icon_url:{type:'string'},icon_base64:{type:'string'},remove_icon:{type:'boolean'}},['name'],async({name,new_name,kind,icon_url,icon_base64,remove_icon})=>{let r=await api('/assignees/'+encodeURIComponent(name),{method:'PATCH',body:{new_name,kind}});const n=new_name||name,u='/assignees/'+encodeURIComponent(n)+'/icon';
  if(remove_icon)r=await api(u,{method:'DELETE'});else if(icon_base64)r=await api(u,{method:'PUT',body:{data_base64:icon_base64}});else if(icon_url)r=await api(u,{method:'PUT',body:{url:icon_url}});return r;}),
 tool('list_group_tags','登録済みグループタグ一覧（name, color, job_count）',{},[],()=>api('/group_tags'),true),
 tool('add_group_tag','グループタグを登録',{name:{type:'string'},color:{type:'string'}},['name'],a=>api('/group_tags',{method:'POST',body:{name:a.name,color:a.color||''}})),
 tool('update_group_tag','グループタグの名前変更（ジョブも更新）・色変更',{name:{type:'string'},new_name:{type:'string'},color:{type:'string'}},['name'],({name,...b})=>api('/group_tags/'+encodeURIComponent(name),{method:'PATCH',body:b})),
 tool('source_refs','移管元を区別して旧UUID/番号から新IDを照会',{system:{type:'string'},uuid:{type:'string'},number:{type:'string'}},['system'],a=>api('/source_refs?'+new URLSearchParams(Object.entries(a))),true),
 tool('dry_run_migration','読み取り専用ドライラン',{payload:{type:'object'}},['payload'],a=>api('/migrations/dry_run',{method:'POST',body:a.payload}),true),
 tool('import_migration','コピー環境のみ。バックアップ必須。結果不明時は先にget_migration_batchを呼ぶ',{payload:{type:'object'}},['payload'],a=>api('/migrations',{method:'POST',body:a.payload})),
 tool('get_migration_batch','コミット済みバッチ結果を照会',{batch_id:{type:'string'}},['batch_id'],a=>api('/migrations/'+encodeURIComponent(a.batch_id)),true),
];
const sharedToolSchemas=typeof document==='undefined'?{}:JSON.parse(document.querySelector('#tool-schemas')?.textContent||'{}');
WEBMCP_TOOLS.forEach(t=>{if(sharedToolSchemas[t.name])t.inputSchema=sharedToolSchemas[t.name];});
(function registerWebMCP(){const mc=navigator.modelContext;window.__jobBoardTools=WEBMCP_TOOLS.map(t=>t.name);if(!mc)return;
 try{if(typeof mc.provideContext==='function')mc.provideContext({tools:WEBMCP_TOOLS});
  else if(typeof mc.registerTool==='function')WEBMCP_TOOLS.forEach(t=>mc.registerTool(t));document.documentElement.dataset.webmcp='on';}catch(e){console.warn('WebMCP registration failed',e);}})();

/* ---- three.js 3D stack for matrix cells with multiple jobs (fallback: CSS overlap) ---- */
let STACKS=[], THREE=null;
const RM=matchMedia('(prefers-reduced-motion: reduce)');
function disposeStacks(){STACKS.forEach(s=>{cancelAnimationFrame(s.raf);s.r.dispose();s.r.forceContextLoss?.();});STACKS=[];}
function hasGL(){try{const c=document.createElement('canvas');return !!(c.getContext('webgl2')||c.getContext('webgl'));}catch(e){return false;}}
async function initStacks(){const els=[...document.querySelectorAll('.stk')];if(!els.length||!hasGL())return;
 try{THREE=THREE||await import('https://cdn.jsdelivr.net/npm/three@0.169.0/build/three.module.min.js');}catch(e){return;}
 const css=getComputedStyle(document.documentElement),col={wait:css.getPropertyValue('--t-doing').trim(),ready:css.getPropertyValue('--mut').trim(),run:css.getPropertyValue('--ac').trim()};
 for(const el of els){if(!el.isConnected)continue;const st=el.dataset.statuses.split(','),W=72,H=72;
  const r=new THREE.WebGLRenderer({alpha:true,antialias:true});r.setPixelRatio(devicePixelRatio);r.setSize(W,H);r.domElement.className='stk3d';r.domElement.setAttribute('aria-hidden','true');
  const sc=new THREE.Scene(),cam=new THREE.PerspectiveCamera(35,1,.1,50);cam.position.set(0,3.2,5.2);cam.lookAt(0,.25,0);
  sc.add(new THREE.AmbientLight(0xffffff,1.6));const dl=new THREE.DirectionalLight(0xffffff,1.6);dl.position.set(2,4,3);sc.add(dl);
  const g=new THREE.Group();st.slice(0,8).forEach((s,i)=>{const m=new THREE.Mesh(new THREE.CylinderGeometry(1,1,.22,48),new THREE.MeshStandardMaterial({color:new THREE.Color(col[s]||'#888'),roughness:.5,metalness:.1}));
   m.position.set(i*.06,i*.3,-i*.04);g.add(m);});g.position.y=-(Math.min(st.length,8)-1)*.15;sc.add(g);
  el.prepend(r.domElement);el.classList.add('gl');const S0={r,raf:0};
  const tick=t=>{g.rotation.y=Math.sin(t/1600)*.35;r.render(sc,cam);if(!RM.matches)S0.raf=requestAnimationFrame(tick);};tick(0);STACKS.push(S0);}}

/* ---- Live updates (SSE): api/events -> debounced partial re-fetch & re-render; never clobbers in-progress edits ---- */
const LIVE={es:null,pend:[],t:0,lost:false,full:false};
function liveBusy(){const m=$('#main'),a=document.activeElement;
 return editing||!!(m&&m.querySelector('.editing'))||!!document.querySelector('dialog[open]')||
  !!(a&&m&&m.contains(a)&&/^(INPUT|TEXTAREA|SELECT)$/.test(a.tagName)&&a.type!=='button'&&a.type!=='submit');}
function liveQueue(ev){LIVE.pend.push(ev);clearTimeout(LIVE.t);LIVE.t=setTimeout(liveFlush,250);}
async function liveFlush(){
 if(liveBusy()){clearTimeout(LIVE.t);LIVE.t=setTimeout(liveFlush,800);return;}   // defer until the edit ends
 const evs=LIVE.pend.splice(0),full=LIVE.full;LIVE.full=false;if(!evs.length&&!full)return;
 const jobEv=full||evs.some(e=>e.scope==='job'),mEv=full||evs.some(e=>e.scope==='master'),ids=new Set(evs.flatMap(e=>e.job_ids||[]));
 try{const [jobs,asg,tags]=await Promise.all([jobEv||mEv?api('/jobs'):null,mEv||jobEv?api('/assignees'):null,mEv?api('/group_tags'):null]);
  if(liveBusy()){LIVE.pend.unshift(...evs);LIVE.full||=full;LIVE.t=setTimeout(liveFlush,800);return;}
  if(jobs)S.jobs=jobs;if(asg)S.assignees=asg;if(tags)S.tags=tags;counts();
  const h=location.hash||'#/',mm=h.match(/^#\/job\/(\d+)/),y=scrollY;
  if(mm){if(full||mEv||ids.has(+mm[1]))await renderDetail(+mm[1]);}
  else if(h.startsWith('#/master')){renderMaster();}
  else route();                                   // board/matrix/完了履歴/仮タスク from S (no reload)
  scrollTo(0,y);
 }catch(e){LIVE.pend.unshift(...evs);LIVE.full||=full;LIVE.t=setTimeout(liveFlush,3000);}}
async function liveConnect(){if(!window.EventSource)return;
 // EventSource hides HTTP status codes; probe with fetch so a 401 can prompt once.
 try{const r=await apiFetch('api/rules');if(!r.ok)return;}catch(e){return;}
 try{LIVE.es&&LIVE.es.close();}catch(e){}
 const es=LIVE.es=new EventSource('api/events'+(API_AUTH.token?'?token='+encodeURIComponent(API_AUTH.token):''));
 es.addEventListener('change',e=>{try{liveQueue(JSON.parse(e.data));}catch(x){}});
 es.onopen=()=>{if(LIVE.lost){LIVE.lost=false;LIVE.full=true;liveQueue({type:'resync',scope:'job',job_ids:[]});}};
 es.onerror=()=>{LIVE.lost=true;if(es.readyState===EventSource.CLOSED)setTimeout(()=>{if(LIVE.es===es)liveConnect();},5000);};}
load().then(liveConnect).catch(e=>toast(e.message));
document.addEventListener('visibilitychange',()=>{if(!document.hidden&&LIVE.es&&LIVE.es.readyState===EventSource.CLOSED)liveConnect();});

/* overlay scrollbar: native bars are hidden in CSS; a thin translucent thumb floats over content (no layout width) */
const OSB=(()=>{
 const geom=(client,scroll,pos,track)=>{if(!(scroll>client+1)||track<=0)return null;const size=Math.min(track,Math.max(24,track*client/scroll));const max=scroll-client;return {size,off:(track-size)*Math.min(1,Math.max(0,pos/max)),ratio:max/Math.max(1,track-size)};};
 if(typeof document==='undefined'||!document.documentElement||typeof getComputedStyle==='undefined')return {geom};
 const bars=new Map(),root=()=>document.scrollingElement||document.documentElement;
 const isDoc=el=>el===root()||el===document.documentElement||el===document.body;
 const canScroll=(el,s)=>(/(auto|scroll)/.test(s.overflowY)&&el.scrollHeight>el.clientHeight+1)||(/(auto|scroll)/.test(s.overflowX)&&el.scrollWidth>el.clientWidth+1);
 const scroller=el=>{for(;el&&el.nodeType===1&&!isDoc(el);el=el.parentElement){if(el.classList.contains('osb'))return null;if(canScroll(el,getComputedStyle(el)))return el;}const d=root();return d&&(d.scrollHeight>d.clientHeight+1||d.scrollWidth>d.clientWidth+1)?d:null;};
 const ro=typeof ResizeObserver==='function'?new ResizeObserver(es=>es.forEach(e=>{const b=bars.get(e.target);if(b)place(e.target,b);})):null;
 const drag=(el,b,axis)=>e=>{if(e.button!==0)return;e.preventDefault();e.stopPropagation();const t=e.currentTarget,start=axis==='y'?e.clientY:e.clientX,pos=axis==='y'?el.scrollTop:el.scrollLeft,g=b['g'+axis];if(!g)return;
  t.classList.add('drag');b.hold=true;try{t.setPointerCapture(e.pointerId);}catch(_){}
  const mv=ev=>{const d=((axis==='y'?ev.clientY:ev.clientX)-start)*g.ratio;if(axis==='y')el.scrollTop=pos+d;else el.scrollLeft=pos+d;};
  const up=()=>{t.classList.remove('drag');b.hold=false;t.removeEventListener('pointermove',mv);t.removeEventListener('pointerup',up);t.removeEventListener('pointercancel',up);show(el);};
  t.addEventListener('pointermove',mv);t.addEventListener('pointerup',up);t.addEventListener('pointercancel',up);};
 const make=el=>{const b={};['y','x'].forEach(a=>{const t=document.createElement('div');t.className='osb osb-'+a;t.setAttribute('aria-hidden','true');t.addEventListener('pointerdown',drag(el,b,a));
  t.addEventListener('pointerenter',()=>{b.over=true;show(el);});t.addEventListener('pointerleave',()=>{b.over=false;show(el);});document.body.appendChild(t);b[a]=t;});
  bars.set(el,b);if(ro&&!isDoc(el))ro.observe(el);return b;};
 const drop=el=>{const b=bars.get(el);if(!b)return;b.x.remove();b.y.remove();clearTimeout(b.timer);if(ro)ro.unobserve(el);bars.delete(el);};
 const place=(el,b)=>{if(!el.isConnected)return drop(el);const doc=isDoc(el),r=doc?{top:0,left:0}:el.getBoundingClientRect(),L=r.left+(doc?0:el.clientLeft),T=r.top+(doc?0:el.clientTop),W=el.clientWidth,H=doc?(window.innerHeight||el.clientHeight):el.clientHeight;
  const gy=b.gy=geom(H,el.scrollHeight,el.scrollTop,H-4),gx=b.gx=geom(doc?(window.innerWidth||W):W,el.scrollWidth,el.scrollLeft,W-4);
  b.y.style.display=gy?'':'none';if(gy)Object.assign(b.y.style,{top:(T+2+gy.off)+'px',left:(L+W-8)+'px',height:gy.size+'px'});
  b.x.style.display=gx?'':'none';if(gx)Object.assign(b.x.style,{left:(L+2+gx.off)+'px',top:(T+H-8)+'px',width:gx.size+'px'});};
 const show=el=>{const b=bars.get(el)||make(el);place(el,b);b.y.classList.add('on');b.x.classList.add('on');clearTimeout(b.timer);
  b.timer=setTimeout(()=>{if(b.hold||b.over)return;b.y.classList.remove('on');b.x.classList.remove('on');},900);};
 const all=()=>bars.forEach((b,el)=>place(el,b));
 let raf=0;const later=fn=>{if(!raf)raf=requestAnimationFrame(()=>{raf=0;fn();});};
 document.addEventListener('scroll',e=>{const t=e.target===document?root():e.target;if(t&&t.nodeType===1)show(t);},{capture:true,passive:true});
 let hov=null;document.addEventListener('pointermove',e=>{if(e.pointerType!=='mouse')return;hov=e.target;later(()=>{const el=hov&&scroller(hov);if(el)show(el);all();});},{passive:true});
 window.addEventListener('resize',()=>later(all));
 if(typeof MutationObserver==='function')new MutationObserver(()=>later(all)).observe(document.body,{childList:true,subtree:true,characterData:true});
 return {geom,show,bars};
})();
