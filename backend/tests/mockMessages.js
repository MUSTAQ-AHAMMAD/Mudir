// tests/mockMessages.js
// Helpers that build Twilio-style webhook payloads for tests.
'use strict';

/**
 * A plain text WhatsApp message payload.
 * @param {string} from  Sender (e.g. "whatsapp:+1").
 * @param {string} body  Message text.
 */
function text(from, body) {
  return { From: from, Body: body, NumMedia: '0' };
}

/**
 * A voice-note WhatsApp message payload.
 * @param {string} from     Sender.
 * @param {string} mediaUrl Twilio media URL.
 */
function voice(from, mediaUrl) {
  return {
    From: from,
    Body: '',
    NumMedia: '1',
    MediaUrl0: mediaUrl,
    MediaContentType0: 'audio/ogg',
  };
}

module.exports = { text, voice };
