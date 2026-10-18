"""Explicit, append-only migration contract. No network access or inferred mappings."""
import copy
import hashlib
import json
from pathlib import Path
import sqlite3
import backup
import config
import db


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',',':'), allow_nan=False)


def payload_hash(value):
    return hashlib.sha256(canonical(value).encode('utf-8')).hexdigest()


def map_job_wait_fields(job, reason_labels):
    """Map original Job Board wait fields explicitly, without losing memo text."""
    reason_id = job.get('wait_reason_id')
    if reason_id and reason_id not in reason_labels:
        raise ValueError('unresolved job wait reason: '+str(reason_id))
    return dict(wait_reason=reason_labels[reason_id] if reason_id else '',
                wait_for=job.get('waiting_on') or '', wait_note=job.get('wait_note') or '')


def _batch(c, batch_id):
    row = c.execute('SELECT * FROM migration_batches WHERE batch_id=?', (batch_id,)).fetchone()
    return dict(row) if row else None


def get_batch(batch_id):
    with db.conn() as c: row = _batch(c, batch_id)
    if not row: raise KeyError('batch not found; no committed import exists for this ID')
    return dict(batch_id=batch_id, status=row['status'], payload_hash=row['payload_hash'], result=json.loads(row['result']))


def _prepare(c, payload):
    if not isinstance(payload, dict): raise ValueError('migration payload must be an object')
    allowed = {'batch_id','source_system','jobs','assignee_map','group_tag_map','create_group_tags','expected_counts','backup_path'}
    if set(payload) - allowed: raise ValueError('unknown migration fields: '+str(sorted(set(payload)-allowed)))
    for field in ('batch_id','source_system'):
        if not isinstance(payload.get(field), str) or not payload[field].strip(): raise ValueError(field+' required')
    if not isinstance(payload.get('jobs'), list): raise ValueError('jobs array required')
    errors, warnings, items, mappings, seen = [], [], [], [], set()
    system = payload['source_system']
    known_assignees = {r[0] for r in c.execute('SELECT name FROM assignees')}
    known_tags = {r[0] for r in c.execute('SELECT name FROM group_tags')}
    tag_plan = dict(create=[], reuse=[])
    declarations = payload.get('create_group_tags', [])
    if not isinstance(declarations,list): raise ValueError('create_group_tags must be an array')
    declared = {}
    for spec in declarations:
        if not isinstance(spec,dict) or set(spec)-{'name','color'}:
            errors.append('group tag declaration requires name and optional color'); continue
        name = spec.get('name')
        if not isinstance(name,str) or not name.strip() or name != name.strip():
            errors.append('declared group tag name must be nonempty without surrounding whitespace'); continue
        if 'color' in spec and not isinstance(spec['color'],str):
            errors.append('declared group tag color must be a string'); continue
        if name in declared:
            if declared[name] != spec: errors.append('conflicting group tag declarations: '+name)
            continue
        declared[name] = spec
        existing = c.execute('SELECT color FROM group_tags WHERE name=?',(name,)).fetchone()
        if existing:
            if 'color' in spec and spec['color'] != existing['color']:
                errors.append('existing group tag color conflict: '+name)
            tag_plan['reuse'].append(dict(name=name,color=existing['color']))
        else:
            tag_plan['create'].append(dict(name=name,color=spec.get('color','')))
        known_tags.add(name)
    assignee_map, tag_map = payload.get('assignee_map', {}), payload.get('group_tag_map', {})
    if not isinstance(assignee_map, dict) or not isinstance(tag_map, dict): raise ValueError('mapping objects required')

    def mapping(kind, source_id, source_name, target, known):
        if not isinstance(source_id, str) or not isinstance(source_name, str) or not isinstance(target,str) or target not in known:
            errors.append(f'unresolved {kind}: {source_id}'); return
        existing = c.execute('SELECT source_name,target_name FROM source_master_mappings WHERE system=? AND kind=? AND source_id=?', (system,kind,source_id)).fetchone()
        if existing and list(existing) != [source_name,target]: errors.append(f'mapping conflict: {kind}:{source_id}')
        mappings.append((system,kind,source_id,source_name,target))

    for name, target in assignee_map.items(): mapping('assignee',name,name,target,known_assignees)
    for source_id, spec in tag_map.items():
        if not isinstance(spec,dict) or set(spec) != {'name','target'}:
            errors.append(f'tag mapping requires name and target: {source_id}'); continue
        mapping('group_tag',source_id,spec['name'],spec['target'],known_tags)

    def assignee(value):
        if value is None or value == '': return value
        if not isinstance(value,str) or value not in assignee_map or assignee_map[value] not in known_assignees:
            errors.append('unresolved assignee: '+str(value)); return None
        return assignee_map[value]

    job_fields = {'title','status','priority','importance','sort','description','conditions','policy','note','tags','assignees','group_tags','source','source_history','session_urls','tasks','wait_reason','wait_for','wait_note'}
    task_fields = {'title','body','status','priority','importance','sort','description','assignee','wait_reason','wait_for','wait_note','resume_condition','source','source_history','session_urls'}
    job_required = {'title','status','sort','description','assignees','group_tags','source','tasks'}
    task_required = {'title','status','sort','description','assignee','source'}

    def item(raw, kind, parent=None):
        fields, required = (job_fields,job_required) if kind == 'job' else (task_fields,task_required)
        if not isinstance(raw,dict): errors.append(kind+' must be an object'); return
        missing = required-set(raw)
        if missing: errors.append(f'{kind} missing fields: {sorted(missing)}')
        if set(raw)-fields: errors.append(f'{kind} unknown fields: {sorted(set(raw)-fields)}')
        target = copy.deepcopy(raw); target.pop('tasks',None)
        if not isinstance(target.get('source_history',[]),list):
            errors.append('source_history must be an array'); target['source_history']=[]
        source = target.get('source')
        try:
            if not isinstance(source,dict): raise ValueError('source object required')
            db._validate_source(source)
            if source['system'] != system: raise ValueError('source system mismatch')
            missing_meta = {'created_at','updated_at','completed_at','version'} - set(source)
            if missing_meta: raise ValueError('source metadata missing (use explicit null for unknown): '+str(sorted(missing_meta)))
        except (ValueError,KeyError,TypeError) as error:
            errors.append(str(error)); return
        key = (system,source['uuid'])
        if key in seen: errors.append('duplicate input UUID: '+source['uuid'])
        seen.add(key)
        if not isinstance(target.get('title'),str) or not target['title'].strip(): errors.append('title required')
        if type(target.get('sort')) not in (int,float): errors.append('explicit numeric sort required')
        for field in ('description','body','conditions','policy','note','wait_reason','wait_for','wait_note','resume_condition'):
            if field in target and not isinstance(target[field],str): errors.append(field+' must be a string')
        try:
            if kind == 'job':
                for field,default in (('status','wait'),('priority','normal'),('importance','normal')): db._check(field,target.get(field,default))
                if not isinstance(target.get('assignees',[]),list) or not isinstance(target.get('group_tags',[]),list): raise ValueError('assignees/group_tags must be arrays')
                target['assignees'] = [assignee(value) for value in target.get('assignees',[])]
                if any(value is None or value == '' for value in target['assignees']): errors.append('job assignees must be explicitly mapped names')
                groups = []
                for old_id in target.get('group_tags',[]):
                    if not isinstance(old_id,str) or old_id not in tag_map or not isinstance(tag_map[old_id],dict) or tag_map[old_id].get('target') not in known_tags:
                        errors.append('unresolved group tag: '+str(old_id)); continue
                    groups.append(tag_map[old_id]['target'])
                target['group_tags'] = list(dict.fromkeys(groups))
                target['group_tag'] = groups[0] if groups else ''
            else:
                target['assignee'] = assignee(target.get('assignee'))
                db._check_task({k:target[k] for k in ('status','priority','importance','assignee') if k in target})
            db._urls(target.get('session_urls',[]))
            for event in target.get('source_history',[]):
                if not isinstance(event,dict) or type(event.get('id')) not in (int,str): raise ValueError('history original id required')
                db._timestamp(event.get('occurred_at'))
        except (ValueError,TypeError,KeyError) as error: errors.append(str(error))
        for field in ('priority','importance','source_history','session_urls'):
            if field not in raw: warnings.append(f"{kind} {source['uuid']}: {field} omitted; {'normal' if field in ('priority','importance') else 'empty array'}")
        if kind == 'job' and raw.get('status') == 'wait':
            for field in ('wait_reason','wait_for','wait_note'):
                if field not in raw: warnings.append(f"job {source['uuid']}: {field} omitted; verify original wait information")
        item_hash = payload_hash({'kind':kind,'parent':parent,'original':raw,'target':target})
        existing = c.execute('SELECT * FROM migration_items WHERE system=? AND uuid=?',key).fetchone()
        ref = c.execute('SELECT * FROM source_records WHERE system=? AND uuid=?',key).fetchone()
        if ref and (not existing or existing['payload_hash'] != item_hash): errors.append('existing source conflict: '+source['uuid'])
        current = dict(kind=kind, parent=parent, raw=raw, target=target, hash=item_hash, skip=bool(existing and existing['payload_hash']==item_hash))
        items.append(current)
        if kind == 'job':
            candidates = [r[0] for r in c.execute('SELECT id FROM jobs WHERE title=?',(raw.get('title'),))]
            if candidates: warnings.append(dict(source_uuid=source['uuid'], existing_title_candidates=candidates, action='never merged'))
            children = raw.get('tasks',[])
            if not isinstance(children,list): errors.append('tasks must be an array'); return
            if raw.get('status') == 'done' and any(t.get('status') != 'done' for t in children if isinstance(t,dict)):
                errors.append('done job contains unfinished tasks: '+source['uuid'])
            for task in children: item(task,'task',source['uuid'])

    for job in payload['jobs']: item(job,'job')
    available = {(r['system'],r['uuid']):dict(r) for r in c.execute('SELECT * FROM source_records')}
    for current in items:
        source = current['target']['source']
        available[(system,source['uuid'])] = dict(system=system,uuid=source['uuid'],number=source['number'],kind=current['kind'])
    history_ids = set()
    for current in items:
        source = current['target']['source']
        for reference in source.get('references',[]):
            candidates = [r for r in available.values() if r['system']==reference.get('system',system)
                          and all(r[k]==reference[k] for k in ('uuid','number') if reference.get(k))]
            if len(candidates) != 1: errors.append('unresolved or ambiguous reference: '+canonical(reference))
        for event in current['target'].get('source_history',[]):
            if not isinstance(event,dict) or type(event.get('id')) not in (int,str): continue
            event_id = canonical(event['id'])
            if event_id in history_ids: errors.append('duplicate history id: '+event_id)
            history_ids.add(event_id)
            if not current['skip'] and c.execute('SELECT 1 FROM source_history WHERE system=? AND event_key=?',(system,json.dumps(event['id']))).fetchone(): errors.append('existing history ID conflict: '+event_id)
            for field,kind in (('job_uuid','job'),('task_uuid','task')):
                if event.get(field):
                    if not isinstance(event[field],str): errors.append('history related UUID must be a string'); continue
                    related = available.get((system,event[field]))
                    if not related or related.get('kind', 'job' if related.get('job_id') else 'task') != kind:
                        errors.append('unresolved history relation: '+field+':'+str(event[field]))
    counts = dict(jobs=sum(i['kind']=='job' for i in items),tasks=sum(i['kind']=='task' for i in items),
                  wait=sum(i['kind']=='task' and i['target'].get('status')=='wait' for i in items),
                  unassigned=sum(i['kind']=='task' and not i['target'].get('assignee') for i in items),
                  history=sum(len(i['target'].get('source_history',[])) for i in items))
    if 'expected_counts' in payload and payload['expected_counts'] != counts: errors.append('expected_counts mismatch')
    report = dict(status='invalid' if errors else 'valid', batch_id=payload['batch_id'], errors=errors,warnings=warnings,
                  counts=counts, create=sum(not i['skip'] for i in items),skip=sum(i['skip'] for i in items),group_tags=tag_plan)
    return report,items,mappings


def dry_run(payload):
    with db.conn() as c:
        c.execute('PRAGMA query_only=ON'); c.execute('BEGIN')
        report,_,_ = _prepare(c,payload)
        existing = _batch(c,payload['batch_id'])
        if existing and existing['payload_hash'] != payload_hash({k:v for k,v in payload.items() if k!='backup_path'}):
            report['errors'].append('batch ID already used with different payload'); report['status']='invalid'
        return report


def _insert(c, current, parents):
    target, kind = current['target'],current['kind']
    source = target['source']
    if current['skip']:
        row = c.execute('SELECT job_id,task_id FROM source_records WHERE system=? AND uuid=?',(source['system'],source['uuid'])).fetchone()
        return row[0] if kind=='job' else row[1]
    values = {k:v for k,v in target.items() if k not in ('source','source_history','group_tags')}
    values.setdefault('priority','normal'); values.setdefault('importance','normal')
    values['session_urls'] = db._urls(values.get('session_urls',[]))
    if kind == 'job':
        values['tags'] = json.dumps(values.get('tags',[]),ensure_ascii=False)
        values['assignees'] = json.dumps(values.get('assignees',[]),ensure_ascii=False)
    else: values['job_id'] = parents[current['parent']]
    values['created_at'] = values['updated_at'] = db.now()
    columns = ','.join(values)
    cursor = c.execute(f"INSERT INTO {kind+'s' if kind=='task' else 'jobs'}({columns}) VALUES({','.join('?' for _ in values)})",list(values.values()))
    entity_id = cursor.lastrowid
    if kind == 'job': db._set_groups(c,entity_id,target.get('group_tags',[]))
    db._insert_source(c,kind,entity_id,source)
    db._insert_source_history(c,source,target.get('source_history',[]))
    return entity_id


def apply(payload):
    if not config.MIGRATION_ENABLED: raise ValueError('migration writes disabled; enable only in the isolated copy environment')
    request_hash = payload_hash({k:v for k,v in payload.items() if k!='backup_path'})
    with db.conn() as c:
        c.execute('BEGIN IMMEDIATE')
        existing = _batch(c,payload.get('batch_id'))
        if existing:
            if existing['payload_hash'] != request_hash: raise ValueError('batch ID already used with different payload')
            return json.loads(existing['result'])
        report,items,mappings = _prepare(c,payload)
        if report['errors']: raise ValueError(canonical(report))
        if not payload.get('backup_path'): raise ValueError('verified DB and asset backup_path required')
        try: manifest = backup.verify(payload['backup_path'])
        except (OSError,KeyError,ValueError,sqlite3.Error) as error: raise ValueError('invalid backup: '+str(error)) from error
        if Path(manifest['origin_data_dir']).resolve() != Path(db.DB).resolve().parent or manifest['fingerprint'] != backup.fingerprint(c):
            raise ValueError('backup is not a snapshot of the current DB; take a fresh snapshot')
        if manifest['assets'] != backup.assets(Path(db.DB).resolve().parent): raise ValueError('assets changed since backup')
        batch_id = payload['batch_id']
        c.execute('INSERT INTO migration_batches VALUES(?,?,?,?,?,?)',(batch_id,request_hash,'building',canonical(payload),'{}',db.now()))
        for tag in report['group_tags']['create']:
            c.execute('INSERT INTO group_tags(name,color,sort) VALUES(?,?,(SELECT COALESCE(MAX(sort),0)+1 FROM group_tags))',
                      (tag['name'],tag['color']))
        parents,ids = {},[]
        for current in items:
            entity_id = _insert(c,current,parents)
            source = current['target']['source']
            if current['kind']=='job': parents[source['uuid']]=entity_id
            ids.append(dict(system=source['system'],uuid=source['uuid'],kind=current['kind'],new_id=entity_id))
            if not current['skip']:
                c.execute('INSERT INTO migration_items VALUES(?,?,?,?,?,?)',(source['system'],source['uuid'],batch_id,current['hash'],canonical(current['raw']),canonical(current['target'])))
        for mapping in dict.fromkeys(mappings):
            c.execute('INSERT OR IGNORE INTO source_master_mappings VALUES(?,?,?,?,?)',mapping)
        # Compare each persisted field inside the transaction before committing anything.
        for current,identity in zip(items,ids):
            if current['skip']: continue
            kind,entity_id = current['kind'],identity['new_id']
            row = c.execute(f'SELECT * FROM {"jobs" if kind=="job" else "tasks"} WHERE id=?',(entity_id,)).fetchone()
            saved = db._job(c,row) if kind=='job' else db._task(c,row)
            for field,value in current['target'].items():
                if saved[field] != value: raise ValueError('post-import field mismatch: '+identity['uuid']+':'+field)
        if c.execute('PRAGMA foreign_key_check').fetchone(): raise ValueError('foreign key check failed')
        result = dict(report,status='completed',payload_hash=request_hash,ids=ids,verified=True)
        for job_id in dict.fromkeys(parents.values()): db.migration_audit(c,job_id,batch_id,'一括取り込み・照合完了')
        c.execute("UPDATE migration_batches SET status='completed',result=? WHERE batch_id=?",(canonical(result),batch_id))
    db._emit(dict(type='migration',scope='job',job_ids=list(parents.values())))
    if report['group_tags']['create']: db._emit(dict(type='migration_tags',scope='master',job_ids=[]))
    return result
