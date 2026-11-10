import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { Conversation, type ConversationTurn } from './Conversation';

const props = { turns: [] as ConversationTurn[], disabled: false, loading: false, loadingText: 'Thinking through your question…', restoring: false, onAsk: () => {}, audioBusy: false, playing: false, audioUrl: '', onListen: () => {} };
const turn = (id: string, transcript = 'PAN అంటే ఏంటి?'): ConversationTurn => ({ session_id: 'same-session', turn_id: id, transcript, reply: `సమాధానం ${id}\nSecond line <safe>`, details: { bank: 'SBI' } });

describe('unified text and voice conversation presentation', () => {
  it('offers real question starters without presenting invented conversation turns', () => {
    const html = renderToStaticMarkup(<Conversation {...props} disabled />);
    expect(html).toContain('Open a bank account');
    expect(html).toContain('Understand a document');
    expect(html.match(/<button[^>]*disabled/g)).toHaveLength(2);
    expect(html).not.toContain('message-user');
    expect(html).not.toContain('Listen to reply');
  });
  it('retains all turns, multilingual text, and long multiline replies in order', () => {
    const turns = [turn('first', 'తెలుగు & English'), turn('second', 'a'.repeat(2000))];
    const html = renderToStaticMarkup(<Conversation {...props} turns={turns} audioUrl="blob:test" />);
    expect(html.indexOf('సమాధానం first')).toBeLessThan(html.indexOf('సమాధానం second'));
    expect(html).toContain('తెలుగు &amp; English');
    expect(html).toContain('a'.repeat(2000));
    expect(html).toContain('\nSecond line &lt;safe&gt;');
    expect(html).toContain('role="log"');
    expect(html.match(/aria-label="Listen to reply"/g)).toHaveLength(1);
  });
  it('presents actual processing, playback, preparation, and retry states distinctly', () => {
    const turns = [turn('only')];
    const loading = renderToStaticMarkup(<Conversation {...props} turns={turns} loading disabled />);
    expect(loading).toContain('Thinking through your question…');
    expect(loading).toContain('aria-busy="true"');
    const processing = renderToStaticMarkup(<Conversation {...props} turns={turns} audioBusy />);
    expect(processing).toContain('Preparing reply audio');
    expect(processing).toContain('disabled');
    const playing = renderToStaticMarkup(<Conversation {...props} turns={turns} audioUrl="blob:test" playing />);
    expect(playing).toContain('Stop reply playback');
    expect(playing).toContain('playback-indicator');
    const retry = renderToStaticMarkup(<Conversation {...props} turns={turns} />);
    expect(retry).toContain('Retry generating reply audio');
    expect(retry).not.toContain('playback-indicator');
  });
});
