// tests/ai-service.test.js
// Security-focused tests for the media-URL allowlist (SSRF prevention).
'use strict';

const { assertTrustedMediaUrl } = require('../src/ai-service');

describe('assertTrustedMediaUrl (SSRF guard)', () => {
  test('accepts trusted Twilio hosts over HTTPS', () => {
    expect(() => assertTrustedMediaUrl('https://api.twilio.com/2010-04-01/x.ogg')).not.toThrow();
    expect(() => assertTrustedMediaUrl('https://media.twiliocdn.com/abc')).not.toThrow();
    expect(() => assertTrustedMediaUrl('https://mcs.us1.twilio.com/Media/x')).not.toThrow();
  });

  test('rejects untrusted hosts', () => {
    expect(() => assertTrustedMediaUrl('https://evil.example.com/x')).toThrow(/untrusted host/);
    expect(() => assertTrustedMediaUrl('https://api.twilio.com.evil.com/x')).toThrow(/untrusted host/);
  });

  test('rejects non-HTTPS and internal targets', () => {
    expect(() => assertTrustedMediaUrl('http://api.twilio.com/x')).toThrow(/HTTPS/);
    expect(() => assertTrustedMediaUrl('http://169.254.169.254/latest/meta-data')).toThrow();
    expect(() => assertTrustedMediaUrl('file:///etc/passwd')).toThrow();
    expect(() => assertTrustedMediaUrl('not a url')).toThrow(/Invalid media URL/);
  });
});
