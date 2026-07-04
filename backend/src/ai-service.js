// ai-service.js
// -----------------------------------------------------------------------------
// OpenAI integrations:
//   * summarizeConversation() — condenses a project's log/chat into a short,
//     bilingual status summary (used by the daily cron and /status).
//   * transcribeAudio() — downloads a WhatsApp voice note and runs it through
//     Whisper, returning the transcript text.
// The OpenAI client is created lazily so tests can run without an API key.
// -----------------------------------------------------------------------------
'use strict';

const fs = require('fs');
const os = require('os');
const path = require('path');
const axios = require('axios');
const OpenAI = require('openai');
const { config } = require('./config');
const logger = require('./logger');
const { withRetry } = require('./utils');

let openaiClient = null;

/**
 * Get the shared OpenAI client, creating it on first use.
 * @returns {OpenAI}
 */
function getClient() {
  if (openaiClient) return openaiClient;
  if (!config.openai.apiKey) {
    throw new Error('OpenAI is not configured (OPENAI_API_KEY).');
  }
  openaiClient = new OpenAI({ apiKey: config.openai.apiKey });
  return openaiClient;
}

/**
 * Summarise a list of log/message lines into a short bilingual status update.
 * @param {string[]} lines Chronological log/message lines.
 * @returns {Promise<string>}
 */
async function summarizeConversation(lines) {
  const text = (lines || []).join('\n').slice(0, 8000); // guard against huge prompts
  if (!text.trim()) return 'No activity to summarise. / لا يوجد نشاط للتلخيص.';
  const completion = await withRetry(
    () =>
      getClient().chat.completions.create({
        model: config.openai.chatModel,
        temperature: 0.2,
        messages: [
          {
            role: 'system',
            content:
              'You are Mudir, a project coordinator. Summarise the project activity in <=4 bullet ' +
              'points. Reply in Arabic first, then an English translation. Be concise and factual.',
          },
          { role: 'user', content: text },
        ],
      }),
    { retries: 2, onRetry: (err, a) => logger.warn({ err: err.message, a }, 'Retry summarize') },
  );
  return completion.choices[0].message.content.trim();
}

/**
 * Download a media URL (Twilio-hosted) to a temp file. Twilio media requires
 * HTTP basic auth with the account SID / auth token.
 * @param {string} url
 * @returns {Promise<string>} Local file path.
 */
async function downloadMedia(url) {
  const response = await withRetry(
    () =>
      axios.get(url, {
        responseType: 'arraybuffer',
        auth: { username: config.twilio.accountSid, password: config.twilio.authToken },
        maxContentLength: 25 * 1024 * 1024, // 25 MB cap
        timeout: 20000,
      }),
    { retries: 2 },
  );
  const tmpPath = path.join(os.tmpdir(), `mudir-voice-${Date.now()}.ogg`);
  fs.writeFileSync(tmpPath, Buffer.from(response.data));
  return tmpPath;
}

/**
 * Transcribe a WhatsApp voice note using Whisper.
 * @param {string} mediaUrl Twilio media URL for the audio attachment.
 * @returns {Promise<string>} Transcribed text.
 */
async function transcribeAudio(mediaUrl) {
  const filePath = await downloadMedia(mediaUrl);
  try {
    const result = await withRetry(
      () =>
        getClient().audio.transcriptions.create({
          file: fs.createReadStream(filePath),
          model: config.openai.whisperModel,
        }),
      { retries: 2, onRetry: (err, a) => logger.warn({ err: err.message, a }, 'Retry transcribe') },
    );
    return (result.text || '').trim();
  } finally {
    // Always clean up the temp file, even on error.
    fs.unlink(filePath, () => {});
  }
}

module.exports = { summarizeConversation, transcribeAudio, downloadMedia, getClient };
