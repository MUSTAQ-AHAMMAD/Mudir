// notifications.js
// -----------------------------------------------------------------------------
// All outbound WhatsApp messaging goes through here. Uses the Twilio SDK with
// retry/backoff so transient network errors don't drop notifications.
// The Twilio client is created lazily so tests can run without credentials.
// -----------------------------------------------------------------------------
'use strict';

const twilio = require('twilio');
const { config } = require('./config');
const logger = require('./logger');
const { withRetry, normalizeWhatsApp } = require('./utils');

let twilioClient = null;

/**
 * Get the shared Twilio client, creating it on first use.
 * @returns {import('twilio').Twilio}
 */
function getClient() {
  if (twilioClient) return twilioClient;
  if (!config.twilio.accountSid || !config.twilio.authToken) {
    throw new Error('Twilio is not configured (TWILIO_ACCOUNT_SID / TWILIO_AUTH_TOKEN).');
  }
  twilioClient = twilio(config.twilio.accountSid, config.twilio.authToken);
  return twilioClient;
}

/**
 * Send a WhatsApp message to a single recipient with retry/backoff.
 * @param {string} to    Recipient (raw number or "whatsapp:+…").
 * @param {string} body  Message text.
 * @returns {Promise<{sid: string}|null>}
 */
async function sendMessage(to, body) {
  const recipient = normalizeWhatsApp(to);
  try {
    const message = await withRetry(
      () =>
        getClient().messages.create({
          from: config.twilio.whatsappFrom,
          to: recipient,
          body,
        }),
      {
        retries: 3,
        onRetry: (err, attempt) =>
          logger.warn({ err: err.message, attempt, to: recipient }, 'Retrying WhatsApp send'),
      },
    );
    logger.info({ sid: message.sid, to: recipient }, 'WhatsApp message sent');
    return { sid: message.sid };
  } catch (err) {
    // Never let a failed notification crash a command flow; log and continue.
    logger.error({ err: err.message, to: recipient }, 'Failed to send WhatsApp message');
    return null;
  }
}

/**
 * Send the same message to many recipients.
 * @param {string[]} recipients
 * @param {string} body
 * @returns {Promise<void>}
 */
async function broadcast(recipients, body) {
  await Promise.all((recipients || []).filter(Boolean).map((to) => sendMessage(to, body)));
}

module.exports = { sendMessage, broadcast, getClient };
