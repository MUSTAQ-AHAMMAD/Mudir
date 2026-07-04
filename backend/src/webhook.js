// webhook.js
// -----------------------------------------------------------------------------
// Express router for the Twilio WhatsApp webhook. Responsibilities:
//   * Verify the incoming request is genuinely from Twilio (signature check).
//   * Parse text commands OR voice notes.
//   * Route text commands to the command handlers, honouring any pending
//     voice-note confirmation.
//   * Reply using TwiML (Twilio's XML response format).
//
// Twilio posts application/x-www-form-urlencoded bodies. We reply with TwiML so
// the response appears immediately in the chat.
// -----------------------------------------------------------------------------
'use strict';

const express = require('express');
const twilio = require('twilio');
const { config } = require('./config');
const logger = require('./logger');
const { parseCommand } = require('./utils');
const commands = require('./commands');
const voice = require('./voice-handler');
const { t } = require('./templates');

const router = express.Router();

/**
 * Express middleware verifying the X-Twilio-Signature header. Rejects forged
 * requests with 403. Skipped when `TWILIO_VALIDATE_SIGNATURE=false` (tests).
 */
function validateTwilioSignature(req, res, next) {
  if (!config.twilio.validateSignature) return next();
  const signature = req.headers['x-twilio-signature'];
  // The URL Twilio signed is the full public URL of this endpoint.
  const url = `${config.publicUrl}${req.originalUrl}`;
  const valid = twilio.validateRequest(config.twilio.authToken, signature, url, req.body || {});
  if (!valid) {
    logger.warn({ url }, 'Rejected request with invalid Twilio signature');
    return res.status(403).send('Invalid signature');
  }
  return next();
}

/**
 * Build a TwiML reply containing a single message.
 * @param {string} body
 * @returns {string} XML string.
 */
function twiml(body) {
  const response = new twilio.twiml.MessagingResponse();
  response.message(body);
  return response.toString();
}

/**
 * Core handler exported for direct unit/e2e testing without HTTP.
 * @param {object} payload Twilio-style body: { From, Body, NumMedia, MediaUrl0, MediaContentType0 }.
 * @param {object} [deps]
 * @returns {Promise<string>} Reply text.
 */
async function processIncoming(payload, deps = {}) {
  const sender = payload.From;
  const body = (payload.Body || '').trim();
  const numMedia = parseInt(payload.NumMedia || '0', 10);

  // 1. Voice note handling.
  if (numMedia > 0 && /^audio\//.test(payload.MediaContentType0 || '')) {
    // Use the newest project as context for a spoken "we're done".
    const db = deps.db || require('./database');
    const projects = await db.listProjects();
    const projectId = projects[0] ? projects[0].code : undefined;
    return voice.handleVoiceNote({ mediaUrl: payload.MediaUrl0, sender, projectId }, deps);
  }

  // 2. Confirmation of a previously transcribed voice command.
  const pending = voice.getPending(sender);
  if (pending) {
    const decision = voice.parseConfirmation(body);
    if (decision === 'yes') {
      voice.clearPending(sender);
      return commands.dispatch(pending.command, sender, deps);
    }
    if (decision === 'no') {
      voice.clearPending(sender);
      return '❌ تم الإلغاء. / Cancelled.';
    }
    // Anything else: fall through to normal command parsing.
  }

  // 3. Normal text command.
  const command = parseCommand(body);
  if (!command) return t('unknown');
  return commands.dispatch(command, sender, deps);
}

// POST /webhook — Twilio inbound messages.
router.post('/webhook', validateTwilioSignature, async (req, res) => {
  try {
    const reply = await processIncoming(req.body || {});
    res.type('text/xml').send(twiml(reply));
  } catch (err) {
    logger.error({ err: err.message, stack: err.stack }, 'Webhook processing failed');
    // Always return valid TwiML so Twilio doesn't retry-storm us.
    res.type('text/xml').send(twiml('⚠️ حدث خطأ. / Something went wrong. Please try again.'));
  }
});

module.exports = { router, processIncoming, validateTwilioSignature };
