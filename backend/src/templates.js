// templates.js
// -----------------------------------------------------------------------------
// Bilingual (Arabic primary, English fallback) message templates used by the
// bot. Every function returns a ready-to-send string. Keeping copy in one place
// makes it easy to keep tone consistent and to map to Meta-approved templates
// (see ../../WHATSAPP_TEMPLATES.md for the Meta submission versions).
// -----------------------------------------------------------------------------
'use strict';

const AR = {
  welcome: (project) =>
    `👋 مرحبًا! أنا *مدير*، منسق مشروعك.\n` +
    `تم ربط هذه المجموعة بمشروع: *${project}*.\n` +
    `اكتب /help لعرض الأوامر المتاحة.`,
  projectCreated: (code, name, team) =>
    `✅ تم إنشاء المشروع *${name}* (${code}).\n` +
    `👷 الفريق الحالي: *${team}*. يرجى البدء بالمهام.`,
  taskAssigned: (team, task, deadline) =>
    `📋 مهمة جديدة لفريق *${team}*:\n• ${task}\n🗓️ الموعد النهائي: ${deadline}`,
  teamNotified: (team, project) =>
    `🔔 حان دور فريق *${team}* في مشروع *${project}*. يرجى إكمال مهامكم.`,
  teamCompleted: (team, project) =>
    `✅ أكمل فريق *${team}* مهامه في مشروع *${project}*.`,
  projectReady: (project) =>
    `🎉 مشروع *${project}* جاهز! جميع الفرق أنهت مهامها. المتجر سيفتح في الوقت المحدد ✅`,
  overdue: (team, project, days) =>
    `⚠️ تنبيه: فريق *${team}* متأخر ${days} يوم/أيام في مشروع *${project}*.`,
  escalation: (project, reason) =>
    `🚨 *تصعيد عاجل* — مشروع *${project}*.\nالسبب: ${reason}\nيرجى التدخل فورًا.`,
  extensionRequested: (project, team, days) =>
    `⏳ طلب تمديد: فريق *${team}* يطلب ${days} يوم/أيام إضافية لمشروع *${project}*.`,
  dailySummary: (line) => `☀️ *الملخص اليومي*\n${line}`,
  unknown: () =>
    `🤔 لم أفهم الأمر. اكتب /help لعرض الأوامر.`,
  help: () =>
    `📖 *الأوامر المتاحة*\n` +
    `/new_project [الاسم]\n/assign [الفريق] [المهمة] [التاريخ]\n` +
    `/complete [رقم المشروع]\n/extend [رقم المشروع] [الفريق] [الأيام]\n` +
    `/status [رقم المشروع]\n/escalate [رقم المشروع] [السبب]`,
};

const EN = {
  welcome: (project) =>
    `👋 Hello! I'm *Mudir*, your project coordinator.\n` +
    `This group is linked to project: *${project}*.\n` +
    `Type /help to see available commands.`,
  projectCreated: (code, name, team) =>
    `✅ Project *${name}* (${code}) created.\n👷 Current team: *${team}*. Please begin your tasks.`,
  taskAssigned: (team, task, deadline) =>
    `📋 New task for *${team}*:\n• ${task}\n🗓️ Deadline: ${deadline}`,
  teamNotified: (team, project) =>
    `🔔 It's *${team}*'s turn on project *${project}*. Please complete your tasks.`,
  teamCompleted: (team, project) => `✅ *${team}* completed their tasks on *${project}*.`,
  projectReady: (project) =>
    `🎉 Project *${project}* is ready! All teams are done. The store will open on time ✅`,
  overdue: (team, project, days) =>
    `⚠️ Alert: *${team}* is ${days} day(s) overdue on project *${project}*.`,
  escalation: (project, reason) =>
    `🚨 *URGENT ESCALATION* — project *${project}*.\nReason: ${reason}\nPlease intervene immediately.`,
  extensionRequested: (project, team, days) =>
    `⏳ Extension request: *${team}* requests ${days} extra day(s) on *${project}*.`,
  dailySummary: (line) => `☀️ *Daily Summary*\n${line}`,
  unknown: () => `🤔 I didn't understand that. Type /help for commands.`,
  help: () =>
    `📖 *Available commands*\n` +
    `/new_project [name]\n/assign [team] [task] [deadline]\n` +
    `/complete [project_id]\n/extend [project_id] [team] [days]\n` +
    `/status [project_id]\n/escalate [project_id] [reason]`,
};

/**
 * Build a bilingual message: Arabic first, English fallback underneath.
 * @param {keyof typeof AR} key
 * @param  {...any} args
 * @returns {string}
 */
function t(key, ...args) {
  const ar = typeof AR[key] === 'function' ? AR[key](...args) : AR[key];
  const en = typeof EN[key] === 'function' ? EN[key](...args) : EN[key];
  return `${ar}\n\n— — —\n${en}`;
}

module.exports = { t, AR, EN };
