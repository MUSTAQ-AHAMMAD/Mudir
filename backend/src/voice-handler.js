// voice-handler.js
// -----------------------------------------------------------------------------
// Handles WhatsApp voice notes. Flow:
//   1. Transcribe the audio via Whisper.
//   2. Try to map the transcript to an intent (e.g. "we are done" -> /complete).
//   3. Rather than acting immediately, ask the user to confirm. The pending
//      action is stored keyed by sender; the next "yes/نعم" confirms it.
//
// The pending-confirmation store is in-memory for simplicity. In a multi-
// instance production deployment this should be backed by Redis or a DB table
// so confirmations survive restarts and work across instances.
// -----------------------------------------------------------------------------
'use strict';

const logger = require('./logger');

// sender -> { command, transcript, expiresAt }
const pendingConfirmations = new Map();
const CONFIRM_TTL_MS = 5 * 60 * 1000; // pending action expires after 5 minutes

// Natural-language phrases (Arabic + English) mapped to structured commands.
// Only a small, safe set is auto-mapped; anything else falls back to text.
const INTENT_PATTERNS = [
  { re: /\b(we are done|we're done|task done|completed|finished)\b/i, name: 'complete' },
  { re: /(انتهينا|خلصنا|تم الإنجاز|اكتمل)/, name: 'complete' },
];

/**
 * Affirmative / negative detection for confirmation replies.
 * @param {string} text
 * @returns {'yes'|'no'|null}
 */
function parseConfirmation(text) {
  if (!text) return null;
  if (/\b(yes|yep|confirm|ok|okay)\b/i.test(text) || /(نعم|أكد|تمام|موافق)/.test(text)) return 'yes';
  if (/\b(no|cancel|stop)\b/i.test(text) || /(لا|إلغاء|توقف)/.test(text)) return 'no';
  return null;
}

/**
 * Map a transcript to a command intent. Returns null when nothing matches.
 * @param {string} transcript
 * @param {string} projectId Project the intent applies to (required for /complete).
 * @returns {{name: string, args: object}|null}
 */
function transcriptToCommand(transcript, projectId) {
  for (const p of INTENT_PATTERNS) {
    if (p.re.test(transcript)) {
      if (p.name === 'complete') return { name: 'complete', args: { projectId } };
    }
  }
  return null;
}

/**
 * Store a pending action awaiting confirmation.
 * @param {string} sender
 * @param {{name: string, args: object}} command
 * @param {string} transcript
 */
function setPending(sender, command, transcript) {
  pendingConfirmations.set(sender, { command, transcript, expiresAt: Date.now() + CONFIRM_TTL_MS });
}

/**
 * Retrieve (and validate TTL of) a pending action for a sender.
 * @param {string} sender
 * @returns {{command: object, transcript: string}|null}
 */
function getPending(sender) {
  const entry = pendingConfirmations.get(sender);
  if (!entry) return null;
  if (Date.now() > entry.expiresAt) {
    pendingConfirmations.delete(sender);
    return null;
  }
  return entry;
}

/** Clear a pending action. @param {string} sender */
function clearPending(sender) {
  pendingConfirmations.delete(sender);
}

/**
 * Process a voice note: transcribe, detect intent, and return a confirmation
 * prompt (without executing). Returns the transcript when no intent matches.
 *
 * @param {object} params
 * @param {string} params.mediaUrl   Twilio media URL.
 * @param {string} params.sender     WhatsApp id.
 * @param {string} [params.projectId] Project context for the intent.
 * @param {object} deps              { ai } injected AI service.
 * @returns {Promise<string>} Reply text.
 */
async function handleVoiceNote({ mediaUrl, sender, projectId }, deps = {}) {
  const ai = deps.ai || require('./ai-service');
  const transcript = await ai.transcribeAudio(mediaUrl);
  logger.info({ sender, transcript }, 'Voice note transcribed');

  const command = transcriptToCommand(transcript, projectId);
  if (!command) {
    return `📝 سمعت / I heard:\n"${transcript}"\n\n` +
      `لم أتعرف على أمر. / No command detected. Type /help.`;
  }
  setPending(sender, command, transcript);
  return (
    `📝 سمعت / I heard: "${transcript}"\n\n` +
    `هل تريد تنفيذ الأمر: */${command.name} ${command.args.projectId || ''}* ؟\n` +
    `Reply *نعم/yes* to confirm or *لا/no* to cancel.`
  );
}

module.exports = {
  handleVoiceNote,
  transcriptToCommand,
  parseConfirmation,
  setPending,
  getPending,
  clearPending,
};
