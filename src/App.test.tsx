import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import App from './App';

describe('accessible conversation shell', () => {
  it('provides one labelled multiline composer, independent microphone access, and honest language support', () => {
    const html = renderToStaticMarkup(<App />);
    expect(html).toContain('Skip to message');
    expect(html).toContain('for="message"');
    expect(html).toContain('<textarea');
    expect(html).toContain('maxLength="2000"');
    expect(html).toContain('aria-label="Send message"');
    expect(html).toContain('aria-label="Start recording"');
    expect(html).toContain('aria-label="Start recording from message composer"');
    expect(html).toContain('English text');
    expect(html).not.toContain('<select');
    expect(html).not.toContain('type="file"');
    expect(html).toContain('Restoring your conversation');
    expect(html).not.toContain('Listening to you');
  });
});
