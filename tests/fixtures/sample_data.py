"""Reusable sample data and in-memory test doubles for the ORCHESTRA suite.

This module deliberately avoids any heavy or external dependency (no database,
no network, no ML models). It provides:

* **Sample data** — companies, teams, workflows and conversations that mirror
  the shapes the real system produces.
* **Test doubles** — light in-memory fakes for the AI services, repositories
  and engine collaborators, plus an :class:`InMemoryState` store so that
  end-to-end flows can persist state across calls.
* **Builders** — :func:`build_orchestrator` wires a fully in-memory
  :class:`~orchestra.engine.orchestrator.Orchestrator` for e2e/unit testing.

Everything here is intentionally synchronous to construct; async behaviour is
provided by ``async def`` methods on the fakes.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any, Optional


# ===========================================================================
# Sample data
# ===========================================================================
def new_id() -> str:
    """Return a fresh UUID string (ids are treated as opaque strings here)."""

    return str(uuid.uuid4())


SAMPLE_COMPANIES: list[dict[str, Any]] = [
    {"id": new_id(), "name": "Jarir Retail", "industry": "retail", "timezone": "Asia/Riyadh"},
    {"id": new_id(), "name": "Nova Software", "industry": "software", "timezone": "Asia/Riyadh"},
    {"id": new_id(), "name": "Riyadh Events Co", "industry": "events", "timezone": "Asia/Riyadh"},
]


SAMPLE_TEAMS: list[dict[str, Any]] = [
    {"id": new_id(), "name": "Construction", "specialties": ["build", "fit-out", "civil"]},
    {"id": new_id(), "name": "Marketing", "specialties": ["campaign", "signage", "launch"]},
    {"id": new_id(), "name": "IT", "specialties": ["pos", "network", "software", "deploy"]},
    {"id": new_id(), "name": "Logistics", "specialties": ["stock", "delivery", "inventory"]},
]


# A learned workflow is a list of stage templates:
#   {"name", "description", "owner", "depends_on": [names]}
STORE_OPENING_WORKFLOW: dict[str, Any] = {
    "workflow_name": "Retail store opening",
    "industry": "retail",
    "stages": [
        {"name": "Site selection", "description": "Choose and lease the site", "owner": "Logistics", "depends_on": []},
        {"name": "Construction", "description": "Build-out and fit-out", "owner": "Construction", "depends_on": ["Site selection"]},
        {"name": "IT setup", "description": "POS, network, CCTV", "owner": "IT", "depends_on": ["Construction"]},
        {"name": "Stocking", "description": "Receive and shelve inventory", "owner": "Logistics", "depends_on": ["IT setup"]},
        {"name": "Marketing launch", "description": "Signage and opening campaign", "owner": "Marketing", "depends_on": ["Stocking"]},
    ],
}

SOFTWARE_LAUNCH_WORKFLOW: dict[str, Any] = {
    "workflow_name": "Software product launch",
    "industry": "software",
    "stages": [
        {"name": "Requirements", "description": "Gather requirements", "owner": "IT", "depends_on": []},
        {"name": "Design", "description": "Architecture and UX", "owner": "IT", "depends_on": ["Requirements"]},
        {"name": "Development", "description": "Build the product", "owner": "IT", "depends_on": ["Design"]},
        {"name": "QA", "description": "Testing", "owner": "IT", "depends_on": ["Development"]},
        {"name": "Release", "description": "Ship to production", "owner": "IT", "depends_on": ["QA"]},
    ],
}

EVENT_PLANNING_WORKFLOW: dict[str, Any] = {
    "workflow_name": "Event planning",
    "industry": "events",
    "stages": [
        {"name": "Venue booking", "description": "Reserve the venue", "owner": "Logistics", "depends_on": []},
        {"name": "Catering", "description": "Arrange food", "owner": "Logistics", "depends_on": ["Venue booking"]},
        {"name": "Promotion", "description": "Market the event", "owner": "Marketing", "depends_on": ["Venue booking"]},
        {"name": "Execution", "description": "Run the event", "owner": "Marketing", "depends_on": ["Catering", "Promotion"]},
    ],
}


SAMPLE_CONVERSATIONS: dict[str, str] = {
    "store_opening": (
        "We're opening a new retail store in Riyadh. First we pick and lease the "
        "site, then construction and fit-out, then IT sets up POS and network, "
        "then we stock the shelves, and finally marketing runs the launch campaign."
    ),
    "software_launch": (
        "We are launching a new software product. Gather requirements, do the "
        "design, then development, QA testing, and finally release to production."
    ),
    "event_planning": (
        "Planning a corporate event. Book the venue, arrange catering, promote it, "
        "then execute the event on the day."
    ),
}


# A mock voice-note payload (bytes stand in for an .ogg/.opus file). The Whisper
# service is always mocked in tests, so the content is irrelevant.
SAMPLE_VOICE_NOTE_BYTES: bytes = b"RIFF....FAKE-OGG-OPUS-VOICE-NOTE-CONTENT...."
SAMPLE_VOICE_TRANSCRIPT: str = "خلصنا مرحلة البناء"  # "We finished the construction stage"


def make_stage(
    name: str,
    *,
    status: str = "pending",
    sequence: int = 0,
    team_id: Optional[str] = None,
    depends_on: Optional[list[str]] = None,
    stage_id: Optional[str] = None,
    deadline: Any = None,
    completed_at: Any = None,
) -> dict[str, Any]:
    """Return a normalised stage dict of the shape the StateMachine consumes."""

    return {
        "id": stage_id or new_id(),
        "name": name,
        "status": status,
        "sequence": sequence,
        "team_id": team_id,
        "depends_on": list(depends_on or []),
        "deadline": deadline,
        "completed_at": completed_at,
    }


def make_project(
    *,
    name: str = "Test Project",
    company_id: Optional[str] = None,
    status: str = "active",
    metadata: Optional[dict[str, Any]] = None,
    opening_date: Any = None,
) -> SimpleNamespace:
    """Return a project record with attribute access (mimics the ORM model)."""

    return SimpleNamespace(
        id=new_id(),
        name=name,
        company_id=company_id or new_id(),
        status=status,
        metadata_=dict(metadata or {}),
        opening_date=opening_date,
        current_stage=None,
    )


# ===========================================================================
# Fake AI services
# ===========================================================================
class FakeLLM:
    """A deterministic stand-in for :class:`LLMService`.

    ``extract_workflow`` returns a workflow keyed off the injected ``workflow``
    (defaulting to the store-opening workflow). All other methods return
    canned, inspectable values and record their calls.
    """

    def __init__(self, workflow: Optional[dict[str, Any]] = None, reply: str = "OK, understood.") -> None:
        self._workflow = workflow or STORE_OPENING_WORKFLOW
        self._reply = reply
        self.calls: list[tuple[str, Any]] = []
        self.intent: dict[str, Any] = {"intent": "natural_language", "entities": {}}
        self.suggestions: list[dict[str, Any]] = []

    def extract_workflow(self, conversation: str) -> dict[str, Any]:
        self.calls.append(("extract_workflow", conversation))
        return {
            "workflow_name": self._workflow.get("workflow_name"),
            "stages": [dict(s) for s in self._workflow.get("stages", [])],
        }

    def understand_intent(self, message: str) -> dict[str, Any]:
        self.calls.append(("understand_intent", message))
        return dict(self.intent)

    def generate_response(self, context: str, project: Optional[dict[str, Any]] = None) -> str:
        self.calls.append(("generate_response", context))
        return self._reply

    def summarize_conversation(self, messages: list[Any]) -> str:
        self.calls.append(("summarize_conversation", messages))
        return "summary"

    def chat(self, prompt: str, *args: Any, **kwargs: Any) -> str:
        self.calls.append(("chat", prompt))
        return self._reply

    def _chat_json(self, prompt: str, system: str, temperature: float = 0.2) -> dict[str, Any]:
        self.calls.append(("_chat_json", prompt))
        return {"suggestions": list(self.suggestions)}


class FakeWhisper:
    """Whisper transcription stub."""

    def __init__(self, transcript: str = SAMPLE_VOICE_TRANSCRIPT) -> None:
        self.transcript = transcript
        self.calls: list[str] = []

    def transcribe(self, audio_path: str, language: Optional[str] = None) -> str:
        self.calls.append(audio_path)
        return self.transcript

    def transcribe_whatsapp_voice(self, media_url: str, language: Optional[str] = None) -> str:
        self.calls.append(media_url)
        return self.transcript


# ===========================================================================
# In-memory persistence + repository / manager fakes
# ===========================================================================
class InMemoryState:
    """A tiny in-memory database shared by the repository/manager fakes."""

    def __init__(self) -> None:
        self.projects: dict[str, SimpleNamespace] = {}
        self.stages: dict[str, list[dict[str, Any]]] = {}  # project_id -> stages
        self.workflows: dict[str, SimpleNamespace] = {}
        self.tasks: dict[str, SimpleNamespace] = {}
        self.escalations: list[SimpleNamespace] = []
        self.messages: list[dict[str, Any]] = []
        self.sessions: dict[str, SimpleNamespace] = {}  # group_id -> session
        self.notifications: list[dict[str, Any]] = []

    def stage_by_id(self, stage_id: Any) -> Optional[dict[str, Any]]:
        for stages in self.stages.values():
            for stage in stages:
                if str(stage["id"]) == str(stage_id):
                    return stage
        return None


class FakeWorkflowRepo:
    def __init__(self, state: InMemoryState) -> None:
        self.state = state

    async def get_workflow(self, workflow_id: Any) -> Any:
        return self.state.workflows[str(workflow_id)]

    async def get_workflows_by_company(self, company_id: Any) -> list[Any]:
        return [w for w in self.state.workflows.values() if str(w.company_id) == str(company_id)]

    async def create_workflow(self, data: dict[str, Any]) -> Any:
        record = SimpleNamespace(
            id=new_id(),
            company_id=data.get("company_id"),
            name=data.get("name"),
            stages=list(data.get("stages", [])),
            confidence=data.get("confidence", 0.0),
            usage_count=0,
            metadata_=data.get("metadata_", {}),
        )
        self.state.workflows[str(record.id)] = record
        return record

    async def update_workflow(self, workflow_id: Any, values: dict[str, Any]) -> Any:
        record = self.state.workflows[str(workflow_id)]
        for key, value in values.items():
            setattr(record, key, value)
        return record

    async def increment_usage_count(self, workflow_id: Any) -> Any:
        record = self.state.workflows[str(workflow_id)]
        record.usage_count = int(getattr(record, "usage_count", 0)) + 1
        return record


class FakeProjectRepo:
    def __init__(self, state: InMemoryState) -> None:
        self.state = state

    async def create_project(self, data: dict[str, Any]) -> Any:
        project = SimpleNamespace(
            id=new_id(),
            name=data.get("name"),
            company_id=data.get("company_id"),
            status="draft",
            metadata_=dict(data.get("metadata_", {})),
            opening_date=data.get("opening_date"),
            current_stage=None,
            workflow_id=data.get("workflow_id"),
        )
        self.state.projects[str(project.id)] = project
        self.state.stages.setdefault(str(project.id), [])
        return project

    async def get_project(self, project_id: Any) -> Any:
        return self.state.projects[str(project_id)]

    async def update(self, project_id: Any, values: dict[str, Any]) -> Any:
        project = self.state.projects[str(project_id)]
        for key, value in values.items():
            setattr(project, key, value)
        return project

    async def update_project_status(self, project_id: Any, status: Any, *, current_stage: Optional[str] = None) -> Any:
        project = self.state.projects[str(project_id)]
        project.status = getattr(status, "value", status)
        if current_stage is not None:
            project.current_stage = current_stage
        return project

    async def get_active_projects(self, company_id: Optional[Any] = None) -> list[Any]:
        return [
            p for p in self.state.projects.values()
            if company_id is None or str(p.company_id) == str(company_id)
        ]

    async def add_project_stage(self, project_id: Any, data: dict[str, Any]) -> Any:
        stages = self.state.stages.setdefault(str(project_id), [])
        depends_on = (data.get("metadata_") or {}).get("depends_on", [])
        stage = make_stage(
            data.get("name", f"Stage {len(stages) + 1}"),
            sequence=data.get("sequence", len(stages)),
            depends_on=list(depends_on),
        )
        stages.append(stage)
        return SimpleNamespace(**stage)

    async def get_stages(self, project_id: Any) -> list[dict[str, Any]]:
        return [dict(s) for s in self.state.stages.get(str(project_id), [])]

    async def complete_stage(self, stage_id: Any) -> Any:
        stage = self.state.stage_by_id(stage_id)
        if stage is not None:
            stage["status"] = "completed"
        return stage


class FakeTaskRepo:
    def __init__(self, state: InMemoryState) -> None:
        self.state = state

    async def complete_task(self, task_id: Any) -> Any:
        task = self.state.tasks.get(str(task_id))
        if task is not None:
            task.status = "completed"
        return task

    async def get_tasks_by_project(self, project_id: Any) -> list[Any]:
        return [t for t in self.state.tasks.values() if str(getattr(t, "project_id", "")) == str(project_id)]


class FakeProjectManager:
    """Store-backed stand-in for :class:`ProjectManager`."""

    def __init__(self, state: InMemoryState, project_repo: FakeProjectRepo, task_repo: FakeTaskRepo) -> None:
        self.state = state
        self.project_repo = project_repo
        self.task_repo = task_repo

    async def create_project(self, name: str, description: Optional[str] = None, industry: Optional[str] = None,
                             group_id: Optional[str] = None, sender: Optional[str] = None, *,
                             company_id: Optional[Any] = None, workflow_id: Optional[Any] = None,
                             location: Optional[str] = None) -> Any:
        metadata = {k: v for k, v in {"industry": industry, "group_id": group_id, "created_by": sender}.items() if v is not None}
        return await self.project_repo.create_project(
            {"company_id": company_id, "name": name, "description": description,
             "metadata_": metadata, "workflow_id": workflow_id}
        )

    async def get_project(self, project_id: Any) -> dict[str, Any]:
        project = self.state.projects[str(project_id)]
        return {
            "project": project,
            "stages": [dict(s) for s in self.state.stages.get(str(project_id), [])],
            "tasks": await self.task_repo.get_tasks_by_project(project_id),
        }

    async def update_project_status(self, project_id: Any, status: Any, *, current_stage: Optional[str] = None) -> Any:
        return await self.project_repo.update_project_status(project_id, status, current_stage=current_stage)


class FakeTaskManager:
    def __init__(self, state: InMemoryState, teams: Optional[list[dict[str, Any]]] = None) -> None:
        self.state = state
        self.teams = teams or SAMPLE_TEAMS

    async def get_task(self, task_id: Any) -> Any:
        return self.state.tasks[str(task_id)]

    async def create_task(self, project_id: Any, description: str, assigned_team: Optional[Any] = None) -> Any:
        task = SimpleNamespace(
            id=new_id(),
            title=description[:60],
            description=description,
            project_id=project_id,
            assigned_team=assigned_team,
            status="pending",
        )
        self.state.tasks[str(task.id)] = task
        return task

    async def auto_assign_task(self, description: str, company_id: Optional[Any] = None) -> Any:
        text = description.lower()
        for team in self.teams:
            if any(word in text for word in team.get("specialties", [])):
                return SimpleNamespace(id=team["id"], name=team["name"])
        return SimpleNamespace(id=self.teams[0]["id"], name=self.teams[0]["name"]) if self.teams else None


class FakeTeamCoordinator:
    def __init__(self, state: InMemoryState) -> None:
        self.state = state

    async def notify_team(self, team_id: Any, message: str) -> dict[str, Any]:
        self.state.notifications.append({"to": str(team_id), "message": message, "kind": "team"})
        return {"delivered": True}

    async def notify_ceo(self, project_id: Any, message: str) -> dict[str, Any]:
        self.state.notifications.append({"to": "ceo", "project_id": str(project_id), "message": message, "kind": "ceo"})
        return {"delivered": True}

    async def send_welcome_message(self, group_id: str, project_id: Any) -> dict[str, Any]:
        self.state.notifications.append({"to": group_id, "project_id": str(project_id), "kind": "welcome"})
        return {"delivered": True}


class FakeEscalationRepo:
    def __init__(self, state: InMemoryState) -> None:
        self.state = state

    async def create_escalation(self, data: dict[str, Any]) -> Any:
        record = SimpleNamespace(id=new_id(), **data)
        self.state.escalations.append(record)
        return record


class FakeCommunicationRepo:
    def __init__(self, state: InMemoryState) -> None:
        self.state = state

    async def log_message(self, data: dict[str, Any]) -> Any:
        self.state.messages.append(dict(data))
        return SimpleNamespace(id=new_id(), **data)


class FakeWhatsAppRepo:
    def __init__(self, state: InMemoryState) -> None:
        self.state = state

    async def get_session_by_group(self, group_id: str) -> Any:
        return self.state.sessions.get(group_id)

    async def update(self, session_id: Any, values: dict[str, Any]) -> Any:
        for session in self.state.sessions.values():
            if str(session.id) == str(session_id):
                for key, value in values.items():
                    setattr(session, key, value)
                return session
        return None


class FakeContextManager:
    def __init__(self, state: InMemoryState) -> None:
        self.state = state

    async def get_project_context(self, project_id: Any) -> dict[str, Any]:
        project = self.state.projects.get(str(project_id))
        return {"project_id": str(project_id), "name": getattr(project, "name", None)}


class FakeIntentRouter:
    """A scripted intent router for driving :meth:`handle_incoming_message`."""

    def __init__(self, intent: str = "natural_language", entities: Optional[dict[str, Any]] = None,
                 reply: str = "Sure!") -> None:
        self.intent = intent
        self.entities = entities or {}
        self.reply = reply

    async def classify_intent(self, message: str) -> dict[str, Any]:
        return {"intent": self.intent, "confidence": 0.9, "raw_intent": self.intent, "understanding": {}}

    async def extract_entities(self, message: str) -> dict[str, Any]:
        return dict(self.entities)

    def route_intent(self, intent: str, entities: Optional[dict[str, Any]] = None,
                    context: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        return {"command": intent, "handler": intent, "entities": entities or {}, "context": context or {}}

    async def fallback_llm_response(self, message: str, context: Optional[dict[str, Any]] = None) -> str:
        return self.reply


class FakeWhatsAppSender:
    """Implements the engine's WhatsAppSender protocol; records everything."""

    def __init__(self) -> None:
        self.sent: list[dict[str, str]] = []

    async def send_message(self, to: str, message: str) -> Any:
        self.sent.append({"to": to, "message": message})
        return {"result": "sent", "to": to}

    async def send_group_message(self, group_id: str, message: str) -> Any:
        self.sent.append({"group_id": group_id, "message": message})
        return {"result": "sent", "group_id": group_id}


# ===========================================================================
# Orchestrator builder
# ===========================================================================
def build_orchestrator(
    *,
    state: Optional[InMemoryState] = None,
    workflow: Optional[dict[str, Any]] = None,
    intent_router: Optional[Any] = None,
    company_id: Optional[str] = None,
    group_id: str = "group-1",
) -> SimpleNamespace:
    """Wire an :class:`Orchestrator` backed entirely by in-memory fakes.

    Returns a :class:`SimpleNamespace` bundling the orchestrator and the
    shared ``state`` / collaborators so tests can assert on side effects.

    The DB-touching helpers ``_update_stage`` / ``_get_stage`` are replaced
    with store-backed coroutines so no real database is required.
    """

    from orchestra.engine.orchestrator import Orchestrator
    from orchestra.engine.workflow_engine import WorkflowEngine

    state = state or InMemoryState()
    company_id = company_id or SAMPLE_COMPANIES[0]["id"]

    # Seed a WhatsApp session so group -> company resolution works.
    session = SimpleNamespace(id=new_id(), company_id=company_id, session_data={})
    state.sessions[group_id] = session

    project_repo = FakeProjectRepo(state)
    task_repo = FakeTaskRepo(state)
    llm = FakeLLM(workflow=workflow)

    orch = Orchestrator(
        whatsapp_service=FakeWhatsAppSender(),
        workflow_engine=None,
        project_manager=FakeProjectManager(state, project_repo, task_repo),
        task_manager=FakeTaskManager(state),
        team_coordinator=FakeTeamCoordinator(state),
        intent_router=intent_router or FakeIntentRouter(),
        context_manager=FakeContextManager(state),
        scheduler=SimpleNamespace(get_scheduled_jobs=lambda: []),
        project_repo=project_repo,
        task_repo=task_repo,
        workflow_repo=FakeWorkflowRepo(state),
        escalation_repo=FakeEscalationRepo(state),
        communication_repo=FakeCommunicationRepo(state),
        whatsapp_repo=FakeWhatsAppRepo(state),
        learning_repo=SimpleNamespace(),
    )

    # Use the real WorkflowEngine but with the fake LLM (exercises the real
    # learning/validation logic without any network access).
    orch.workflow_engine = WorkflowEngine(llm_service=llm, workflow_repo=orch.workflow_repo)

    # Replace the two DB-touching private helpers with store-backed versions.
    async def _update_stage(stage_id: Any, values: dict[str, Any]) -> None:
        stage = state.stage_by_id(stage_id)
        if stage is not None:
            stage.update(values)

    async def _get_stage(stage_id: Any) -> Any:
        stage = state.stage_by_id(stage_id)
        return SimpleNamespace(**stage) if stage else None

    orch._update_stage = _update_stage  # type: ignore[assignment]
    orch._get_stage = _get_stage  # type: ignore[assignment]

    return SimpleNamespace(
        orchestrator=orch,
        state=state,
        llm=llm,
        company_id=company_id,
        group_id=group_id,
        project_repo=project_repo,
        task_repo=task_repo,
    )


__all__ = [
    "new_id",
    "SAMPLE_COMPANIES",
    "SAMPLE_TEAMS",
    "STORE_OPENING_WORKFLOW",
    "SOFTWARE_LAUNCH_WORKFLOW",
    "EVENT_PLANNING_WORKFLOW",
    "SAMPLE_CONVERSATIONS",
    "SAMPLE_VOICE_NOTE_BYTES",
    "SAMPLE_VOICE_TRANSCRIPT",
    "make_stage",
    "make_project",
    "FakeLLM",
    "FakeWhisper",
    "InMemoryState",
    "FakeWorkflowRepo",
    "FakeProjectRepo",
    "FakeTaskRepo",
    "FakeProjectManager",
    "FakeTaskManager",
    "FakeTeamCoordinator",
    "FakeEscalationRepo",
    "FakeCommunicationRepo",
    "FakeWhatsAppRepo",
    "FakeContextManager",
    "FakeIntentRouter",
    "FakeWhatsAppSender",
    "build_orchestrator",
]
