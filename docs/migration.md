# Job Boardからの情報保持

## 保存設計（task03）

正本は本リポジトリの `app.py` / `db.py` / `static/`。起動は `run.py`、設定は `config.py`。
SQLiteは `CREWBOARD_DATA_DIR/jobs.db`、WAL・外部キー有効。スキーマ更新は起動時の加算的変更のみ。
本番DBをこのブランチで起動して更新してはいけない。

tasksへTEXT列 `wait_reason`, `wait_for`, `wait_note`, `resume_condition`（既定空文字）を追加。
状態にwaitを追加。未割当はnull/空文字の原値を保存し、既定担当を自動設定しない。
先頭の未完了タスクがwaitなら `blocked=true` / `can_start=false`。
未割当も `can_start=false`。先頭を飛ばして後続を実行可能扱いにしない。
waitは未完了なので全件完了には含めず、doneからwaitへ戻すとジョブをrunへ再開する。
再開は明示的な状態変更のみ。待機情報を状態変更で消さない。
既存行・担当者・履歴・マスタにはこの変更で代入しない。

テストは `python -m pip install -r requirements-dev.txt` 後 `python -m pytest tests/ -q`。
UIは `node --test tests/test_ui_auth.cjs`。DBは一時領域、HTTP試験も専用プロセスを使う。
SQLite接続はコンテキスト終了で閉じ、Windowsでもファイルハンドルを残さない。
