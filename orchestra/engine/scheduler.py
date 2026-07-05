"""Cron job management for the orchestration engine.

:class:`Scheduler` provides a small, **dependency-free** cron facility built on
``asyncio``. It avoids pulling in a heavyweight scheduler so the engine stays
lean; each :class:`ScheduledJob` carries a simple time specification (minute,
hour, allowed weekdays, optional day-of-month) and the scheduler computes the
next run time itself.

The default jobs wire the orchestrator's periodic routines:

    * daily reminders — 09:00 on working days
    * evening escalations — 18:00 daily
    * weekly report — Sundays 10:00
    * monthly learning — 1st of the month 03:00

Jobs can be started as a background loop (:meth:`start`) or triggered manually
(:meth:`run_job` / :meth:`run_due_jobs`), which keeps them easy to unit-test.
"""

from __future__ import annotations

import asyncio
import inspect
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Optional

from ..services.config import get_logger
from .exceptions import SchedulingError

_log = get_logger(__name__)

# Saudi working week (Sunday-Thursday). Python weekday(): Monday=0 .. Sunday=6.
DEFAULT_WORKING_DAYS = frozenset({6, 0, 1, 2, 3})

JobCallback = Callable[[], Any]


def _now() -> datetime:
    """Return an aware UTC ``datetime`` (single choke-point for testability)."""

    return datetime.now(timezone.utc)


@dataclass
class ScheduledJob:
    """A single recurring job with a simple cron-like specification."""

    name: str
    callback: JobCallback
    minute: int = 0
    hour: int = 9
    weekdays: frozenset[int] = field(default_factory=lambda: frozenset(range(7)))
    day_of_month: Optional[int] = None
    last_run: Optional[datetime] = None
    next_run: Optional[datetime] = None

    def compute_next_run(self, after: Optional[datetime] = None) -> datetime:
        """Return the next run time strictly after ``after`` (default: now)."""

        reference = after or _now()
        candidate = reference.replace(
            hour=self.hour, minute=self.minute, second=0, microsecond=0
        )
        if candidate <= reference:
            candidate += timedelta(days=1)
        for _ in range(367):  # scan up to just over a year
            if self._matches_day(candidate):
                return candidate
            candidate += timedelta(days=1)
        raise SchedulingError(f"Could not compute next run for job {self.name!r}")

    def _matches_day(self, moment: datetime) -> bool:
        if self.day_of_month is not None and moment.day != self.day_of_month:
            return False
        if moment.weekday() not in self.weekdays:
            return False
        return True

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable description of the job."""

        return {
            "name": self.name,
            "minute": self.minute,
            "hour": self.hour,
            "weekdays": sorted(self.weekdays),
            "day_of_month": self.day_of_month,
            "last_run": self.last_run.isoformat() if self.last_run else None,
            "next_run": self.next_run.isoformat() if self.next_run else None,
        }


class Scheduler:
    """Registers and runs recurring engine jobs."""

    def __init__(
        self,
        orchestrator: Any = None,
        *,
        working_days: frozenset[int] = DEFAULT_WORKING_DAYS,
    ) -> None:
        self._orchestrator = orchestrator
        self.working_days = working_days
        self._jobs: dict[str, ScheduledJob] = {}
        self._task: Optional[asyncio.Task[None]] = None
        self._stopped = asyncio.Event()

    # -- registration -------------------------------------------------------
    def register(self, job: ScheduledJob) -> ScheduledJob:
        """Register (or replace) a job and compute its first run time."""

        job.next_run = job.compute_next_run()
        self._jobs[job.name] = job
        _log.info("Registered job %r (next run %s)", job.name, job.next_run)
        return job

    def _callback_for(self, method_name: str) -> JobCallback:
        """Bind a job to an orchestrator coroutine, resolving lazily."""

        def _invoke() -> Any:
            orch = self._orchestrator
            if orch is None:
                _log.warning("No orchestrator bound; job %r is a no-op", method_name)
                return None
            method = getattr(orch, method_name, None)
            if method is None:
                raise SchedulingError(
                    f"Orchestrator has no method {method_name!r}"
                )
            return method()

        return _invoke

    # -- default job factories ---------------------------------------------
    def schedule_daily_reminders(self) -> ScheduledJob:
        """Schedule 09:00 reminders on working days."""

        return self.register(
            ScheduledJob(
                name="daily_reminders",
                callback=self._callback_for("send_daily_reminders"),
                hour=9,
                minute=0,
                weekdays=self.working_days,
            )
        )

    def schedule_evening_escalations(self) -> ScheduledJob:
        """Schedule 18:00 escalations every day."""

        return self.register(
            ScheduledJob(
                name="evening_escalations",
                callback=self._callback_for("send_evening_escalations"),
                hour=18,
                minute=0,
                weekdays=frozenset(range(7)),
            )
        )

    def schedule_weekly_report(self) -> ScheduledJob:
        """Schedule the Sunday 10:00 weekly report."""

        return self.register(
            ScheduledJob(
                name="weekly_report",
                callback=self._callback_for("send_weekly_report"),
                hour=10,
                minute=0,
                weekdays=frozenset({6}),  # Sunday
            )
        )

    def schedule_monthly_learning(self) -> ScheduledJob:
        """Schedule monthly workflow learning on the 1st at 03:00."""

        return self.register(
            ScheduledJob(
                name="monthly_learning",
                callback=self._callback_for("run_monthly_learning"),
                hour=3,
                minute=0,
                weekdays=frozenset(range(7)),
                day_of_month=1,
            )
        )

    def schedule_all_defaults(self) -> list[ScheduledJob]:
        """Register the full set of default jobs and return them."""

        return [
            self.schedule_daily_reminders(),
            self.schedule_evening_escalations(),
            self.schedule_weekly_report(),
            self.schedule_monthly_learning(),
        ]

    # -- introspection ------------------------------------------------------
    def get_scheduled_jobs(self) -> list[dict[str, Any]]:
        """Return a JSON-serialisable list of all registered jobs."""

        return [job.to_dict() for job in self._jobs.values()]

    # -- execution ----------------------------------------------------------
    async def run_job(self, name: str) -> Any:
        """Run a single registered job immediately by name."""

        job = self._jobs.get(name)
        if job is None:
            raise SchedulingError(f"No such job: {name!r}")
        return await self._execute(job)

    async def run_due_jobs(self, *, now: Optional[datetime] = None) -> list[str]:
        """Run every job whose ``next_run`` is due, returning executed names."""

        moment = now or _now()
        executed: list[str] = []
        for job in self._jobs.values():
            if job.next_run is not None and job.next_run <= moment:
                await self._execute(job)
                executed.append(job.name)
        return executed

    async def _execute(self, job: ScheduledJob) -> Any:
        """Invoke a job's callback, awaiting it if it is a coroutine."""

        _log.info("Running scheduled job %r", job.name)
        try:
            result = job.callback()
            if inspect.isawaitable(result):
                result = await result
        except Exception as exc:  # noqa: BLE001 - a failing job must not kill loop
            _log.error("Scheduled job %r failed: %s", job.name, exc)
            raise SchedulingError(
                f"Job {job.name!r} failed", original=exc
            ) from exc
        finally:
            job.last_run = _now()
            job.next_run = job.compute_next_run(job.last_run)
        return result

    async def run_health_check(self) -> dict[str, Any]:
        """Probe core dependencies (LLM + database) and report their health."""

        health: dict[str, Any] = {"checked_at": _now().isoformat()}
        try:
            from ..services import llm_service

            health["llm"] = bool(llm_service.get_service().health_check())
        except Exception as exc:  # noqa: BLE001
            health["llm"] = False
            health["llm_error"] = str(exc)
        try:
            from ..database.connection import get_connection_manager

            health["database"] = bool(await get_connection_manager().health_check())
        except Exception as exc:  # noqa: BLE001
            health["database"] = False
            health["database_error"] = str(exc)
        health["healthy"] = bool(health.get("llm")) and bool(health.get("database"))
        return health

    # -- background loop ----------------------------------------------------
    async def start(self, *, poll_seconds: float = 30.0) -> None:
        """Run the scheduler loop until :meth:`stop` is called."""

        if self._task is not None:
            _log.warning("Scheduler already running")
            return
        self._stopped.clear()
        self._task = asyncio.current_task()
        _log.info("Scheduler loop started (poll=%.0fs)", poll_seconds)
        try:
            while not self._stopped.is_set():
                await self.run_due_jobs()
                try:
                    await asyncio.wait_for(
                        self._stopped.wait(), timeout=poll_seconds
                    )
                except asyncio.TimeoutError:
                    continue
        finally:
            self._task = None
            _log.info("Scheduler loop stopped")

    def stop(self) -> None:
        """Signal the background loop to stop."""

        self._stopped.set()


__all__ = ["Scheduler", "ScheduledJob", "DEFAULT_WORKING_DAYS"]
