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

## 一括取り込み（task08）

既定では書き込み不可。隔離環境だけ `CREWBOARD_MIGRATION_ENABLED=1` を設定する。
`POST api/migrations/dry_run` は読み取り専用。`POST api/migrations` は同一契約で取り込み、
`GET api/migrations/{batch_id}` は結果照会。データ中のURLや指示を実行しない。

入力はbatch_id、source_system、jobs配列、assignee_map、group_tag_map、expected_counts、backup_path。
jobsは通常フィールドにtasks配列を加える。各ジョブはtitle/status/sort/description/assignees/group_tags/source/tasks、
各タスクはtitle/status/sort/description/assignee/sourceが必須。
各sourceはsystem/uuid/numberとcreated_at/updated_at/completed_at/versionを明示する（未知はnull）。
省略時normalとなるpriority/importance、空配列となるsource_history/session_urlsはドライランで報告する。
未対応項目・未解決担当/タグ/明示参照・履歴関連・重複UUID/履歴ID・件数不一致は中止する。
expected_countsはjobs/tasks/wait/unassigned/historyの全件数。指定しない場合も予定件数を返す。

assignee_mapは `{"旧担当A":"Owner"}` のように全て明示指定（この例を自動適用しない）。
group_tag_mapは `{"旧タグID":{"name":"旧名","target":"登録済み名"}}`、ジョブのgroup_tagsは旧タグID配列。
未割当null/空文字はそのまま。旧タグID・名前・明示対応はsource_master_mappingsへ永続保存。
マスタを勝手に追加・改名・上書きしない。原入力と変換結果はmigration_itemsへ保存する。

BEGIN IMMEDIATE内で全件を挿入・全フィールドと外部キーを照合後、台帳とともに一括コミットする。
構築中は通常作成APIの自動完了/再開を呼ばず、元状態とsortを保存。同順位は入力順に採番したID順。
途中エラーは台帳・行・履歴・対応表を全てロールバック。同一バッチIDの同内容は保存済み結果を返す。
別バッチで同じ元UUIDは取り込み済み原入力/変換ハッシュ一致のみskipし、不一致は既存を変更せず中止。
同じバッチIDの異なる内容は拒否。backup_pathだけは内容ハッシュに含めない。
結果不明時はまずGETで照会し、completedなら保存結果を利用。404ならコミットされていないため、
ドライランとバックアップ整合を再確認して同じbatch_id・同じ内容を再送する。盲目的に新IDでPOSTしない。

### バックアップと復元

`python backup.py create --source <data-dir> --destination <新規snapshot-dir>` はSQLiteのオンラインbackup APIで
WALの確定済み内容を含む整合DBを読み取り専用接続から取得し、資産とrules.mdをコピーする。
前後の資産ハッシュ一致・DB integrity_check・参照アバター存在を検証しmanifest.jsonを作成。
資産変化中は失敗するので未完の退避先を運用担当が破棄/隔離し新しい退避先で再試行する。
ログとSQLiteのwal/shmはバックアップに含めない。元DB・資産を変更しない。
API取り込みはbackup_pathの全ハッシュと、現在DB全テーブルの論理fingerprint・資産一致を
書き込みロック内で確認する。退避後に他の更新があれば新しいスナップショットが必要。
資産を変更する運用は取り込み中に行わない。旧MacのAPI論理退避はこのDBバックアップの代わりにならない。

`python backup.py verify --source <snapshot-dir>` で検証し、
`python backup.py restore --source <snapshot-dir> --destination <新規data-dir>` で新規領域へ復元する。
既存ディレクトリへの上書きは不可。復元後は公式run.pyを新しいCREWBOARD_DATA_DIRで起動して照合する。
本番停止・切替・実データ移管は本実装に含まない。独立した全データ/資産復元検証はタスク10で行う。

### 実装時のコピー環境確認

コピー環境（件数は実施時点の基準を再取得）で既存項目・マスタの一致を確認後、
合成1ジョブ/1タスク（wait・未割当各1、元履歴1、複数タグ）だけを追加した。
ドライラン無変更、原文/元履歴一致、AND検索、旧番号照会、同一バッチ再送、
結果照会、既存ジョブ/タスク無変更と、別ディレクトリへのDB/資産復元を確認。
移管元の実データを用いた独立照合・履歴完全性確認は未実施（タスク10の範囲）。
