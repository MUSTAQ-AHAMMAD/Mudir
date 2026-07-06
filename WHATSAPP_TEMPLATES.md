# WhatsApp Message Templates (Meta / Twilio)

These are the **Meta-approved template** versions of Mudir's outbound messages.
Business-initiated WhatsApp messages sent outside the 24-hour customer service
window must use a pre-approved template. Submit these in the Twilio Content
Template Builder (or Meta Business Manager) and reference them by `ContentSid`
when sending. Variables use Twilio's `{{1}}`, `{{2}}` … placeholders.

Each template is bilingual: Arabic first, English fallback below.
Category is either **UTILITY** (transactional) or **ALERT/UTILITY**.

---

## 1. Welcome (bot added to a group)
- **Name:** `mudir_welcome`
- **Category:** UTILITY
- **Body:**
```
👋 مرحبًا! أنا مدير، منسق مشروعك. تم ربط هذه المجموعة بمشروع: {{1}}. اكتب /help لعرض الأوامر.

— — —
👋 Hello! I'm Mudir, your project coordinator. This group is linked to project: {{1}}. Type /help for commands.
```
- **Variables:** `{{1}}` = project name

## 2. Daily Summary
- **Name:** `mudir_daily_summary`
- **Category:** UTILITY
- **Body:**
```
☀️ الملخص اليومي
{{1}}

— — —
☀️ Daily Summary
{{1}}
```
- **Variables:** `{{1}}` = summary text

## 3. Task Assignment Notification
- **Name:** `mudir_task_assigned`
- **Category:** UTILITY
- **Body:**
```
📋 مهمة جديدة لفريق {{1}}:
• {{2}}
🗓️ الموعد النهائي: {{3}}

— — —
📋 New task for {{1}}:
• {{2}}
🗓️ Deadline: {{3}}
```
- **Variables:** `{{1}}` = team, `{{2}}` = task, `{{3}}` = deadline

## 4. Overdue Alert
- **Name:** `mudir_overdue_alert`
- **Category:** UTILITY
- **Body:**
```
⚠️ تنبيه: فريق {{1}} متأخر {{2}} يوم/أيام في مشروع {{3}}.

— — —
⚠️ Alert: {{1}} is {{2}} day(s) overdue on project {{3}}.
```
- **Variables:** `{{1}}` = team, `{{2}}` = days, `{{3}}` = project

## 5. Project Completion Announcement
- **Name:** `mudir_project_ready`
- **Category:** UTILITY
- **Body:**
```
🎉 مشروع {{1}} جاهز! جميع الفرق أنهت مهامها. المتجر سيفتح في الوقت المحدد ✅

— — —
🎉 Project {{1}} is ready! All teams are done. The store will open on time ✅
```
- **Variables:** `{{1}}` = project name

## 6. Escalation Alert
- **Name:** `mudir_escalation`
- **Category:** UTILITY
- **Body:**
```
🚨 تصعيد عاجل — مشروع {{1}}.
السبب: {{2}}
يرجى التدخل فورًا.

— — —
🚨 URGENT ESCALATION — project {{1}}.
Reason: {{2}}
Please intervene immediately.
```
- **Variables:** `{{1}}` = project, `{{2}}` = reason

---

### Sending a template with Twilio (example)
```js
await twilioClient.messages.create({
  from: 'whatsapp:+1415…',
  to: 'whatsapp:+9665…',
  contentSid: 'HXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',   // the approved template
  contentVariables: JSON.stringify({ 1: 'Riyadh Mall', 2: '2 days', 3: 'P-001' }),
});
```

> The plain-text strings the bot sends interactively (within the 24h window)
> live in `backend/src/templates.js`. Keep the two in sync when copy changes.
