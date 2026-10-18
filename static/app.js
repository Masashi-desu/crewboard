'use strict';
const LV={low:'低',normal:'通常',high:'高',urgent:'最優先'}, TS={todo:'未着手',doing:'進行中',done:'完了'}, COLS=['wait','ready','run'];
const S={jobs:[],assignees:[],tags:[],mseg:'assignees',view:'kanban'/* matrix toggle removed; saved prefs ignored */,q:'',prio:'',group:'',who:''};
const $=(s,r=document)=>r.querySelector(s), esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const av=(n,cls='av')=>{const a=S.assignees.find(x=>x.name===n);return a&&a.icon?`<img class="${cls}" src="${esc(String(a.icon).replace(/^\//,''))}" alt="" aria-hidden="true" loading="lazy">`:'';};
const setEd=(el,on)=>{el.classList.toggle('editing',on);el.querySelectorAll('.v').forEach(x=>x.hidden=on);el.querySelectorAll('.e').forEach(x=>x.hidden=!on);};
const pad=n=>String(n).padStart(4,'0'), two=n=>String(n).padStart(2,'0');
async function api(p,o={}){const r=await fetch('api'+p,{headers:{'content-type':'application/json'},...o,body:o.body?JSON.stringify(o.body):undefined});
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
 <h3>${esc(j.title)}</h3>${j.tags.length?`<div class="tags">${j.tags.map(t=>`<span class="tag">${esc(t)}</span>`).join('')}</div>`:''}
 ${j.task_counts.total?bar(j):''}${j.conditions?`<p>${esc(j.conditions)}</p>`:''}</article>`;}
function filtered(list){const q=S.q.toLowerCase();return list.filter(j=>(!S.who||j.assignees.includes(S.who)||(j.tasks||[]).some(t=>t.assignee===S.who))&&(!S.prio||j.priority===S.prio)&&(!S.group||j.group_tag===S.group)&&
  (!q||[j.title,j.conditions,j.policy,j.note].join(' ').toLowerCase().includes(q)));}
function topbar(mode){const groups=S.tags.map(g=>g.name);
 return `<header class="top" role="toolbar" aria-label="ツールバー">  <label class="search">${I.search}<input type="search" id="q" placeholder="タイトル・内容を検索" aria-label="タイトル・内容を検索" value="${esc(S.q)}"></label>
  <select id="prio" aria-label="優先度フィルタ"><option value="">すべての優先度</option>${Object.entries(LV).map(([k,v])=>`<option value="${k}" ${S.prio===k?'selected':''}>優先度 ${v}</option>`).join('')}</select>
  <select id="group" aria-label="グループタグフィルタ"><option value="">グループタグ すべて</option>${groups.map(g=>`<option ${S.group===g?'selected':''}>${esc(g)}</option>`).join('')}</select>
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
 $('#prio').onchange=e=>{S.prio=e.target.value;route();};$('#group').onchange=e=>{S.group=e.target.value;route();};
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
async function renderDetail(id){let j;try{j=await api('/jobs/'+id);}catch(e){$('#main').innerHTML='<div class="empty">ジョブが見つかりません</div>';return;}
 const tc=j.task_counts, byA={};j.tasks.forEach(t=>{byA[t.assignee]=byA[t.assignee]||{done:0,total:0};byA[t.assignee].total++;if(t.status==='done')byA[t.assignee].done++;});
 const asg=S.assignees.map(a=>[a.name,a.name]), link=location.origin+location.pathname+'#/job/'+j.id;
 const sec=(h,name,val,rows)=>`<h2 class="${val?'':'e'}" ${val?'':'hidden'}>${h}</h2><div class="txt v">${esc(val)}</div><textarea class="e inplace txt" name="${name}" rows="${rows}" hidden aria-label="${h}">${esc(val)}</textarea>`;
 const left=`<form id="edit-form" class="jleft"><div class="meta"><span class="badge ${j.status}">${j.status}</span>${meta(j)}<span class="edact">
   <button type="button" class="icon v" id="edit" aria-label="ジョブを編集"><svg viewBox="0 0 24 24"><path d="M12 20h9M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z"/></svg></button>
   <button type="button" class="e sm" id="cancel-edit" hidden>キャンセル</button><button class="e sm primary" hidden>保存</button></span></div>
  <h1 class="v">${esc(j.title)}</h1><textarea class="e inplace h1" name="title" rows="2" required hidden aria-label="タイトル">${esc(j.title)}</textarea>
  <div class="tags ${j.tags.length?'v':''}" ${j.tags.length?'':'hidden'}>${j.tags.map(t=>`<span class="tag">${esc(t)}</span>`).join('')}</div><input class="e inplace tagsin" name="tags" value="${esc(j.tags.join(', '))}" placeholder="タグ（カンマ区切り）" hidden aria-label="タグ">
  <div class="links"><a href="${link}">#${pad(j.id)}</a><button type="button" data-c="${esc(link)}">${I.copy}リンクをコピー</button><button type="button" data-c="${esc(j.title+' '+link)}">${I.copy}名前とリンクをコピー</button></div>
  ${sec('完了条件','conditions',j.conditions,4)}${sec('方針','policy',j.policy,4)}
  <div class="note ${j.note?'':'e'}" ${j.note?'':'hidden'}><b>その他</b><span class="v">${esc(j.note)}</span><textarea class="e inplace" name="note" rows="3" hidden aria-label="その他">${esc(j.note)}</textarea></div></form>`;
 $('#main').innerHTML=`<article class="detail" data-job-id="${j.id}" data-status="${j.status}" aria-label="ジョブ詳細 #${j.id}">
 <div class="dtop"><button onclick="history.length>1?history.back():location.hash='#/'">← 戻る</button>ジョブ</div>
 <section class="panel" aria-label="タスクの進捗"><div class="hd"><span>タスクの進捗</span><span><b>${tc.done}</b> / ${tc.total} 完了</span></div>${bar(j)}
  <div class="chips">${j.tasks.map((t,i)=>`<span class="chip" data-task-id="${t.id}" data-task-status="${t.status}" title="${esc(t.title)}"><span class="dot ${t.status}">${t.status==='done'?'✓':t.status==='doing'?'▶':''}</span>${two(i+1)} ・ ${av(t.assignee)}${esc(t.assignee)} <span style="color:var(--mut)">${TS[t.status]}</span></span>`).join('')||'<span style="color:var(--mut);font-size:12px">タスクはまだありません</span>'}</div>
  <div class="counts" aria-label="担当者別">${Object.entries(byA).map(([a,c])=>`<span data-assignee="${esc(a)}" class="cnt-a">${av(a)}${esc(a)} ${c.done}/${c.total}</span>`).join('')}</div></section>
 <div class="dgrid"><section class="dleft">${left}
  <div class="fields"><label>ステータス${sel('status',[['wait','wait'],['ready','ready'],['run','run'],['done','完了']],j.status,'ステータス','data-job-field')}</label>
   <label>優先度${sel('priority',Object.entries(LV),j.priority,'優先度','data-job-field')}</label><label>重要度${sel('importance',Object.entries(LV).slice(0,3),j.importance,'重要度','data-job-field')}</label>
   <div class="jasg" style="grid-column:1/-1" role="group" aria-label="ジョブ担当者">ジョブ担当<div>${S.assignees.map(a=>`<button class="pill ${j.assignees.includes(a.name)?'on':''}" data-jasg="${esc(a.name)}" aria-pressed="${j.assignees.includes(a.name)}">${av(a.name)}${esc(a.name)}</button>`).join('')}</div></div>
   <span></span><label style="grid-column:span 2">グループタグ${sel('group_tag',[['','グループタグなし'],...S.tags.map(g=>[g.name,g.name])],j.group_tag,'グループタグ','data-job-field')}<a href="#/master" class="mlink" data-mseg="tags">＋ マスタで管理</a></label></div>
  <section class="dz" aria-label="危険ゾーン"><h3><button class="dz-h" id="dz-toggle" aria-expanded="false" aria-controls="dz-body">危険ゾーン<svg class="chev" viewBox="0 0 24 24"><path d="M6 9l6 6 6-6"/></svg></button></h3>
   <div class="dz-wrap" id="dz-body" hidden inert><div class="dz-in"><div class="dz-row"><span>ジョブとタスク・履歴を完全に削除します。</span><button class="danger-outline" id="del-job" data-action="delete-job">このジョブを削除</button></div></div></div></section>
  <details class="hist"><summary>変更履歴 ${j.history.length}</summary><ul>${j.history.map(h=>`<li>${esc(h.at.replace('T',' ').slice(0,16))} — ${esc(h.text)}</li>`).join('')}</ul></details></section>
 <section aria-label="タスク一覧"><div class="tasks-h"><h2>タスク <span class="n">${tc.done} / ${tc.total}</span></h2><button class="addlink" id="add-task" data-action="add-task">＋ 追加</button></div>
  <form class="addform" id="add-form" hidden aria-label="タスクを追加"><input name="title" placeholder="タイトル" aria-label="タスクタイトル" required autocomplete="off"><textarea name="body" rows="2" placeholder="本文（任意）" aria-label="タスク本文" style="flex-basis:100%"></textarea>
   ${sel('assignee',asg,(S.assignees.find(a=>a.kind==='human')||S.assignees[0]||{}).name||'','担当')}${sel('status',Object.entries(TS),'todo','状態')}<button class="primary">追加</button></form>
  <ul style="list-style:none;margin:0;padding:0">${j.tasks.map((t,i)=>`<li class="task ${t.status}" data-task-id="${t.id}" data-task-status="${t.status}" data-assignee="${esc(t.assignee)}" aria-label="タスク ${i+1} ${TS[t.status]} 担当 ${esc(t.assignee)}">
   <div class="thead"><span class="num">${two(i+1)}</span>${sel('status',Object.entries(TS),t.status,'タスク状態')}
   <span class="who">${av(t.assignee)||I.user} 担当：${sel('assignee',asg,t.assignee,'担当')}</span>
   <span class="tidw"><span class="tid">#${pad(j.id)}-#${t.id}</span> <button class="icon" data-c="#${pad(j.id)}-#${t.id}" aria-label="タスクIDをコピー">${I.copy}</button></span></div>
   <form class="tbody" data-task-form="${t.id}" aria-label="タスク ${i+1}"><div class="tline"><b class="ttitle v">${esc(t.title)||'<span style="color:var(--mut)">（タイトルなし）</span>'}</b><input class="e inplace ttitle" name="title" value="${esc(t.title)}" aria-label="タスクタイトル" placeholder="タイトル" hidden>
    <span class="tact"><button type="button" class="addlink v" data-edit-task>編集</button><button type="button" class="addlink e" data-cancel hidden>キャンセル</button><button class="addlink e strong" hidden>保存</button></span></div>
    ${t.body?`<details class="tbd v"><summary>${esc(t.body)}</summary><div class="full">${esc(t.body)}</div></details>`:''}<textarea class="e inplace tbd-in" name="body" rows="2" aria-label="タスク本文" placeholder="本文" hidden>${esc(t.body)}</textarea></form></li>`).join('')}</ul></section></div></article>`;
 const m=$('#main');
 m.querySelectorAll('[data-c]').forEach(b=>b.onclick=()=>copy(b.dataset.c));
 m.querySelectorAll('[data-job-field]').forEach(el=>el.onchange=async()=>{await api('/jobs/'+j.id,{method:'PATCH',body:{[el.name]:el.value}});toast('保存しました');await load();});
 m.querySelectorAll('.task select').forEach(el=>el.onchange=async()=>{await api('/tasks/'+el.closest('.task').dataset.taskId,{method:'PATCH',body:{[el.name]:el.value}});toast('保存しました');await load();});
 m.querySelectorAll('form.tbody').forEach(f=>{f.querySelector('[data-edit-task]').onclick=()=>{setEd(f,true);f.title.focus();};
  f.querySelector('[data-cancel]').onclick=()=>{f.reset();setEd(f,false);};
  f.onsubmit=async e=>{e.preventDefault();await api('/tasks/'+f.dataset.taskForm,{method:'PATCH',body:{title:f.title.value,body:f.body.value}});toast('保存しました');await load();};});
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
 $('#add-form').onsubmit=async e=>{e.preventDefault();const f=e.target;await api(`/jobs/${j.id}/tasks`,{method:'POST',body:{title:f.title.value,body:f.body.value,assignee:f.assignee.value,status:f.status.value}});toast('タスクを追加しました');await load();};
 const ef=$('#edit-form');setEd(ef,editing);
 $('#edit').onclick=()=>{editing=true;setEd(ef,true);ef.title.focus();};$('#cancel-edit').onclick=()=>{editing=false;ef.reset();setEd(ef,false);};
 ef.onsubmit=async e=>{e.preventDefault();const f=new FormData(ef);await api('/jobs/'+j.id,{method:'PATCH',body:{title:f.get('title'),conditions:f.get('conditions'),policy:f.get('policy'),note:f.get('note'),tags:f.get('tags').split(',').map(s=>s.trim()).filter(Boolean)}});editing=false;toast('保存しました');await load();};}
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
 async execute(a){try{const r=await fn(a||{});if(!ro)await load();return ok(r);}catch(e){return {content:[{type:'text',text:'Error: '+e.message}],isError:true};}}});
const R_JOB='ルール: status は wait(着手不可/待ち)/ready(着手可)/run(進行中)/done(完了→完了履歴)。priority low|normal|high|urgent, importance low|normal|high。group_tag はマスタ登録済みのみ。自動完了: 全タスクが完了するとジョブは自動で done になる（自分でジョブのステータスを変える必要はない）。done のジョブに未完了タスクが生じる（タスクを todo/doing に戻す・未完了タスクを追加）と自動で run に戻る。詳細は get_rules。',R_TASK='ルール: タスクは上から順に実行（先頭の未完了タスクの担当=現在の担当）。title必須・body任意。assignee はマスタ(list_assignees)の名前が必須。完了は status=done。全タスクが完了するとジョブは自動で done になる（自分でジョブのステータスを変える必要はない）。done のジョブに未完了タスクが生じる（タスクを todo/doing に戻す・未完了タスクを追加）と自動で run に戻る。詳細は get_rules。';
const WEBMCP_TOOLS=[
 tool('get_rules','Crewboard の運用ルール（日本語 Markdown）。操作前に一度読むこと',{},[],()=>fetch('api/rules?format=md').then(r=>r.text()),true),
 tool('list_jobs','ジョブ一覧（タスク含む。current_assignee=先頭の未完了タスクの担当）。status: wait|ready|run|done',{status:{type:'string',enum:['wait','ready','run','done']},query:{type:'string'}},[],a=>api('/jobs?'+new URLSearchParams(Object.entries({status:a.status||'',q:a.query||''}).filter(e=>e[1]))),true),
 tool('get_job','ジョブ詳細（タスク本文・履歴含む）',{job_id:{type:'integer'}},['job_id'],a=>api('/jobs/'+a.job_id),true),
 tool('create_job','ジョブを作成。conditions=完了条件, policy=方針, note=その他\n'+R_JOB,{title:{type:'string'},status:{type:'string',enum:['wait','ready','run']},priority:P4,importance:L3,tags:{type:'array',items:{type:'string'}},group_tag:{type:'string'},conditions:{type:'string'},policy:{type:'string'},note:{type:'string'}},['title'],a=>api('/jobs',{method:'POST',body:a})),
 tool('update_job','ジョブの項目を更新（指定した項目のみ）\n'+R_JOB,{job_id:{type:'integer'},assignees:{type:'array',items:{type:'string'}},title:{type:'string'},status:{type:'string',enum:['wait','ready','run','done']},priority:P4,importance:L3,tags:{type:'array',items:{type:'string'}},group_tag:{type:'string'},conditions:{type:'string'},policy:{type:'string'},note:{type:'string'}},['job_id'],({job_id,...b})=>api('/jobs/'+job_id,{method:'PATCH',body:b})),
 tool('move_job','ジョブを列移動（wait|ready|run|done）\n'+R_JOB,{job_id:{type:'integer'},status:{type:'string',enum:['wait','ready','run','done']}},['job_id','status'],a=>api('/jobs/'+a.job_id,{method:'PATCH',body:{status:a.status}})),
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
];
(function registerWebMCP(){const mc=navigator.modelContext;window.__jobBoardTools=WEBMCP_TOOLS.map(t=>t.name);if(!mc)return;
 try{if(typeof mc.provideContext==='function')mc.provideContext({tools:WEBMCP_TOOLS});
  else if(typeof mc.registerTool==='function')WEBMCP_TOOLS.forEach(t=>mc.registerTool(t));document.documentElement.dataset.webmcp='on';}catch(e){console.warn('WebMCP registration failed',e);}})();
load();

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
function liveConnect(){if(!window.EventSource)return;try{LIVE.es&&LIVE.es.close();}catch(e){}
 const es=LIVE.es=new EventSource('api/events');
 es.addEventListener('change',e=>{try{liveQueue(JSON.parse(e.data));}catch(x){}});
 es.onopen=()=>{if(LIVE.lost){LIVE.lost=false;LIVE.full=true;liveQueue({type:'resync',scope:'job',job_ids:[]});}};
 es.onerror=()=>{LIVE.lost=true;if(es.readyState===EventSource.CLOSED)setTimeout(()=>{if(LIVE.es===es)liveConnect();},5000);};}
liveConnect();
document.addEventListener('visibilitychange',()=>{if(!document.hidden&&LIVE.es&&LIVE.es.readyState===EventSource.CLOSED)liveConnect();});
