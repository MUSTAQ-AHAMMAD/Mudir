# ORCHESTRA Orchestration Engine (`orchestra/engine`)

**Phase 3 — the coordination brain.** This package connects the self-hosted AI
services (`orchestra/services`) and the async database layer
(`orchestra/database`) into one engine that learns workflows, drives projects
through a universal state machine, understands natural-language messages, and
runs the recurring reminder / escalation / reporting jobs.

## Modules

| File | Purpose |
| --- | --- |
| `orchestrator.py` | **THE MAIN ENGINE** — wires AI + DB + workflow together |
| `workflow_engine.py` | Learns *any* workflow dynamically from conversations |
| `state_machine.py` | Universal, workflow-agnostic state manager |
| `project_manager.py` | Project lifecycle (CRUD, archive, at-risk queries) |
| `task_manager.py` | Task CRUD + embeddings-based smart assignment |
| `team_coordinator.py` | Team notifications and CEO escalations |
| `intent_router.py` | NLP intent classification + command routing |
| `context_manager.py` | Project context and long-term memory |
| `scheduler.py` | Dependency-free cron jobs (reminders, reports, learning) |
| `exceptions.py` | Engine-specific exception hierarchy |

## Design patterns

- **Singleton** — `get_orchestrator()` returns one shared `Orchestrator`.
- **Command** — `IntentRouter` maps each intent to an orchestrator handler,
  dispatched by `Orchestrator.process_message_intent`.
- **Strategy** — workflow learning is delegated to `WorkflowEngine`.
- **Dependency injection** — every collaborator (managers, coordinator, router,
  repositories, and the WhatsApp transport) can be supplied for testing;
  otherwise sensible lazy defaults are created.

## Integration

The orchestrator lazily uses:

- **AI services** — `orchestra.services` (LLM, embeddings, sentiment, …).
- **Database repositories** — `orchestra.database.repositories`.
- **WhatsApp transport** — injected via the `WhatsAppSender` protocol. Because
  WhatsApp integration is a later phase, the engine degrades gracefully when no
  transport is supplied: outbound messages are logged and recorded in the
  communication log instead of being sent.

All heavy dependencies are imported lazily, so importing the package is cheap
and side-effect free.

## Quick start

```python
from orchestra.engine import Orchestrator

orchestrator = Orchestrator()

result = await orchestrator.handle_incoming_message(
    message="We're opening a store in Riyadh Mall",
    sender="+966501234567",
    group_id="group123",
)
print(result["reply"])
```

## Requirements

The engine adds **no new third-party dependencies**; it only relies on the
Python standard library plus the already-declared requirements of the services
and database layers:

```bash
pip install -r orchestra/services/requirements.txt
pip install -r orchestra/database/requirements.txt
```
