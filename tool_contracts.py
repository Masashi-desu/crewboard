"""Use the same typed models for MCP validation and browser JSON schemas."""
from pydantic import create_model
from mcp.server.fastmcp.utilities.func_metadata import ArgModelBase
from schemas import JobCreate, JobPatch, TaskCreate, TaskPatch, JobQuery, JobMove, SourceQuery, MigrationRequest, BatchQuery


class ProvidedArgs(ArgModelBase):
    def model_dump_one_level(self):
        # The SDK normally passes all defaults. Preserve omitted vs explicit null.
        return self.model_dump(exclude_unset=True)


JobUpdate = create_model('JobUpdate', __base__=JobPatch, job_id=(int,...))
TaskAdd = create_model('TaskAdd', __base__=TaskCreate, job_id=(int,...))
TaskUpdate = create_model('TaskUpdate', __base__=TaskPatch, task_id=(int,...))
MODELS = dict(create_job=JobCreate, update_job=JobUpdate, add_task=TaskAdd, update_task=TaskUpdate,
              list_jobs=JobQuery, move_job=JobMove, source_refs=SourceQuery,
              dry_run_migration=MigrationRequest, import_migration=MigrationRequest, get_migration_batch=BatchQuery)


def register(mcp):
    import db
    import migration
    handlers = dict(create_job=db.create_job, update_job=db.update_job, add_task=db.add_task,
                    update_task=db.update_task, move_job=db.move_job,
                    list_jobs=lambda **kw: db.list_jobs(**{'q' if k=='query' else k:v for k,v in kw.items()}),
                    source_refs=db.source_refs, dry_run_migration=lambda payload:migration.dry_run(payload),
                    import_migration=lambda payload:migration.apply(payload),get_migration_batch=migration.get_batch)
    descriptions = dict(create_job='ジョブを作成。priority/importance既定normal。sort省略は末尾。source/source_historyは作成時のみ。',
        update_job='指定したジョブ項目だけ更新。元メタデータは不変。',
        add_task='タスクを追加。waitはブロック、未割当は補完しない。priority/importance既定normal。',
        update_task='指定したタスク項目だけ更新。assignee省略は維持、nullは未割当。',
        list_jobs='ジョブ一覧とタスク。複数group_tagsはAND。queryは本文・旧番号検索。',
        move_job='ジョブの列とsortを変更。sort昇順・同順位はID昇順。',
        source_refs='移管元システムを区別した旧UUID・旧番号と新IDの対応表。',
        dry_run_migration='読み取り専用ドライラン。項目・担当・タグ・参照・重複・予定件数を照合。',
        import_migration='隔離コピー環境のみ。整合バックアップ必須。原子的に取り込み、既存は上書きしない。結果不明時はget_migration_batchを先に呼ぶ。',
        get_migration_batch='バッチ結果照会。404はコミット済み結果が存在しないことを示す。')
    for name, model in MODELS.items():
        args_model = create_model(name+'Arguments', __base__=(model, ProvidedArgs))
        entry = mcp._tool_manager.get_tool(name)
        if entry is None:
            def endpoint(handler, output):
                def call(**values): return handler(**values)
                call.__annotations__['return'] = output
                return call
            entry = mcp._tool_manager.add_tool(endpoint(handlers[name],list if name in ('list_jobs','source_refs') else dict), name=name, description=descriptions[name])
        entry.fn = handlers[name]
        entry.is_async = False
        entry.fn_metadata.arg_model = args_model
        entry.parameters = model.model_json_schema()
        # New tools use unstructured JSON; existing tools retain their result contracts.


def schemas():
    return {name:model.model_json_schema() for name,model in MODELS.items()}
