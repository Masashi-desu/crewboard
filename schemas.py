"""Shared REST/MCP/WebMCP write contracts. Omitted fields differ from explicit null."""
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field

Level = Literal['low','normal','high']
Priority = Literal['low','normal','high','urgent']
JobStatus = Literal['wait','ready','run','done']
TaskStatus = Literal['todo','doing','wait','done']


class StrictIn(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)


class ReferenceIn(StrictIn):
    system: str = Field(default=None)
    uuid: str = Field(default=None)
    number: str = Field(default=None)
    label: str = Field(default=None)


class SourceIn(StrictIn):
    system: str = Field(min_length=1)
    uuid: str = Field(min_length=1)
    number: str = Field(min_length=1)
    created_at: str | None = None
    updated_at: str | None = None
    completed_at: str | None = None
    version: int | None = Field(default=None, ge=0, description='移管元version。移管先versionとは独立。')
    references: list[ReferenceIn] = Field(default_factory=list)


class SourceEvent(StrictIn):
    model_config = ConfigDict(extra='allow', strict=True)
    id: str | int
    occurred_at: str
    job_uuid: str | None = None
    task_uuid: str | None = None
    operation: Any = None
    details: Any = None
    recorder: Any = None
    source: Any = None


class JobPatch(StrictIn):
    title: str = Field(default=None, min_length=1)
    status: JobStatus = Field(default=None)
    priority: Priority = Field(default=None)
    importance: Level = Field(default=None)
    assignees: list[str] = Field(default=None)
    tags: list[str] = Field(default=None)
    group_tag: str = Field(default=None)
    group_tags: list[str] = Field(default=None)
    conditions: str = Field(default=None)
    policy: str = Field(default=None)
    note: str = Field(default=None)
    sort: int | float = Field(default=None, allow_inf_nan=False, description='昇順。同順位は新ID昇順。')
    description: str = Field(default=None)
    session_urls: list[str] = Field(default=None)


class JobCreate(JobPatch):
    title: str = Field(min_length=1)
    status: JobStatus = 'wait'
    priority: Priority = 'normal'
    importance: Level = 'normal'
    source: SourceIn | None = Field(default=None, description='作成時のみ。移管元メタデータは不変。')
    source_history: list[SourceEvent] = Field(default_factory=list, description='作成時のみ。取得順で保存し編集不可。')


class TaskPatch(StrictIn):
    title: str = Field(default=None, min_length=1)
    body: str = Field(default=None)
    status: TaskStatus = Field(default=None)
    assignee: str | None = Field(default=None, description='null/空文字は未割当。省略時は変更しない。')
    priority: Level = Field(default=None)
    importance: Level = Field(default=None)
    sort: int | float = Field(default=None, allow_inf_nan=False)
    wait_reason: str = Field(default=None)
    wait_for: str = Field(default=None)
    wait_note: str = Field(default=None)
    resume_condition: str = Field(default=None)
    description: str = Field(default=None)
    session_urls: list[str] = Field(default=None)


class TaskCreate(TaskPatch):
    title: str = Field(min_length=1)
    status: TaskStatus = 'todo'
    priority: Level = 'normal'
    importance: Level = 'normal'
    source: SourceIn | None = None
    source_history: list[SourceEvent] = Field(default_factory=list)


class JobQuery(StrictIn):
    status: JobStatus = Field(default=None)
    query: str = Field(default=None)
    priority: Priority = Field(default=None)
    group_tag: str = Field(default=None)
    group_tags: list[str] = Field(default=None)


class JobMove(StrictIn):
    job_id: int
    status: JobStatus
    sort: int | float = Field(default=None, allow_inf_nan=False)


class SourceQuery(StrictIn):
    system: str
    uuid: str = Field(default=None)
    number: str = Field(default=None)


class MigrationSource(SourceIn):
    created_at: str | None
    updated_at: str | None
    completed_at: str | None
    version: int | None = Field(ge=0)


class MigrationTask(TaskCreate):
    status: TaskStatus
    sort: int | float = Field(allow_inf_nan=False)
    description: str
    assignee: str | None
    source: MigrationSource


class MigrationJob(JobCreate):
    status: JobStatus
    sort: int | float = Field(allow_inf_nan=False)
    description: str
    assignees: list[str]
    group_tags: list[str]
    source: MigrationSource
    tasks: list[MigrationTask]


class TagMapping(StrictIn):
    name: str
    target: str


class ExpectedCounts(StrictIn):
    jobs: int = Field(ge=0)
    tasks: int = Field(ge=0)
    wait: int = Field(ge=0)
    unassigned: int = Field(ge=0)
    history: int = Field(ge=0)


class MigrationPayload(StrictIn):
    batch_id: str = Field(min_length=1)
    source_system: str = Field(min_length=1)
    jobs: list[MigrationJob]
    assignee_map: dict[str,str] = Field(default_factory=dict)
    group_tag_map: dict[str,TagMapping] = Field(default_factory=dict)
    expected_counts: ExpectedCounts = Field(default=None)
    backup_path: str = Field(default=None)


class MigrationRequest(StrictIn):
    payload: MigrationPayload


class BatchQuery(StrictIn):
    batch_id: str
