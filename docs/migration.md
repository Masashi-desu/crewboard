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

## 複数グループタグ（task04）

`job_group_tags(job_id,name,position)`を加算し、既存group_tagを起動時に登録する。
group_tagsは順序つき配列、group_tagは先頭タグを返す互換フィールド。
単一指定で更新すると1タグへ置換、配列の空指定で解除。両方指定すると先頭一致が必要。
タグ名は前後空白のみ除去、大小文字・Unicode表記は区別し、登録マスタと完全一致。
配列内重複は最初の出現を保持。同名マスタ登録は既存を保持し上書きしない。
旧タグIDと名前は取り込み時に明示対応を指定し、曖昧な正規化・自由tagsへの代替をしない。
RESTは `?group_tags=TagA&group_tags=TagB`、WebMCPは配列、UIは複数選択のAND。
タグ改名は全関連へ反映、削除は該当分類だけ外す。

## 移管元と番号（task05）

ジョブ/タスク作成時の `source={system,uuid,number}` は不変。
`source_records` に(system,uuid)主キーとジョブ/タスクへの排他的外部キーを保存。
新IDは通常どおり採番し、番号・タイトル・サンプルの類似で既存と統合しない。
同一キーの再作成は原子的に失敗し、既存は変更しない。一括取り込みの再試行はtask08で扱う。
`GET api/source_refs?system=Job%20Board&number=%230001` またはuuidで対応表を取得する。
同番号が複数ある場合は全候補を返し、勝手に1件へ決定しない。
UIではシステム名:旧番号とUUIDを併記。検索もこの名前空間付き表示に対応。
通常のIssue番号から依存関係や参照先を自動生成しない。

## 元日時・履歴（task06）

sourceにcreated_at/updated_at/completed_at/versionを保持（省略/null可）。
日時はtimezone付きISO 8601文字列を原文のまま保存し、UTCへ書き換えない。
source.versionは元version。jobs/tasks.version（初期1、更新時加算）は移管先のversion。
`source_history`は作成時の順序付きイベント配列で、原ID、occurred_at、job_uuid/task_uuid、
operation、details、recorder、sourceおよび追加情報をJSON原値で保存。ID・日時は必須。
sourceがui/mcpでも記録者を推測しない。配列順を保存し、同一システムの履歴ID重複は拒否。
取得できなかった履歴の完全性は主張しない。元履歴は変更不可。
source_historyテーブルは移管元専用。既存historyにはcategory（既定operation）とbatch_idを加算。
移管操作はcategory=migrationと独立バッチIDで記録し、UIでも元履歴と別表示。

## 原文・Markdown・URL・旧参照（task07）

jobs/tasksへdescriptionとsession_urls（JSON配列）を加算。既存conditions/policy/note/bodyは保持。
旧descriptionを自動分割しない。CRLF・末尾改行を含む原文はDB/APIで無損失。
表示だけCommonMark（markdown-it-py、HTML無効）へ変換する。コード・改行・リンクを扱い、
危険なリンクを無効化し、画像はaltテキスト表示で外部取得しない。編集には原文を使う。
関連セッションURLはHTTP(S)文字列の配列。保存中にURLへアクセスしない。
source.referencesに明示指定されたuuid/numberのみ対応表で解決し、UIにリンクまたは未解決を表示。
例示・通常のIssue番号から参照や依存エッジを推測しない。元本文自体は書き換えない。
