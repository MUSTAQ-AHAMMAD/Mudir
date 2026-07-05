# User Guide — Mudir / ORCHESTRA

**Audience:** team leads and staff who coordinate projects through the WhatsApp
bot.

Mudir ("Manager" in Arabic) is your AI project coordinator. It lives inside
WhatsApp, tracks every stage of a project, reminds the right people, escalates
delays, and confirms delivery on time. You can talk to it in **Arabic or
English** — it always replies **Arabic first**, with an English fallback.

---

## 1. Getting started

You'll be added to a WhatsApp group (or you can message the bot directly). No app
to install — just chat.

- **Group chat:** everyone sees updates; good for a whole project team.
- **Direct message (DM):** drive your own tasks privately. Commands work the
  same in both places because the bot recognises you by your saved phone number.

> If you leave the group you'll still receive your notifications by DM, because
> the bot messages your **stored number**, not group membership.

---

## 2. WhatsApp commands reference

| Command | What it does |
| --- | --- |
| `/new_project [name]` | Create a project and start the first stage |
| `/assign [team] [task] [deadline]` | Assign a task (deadline `YYYY-MM-DD`) |
| `/complete [project_id]` | Mark your current stage done and hand off to the next team |
| `/extend [project_id] [team] [days]` | Extend a team's deadline (alerts the CEO) |
| `/status [project_id]` | See the full project timeline and progress |
| `/escalate [project_id] [reason]` | Raise an urgent issue to the escalation contact |
| `/help` | List the available commands |

You don't have to memorise these — plain language works too (see below).

---

## 3. Natural-language examples

The bot understands everyday phrasing in Arabic and English. Examples:

| You say | The bot understands |
| --- | --- |
| "We're opening a new store in Riyadh next month" | Create a new project |
| "خلصنا مرحلة البناء" ("we finished the construction stage") | Complete the current stage |
| "We're done with our part" | Complete the current stage (asks you to confirm) |
| "The supplier is 4 days late" | Record a delay (auto-escalates if ≥ 3 days) |
| "There's a serious problem with the roof" | Raise an escalation |
| "How is the Riyadh store going?" | Send a status report |

For anything ambiguous, the bot asks a short clarifying question before acting.

---

## 4. Using voice notes

Record a WhatsApp voice note in Arabic or English and send it as usual. Mudir
transcribes it on-device (nothing leaves your server) and treats the text like a
typed message. For action phrases such as "we're done / خلصنا", it will **ask you
to confirm** before completing a stage, so an accidental voice note never changes
your project.

**Tips for accurate transcription**
- Speak clearly and avoid heavy background noise.
- Keep notes reasonably short (a sentence or two).
- Say the project name if you're involved in more than one project.

---

## 5. Sending images and documents

Send a photo of a permit, receipt or signed form. Mudir extracts the text (OCR)
and attaches it to the conversation so the update is captured with the project
record. This is handy for approvals ("municipality permit approved") and proof of
completion.

---

## 6. Checking status

Ask "status?" or run `/status [project_id]`. You'll get a report that shows:

- Overall **progress percentage**
- Each **stage** and whether it's pending, in progress, done or skipped
- The **current stage** and who owns it
- Any **blockers** or recorded **delays**

---

## 7. Managing your project

1. **Start** — create the project; Mudir learns the stages and kicks off the first one.
2. **Work** — each team completes its stage and says so; Mudir advances automatically.
3. **Coordinate** — the next team lead is notified the moment the previous stage finishes.
4. **Finish** — when the last stage completes, Mudir marks the project done and
   announces it to the group.

---

## 8. Team coordination

- Only the **relevant team lead** is nudged for a given stage, to avoid noise.
- When your stage starts you'll get a notification with the task and deadline.
- Daily summaries recap outstanding work (sent on working days only).

---

## 9. Escalation process

- **Automatic:** any delay of **3 days or more** is escalated to the CEO/escalation
  contact automatically.
- **Manual:** use `/escalate [project_id] [reason]` (or say "this is urgent") for
  anything that needs immediate attention. Urgent escalations are flagged
  **critical** and the CEO is notified for approval/decision.

---

## 10. Best practices

- Report progress **as it happens** — short, frequent updates beat long recaps.
- Flag delays **early**; the bot can only help if it knows.
- Include the **project name** when you're on multiple projects.
- Prefer **confirming** action prompts rather than ignoring them.
- Keep team-lead phone numbers **up to date** (ask your admin).

---

## 11. FAQ

**Do I need to install anything?**
No. Everything happens in WhatsApp.

**Which languages are supported?**
Arabic and English, in both directions. Replies are Arabic first.

**Does it work on Fridays?**
Reminders and scheduling respect the Saudi working week (Sun–Thu) and skip
Friday. You can still send messages any day.

**Is my data sent to OpenAI or any cloud AI?**
No. Mudir is 100% self-hosted — transcription, understanding and translation all
run on your own server.

**What if I send a voice note by mistake?**
Action phrases require confirmation, so nothing changes unless you say yes.

**Can I run more than one project at once?**
Yes. Projects are independent; just name the one you mean.

**Who sees my messages?**
In a group, group members do. In a DM, only you and the bot. Data is stored in
your organisation's own database.
