"""Bilingual (Arabic + English) WhatsApp message templates.

Each template is defined once with an Arabic body and an English body plus the
set of variables it expects. :func:`render` fills the variables and, by
default, returns *both* languages (Arabic first, English below) which matches
how Mudir speaks to bilingual project groups. Pass ``lang="ar"`` or
``lang="en"`` to render a single language.

The plain-text bodies here are what the bot sends interactively (within the
WhatsApp 24-hour customer-service window). The Meta/Twilio *pre-approved*
versions used for business-initiated messages live in ``WHATSAPP_TEMPLATES.md``
and are referenced by name via :data:`META_TEMPLATE_NAMES`; keep the two in
sync when copy changes.

Usage::

    from orchestra.whatsapp import templates

    msg = templates.render(
        "PROJECT_CREATED",
        {"project_name": "Riyadh Mall", "team": "Property Team"},
        lang="ar",
    )
"""

from __future__ import annotations

from dataclasses import dataclass
from string import Formatter
from typing import Any, Mapping, Optional

from .config import config, get_logger
from .exceptions import TemplateNotFoundError

_log = get_logger(__name__)

#: Divider used when rendering both languages together.
_DIVIDER = "\n\n— — —\n\n"

Lang = str  # "ar" | "en" | "both"


@dataclass(frozen=True)
class Template:
    """A single bilingual template.

    Args:
        name: Stable template key (also the dict key in :data:`TEMPLATES`).
        ar: Arabic body with ``{variable}`` placeholders.
        en: English body with ``{variable}`` placeholders.
        variables: Ordered names of the variables the bodies expect.
        meta_name: Name of the matching Meta/Twilio approved template, if any.
    """

    name: str
    ar: str
    en: str
    variables: tuple[str, ...] = ()
    meta_name: Optional[str] = None

    def body(self, lang: Lang) -> str:
        """Return the raw (unfilled) body for ``lang``."""

        if lang == "ar":
            return self.ar
        if lang == "en":
            return self.en
        return f"{self.ar}{_DIVIDER}{self.en}"


def _fields(text: str) -> set[str]:
    """Return the set of ``{field}`` names referenced by ``text``."""

    return {
        field_name
        for _, field_name, _, _ in Formatter().parse(text)
        if field_name
    }


# ---------------------------------------------------------------------------
# Template definitions
# ---------------------------------------------------------------------------
TEMPLATES: dict[str, Template] = {
    "PROJECT_CREATED": Template(
        name="PROJECT_CREATED",
        ar=(
            "✅ تم إنشاء المشروع: *{project_name}*\n"
            "أنا مدير، وسأتولّى تنسيق المراحل والمهام مع {team}.\n"
            "اكتب /help لعرض الأوامر المتاحة."
        ),
        en=(
            "✅ Project created: *{project_name}*\n"
            "I'm Mudir and I'll coordinate the stages and tasks with {team}.\n"
            "Type /help to see the available commands."
        ),
        variables=("project_name", "team"),
        meta_name="mudir_welcome",
    ),
    "STAGE_COMPLETED": Template(
        name="STAGE_COMPLETED",
        ar=(
            "✅ اكتملت المرحلة: *{stage_name}* في مشروع {project_name}.\n"
            "أحسنتم! ننتقل الآن إلى الخطوة التالية."
        ),
        en=(
            "✅ Stage completed: *{stage_name}* on project {project_name}.\n"
            "Well done! Moving on to the next step."
        ),
        variables=("stage_name", "project_name"),
    ),
    "STAGE_STARTED": Template(
        name="STAGE_STARTED",
        ar=(
            "▶️ بدأت المرحلة: *{stage_name}* في مشروع {project_name}.\n"
            "الفريق المسؤول: {team}\n"
            "🗓️ الموعد المستهدف: {deadline}"
        ),
        en=(
            "▶️ Stage started: *{stage_name}* on project {project_name}.\n"
            "Owning team: {team}\n"
            "🗓️ Target date: {deadline}"
        ),
        variables=("stage_name", "project_name", "team", "deadline"),
    ),
    "TASK_ASSIGNED": Template(
        name="TASK_ASSIGNED",
        ar=(
            "📋 مهمة جديدة لفريق {team}:\n"
            "• {task}\n"
            "🗓️ الموعد النهائي: {deadline}"
        ),
        en=(
            "📋 New task for {team}:\n"
            "• {task}\n"
            "🗓️ Deadline: {deadline}"
        ),
        variables=("team", "task", "deadline"),
        meta_name="mudir_task_assigned",
    ),
    "DAILY_REMINDER": Template(
        name="DAILY_REMINDER",
        ar=(
            "☀️ تذكير صباحي — مشروع {project_name}\n"
            "{summary}\n"
            "بالتوفيق اليوم!"
        ),
        en=(
            "☀️ Morning reminder — project {project_name}\n"
            "{summary}\n"
            "Have a great day!"
        ),
        variables=("project_name", "summary"),
        meta_name="mudir_daily_summary",
    ),
    "OVERDUE_ALERT": Template(
        name="OVERDUE_ALERT",
        ar="⚠️ تنبيه: فريق {team} متأخر {days} يوم/أيام في مشروع {project_name}.",
        en="⚠️ Alert: {team} is {days} day(s) overdue on project {project_name}.",
        variables=("team", "days", "project_name"),
        meta_name="mudir_overdue_alert",
    ),
    "ESCALATION": Template(
        name="ESCALATION",
        ar=(
            "🚨 تصعيد عاجل — مشروع {project_name}.\n"
            "السبب: {reason}\n"
            "يرجى التدخل فورًا."
        ),
        en=(
            "🚨 URGENT ESCALATION — project {project_name}.\n"
            "Reason: {reason}\n"
            "Please intervene immediately."
        ),
        variables=("project_name", "reason"),
        meta_name="mudir_escalation",
    ),
    "PROJECT_COMPLETE": Template(
        name="PROJECT_COMPLETE",
        ar=(
            "🎉 مشروع {project_name} جاهز! جميع الفرق أنهت مهامها. "
            "أحسنتم جميعًا ✅"
        ),
        en=(
            "🎉 Project {project_name} is ready! All teams are done. "
            "Great work everyone ✅"
        ),
        variables=("project_name",),
        meta_name="mudir_project_ready",
    ),
    "WEEKLY_SUMMARY": Template(
        name="WEEKLY_SUMMARY",
        ar=(
            "🗓️ الملخص الأسبوعي — مشروع {project_name}\n"
            "{summary}"
        ),
        en=(
            "🗓️ Weekly summary — project {project_name}\n"
            "{summary}"
        ),
        variables=("project_name", "summary"),
    ),
    "HELP_RESPONSE": Template(
        name="HELP_RESPONSE",
        ar=(
            "🤖 أوامر مدير:\n"
            "• /status — حالة المشروع\n"
            "• /tasks — المهام المفتوحة\n"
            "• أخبرني بأي تحديث وسأحدّث الخطة تلقائيًا.\n"
            "• لإنهاء مرحلة اكتب: تم إنجاز <اسم المرحلة>"
        ),
        en=(
            "🤖 Mudir commands:\n"
            "• /status — project status\n"
            "• /tasks — open tasks\n"
            "• Tell me any update and I'll adjust the plan automatically.\n"
            "• To finish a stage, say: done <stage name>"
        ),
        variables=(),
    ),
}

#: Convenience mapping of template key -> Meta/Twilio approved template name.
META_TEMPLATE_NAMES: dict[str, str] = {
    name: tpl.meta_name
    for name, tpl in TEMPLATES.items()
    if tpl.meta_name is not None
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def get_template(name: str) -> Template:
    """Return the :class:`Template` for ``name`` or raise.

    Raises:
        TemplateNotFoundError: If ``name`` is not a known template.
    """

    try:
        return TEMPLATES[name]
    except KeyError as exc:
        raise TemplateNotFoundError(name, original=exc) from exc


def render(
    name: str,
    variables: Optional[Mapping[str, Any]] = None,
    *,
    lang: Optional[Lang] = None,
) -> str:
    """Render template ``name`` with ``variables``.

    Args:
        name: The template key (e.g. ``"PROJECT_CREATED"``).
        variables: Mapping of placeholder -> value. Missing values are rendered
            as an empty string rather than raising, so a partial update never
            crashes the send path.
        lang: ``"ar"``, ``"en"`` or ``"both"``. Defaults to
            :data:`config.default_lang` when omitted; any value other than
            ``"ar"``/``"en"`` renders both languages.

    Returns:
        The filled message text.

    Raises:
        TemplateNotFoundError: If ``name`` is unknown.
    """

    template = get_template(name)
    resolved_lang = lang or config.default_lang
    values = dict(variables or {})

    # Fill any expected-but-missing variables with an empty string so a partial
    # payload degrades gracefully instead of raising KeyError mid-send.
    body = template.body(resolved_lang)
    needed = _fields(body)
    for key in needed:
        values.setdefault(key, "")

    try:
        return body.format(**values)
    except (KeyError, IndexError, ValueError) as exc:  # pragma: no cover - defensive
        _log.warning("Failed to render template %s: %s", name, exc)
        # Fall back to the unfilled body rather than losing the message.
        return body


def list_templates() -> list[str]:
    """Return the sorted list of available template names."""

    return sorted(TEMPLATES)


__all__ = [
    "Template",
    "TEMPLATES",
    "META_TEMPLATE_NAMES",
    "get_template",
    "render",
    "list_templates",
]
