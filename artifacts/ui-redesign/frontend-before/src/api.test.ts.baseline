import { afterEach, expect, it, vi } from 'vitest';
import { apiRequest } from './api';

afterEach(() => vi.unstubAllGlobals());

it('preserves actionable backend errors', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: 'No speech was detected.' }), { status: 422 })));
  await expect(apiRequest('/api/transcribe')).rejects.toThrow('No speech was detected.');
});
it('handles a stopped backend without exposing internals', async () => {
  vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('internal error')));
  await expect(apiRequest('/api/health')).rejects.toThrow('Start FastAPI on port 8000');
});
it('handles non-JSON proxy failures', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('proxy error', { status: 500 })));
  await expect(apiRequest('/api/health')).rejects.toThrow('Check that FastAPI is running');
});

it('sends conversation turn requests and receives dialogue state', async () => {
  const fakeTurn = {
    turn_id: 'turn-123',
    session_id: 'sess-456',
    transcript: 'నేను SBI bankలో ఖాతా తెరవాలి',
    reply: 'SBI బ్యాంకులో ఖాతా తెరవడం కోసం సహాయం కావాలని గుర్తుంచుకున్నాను. మీరు ఏ పట్టణం లేదా బ్రాంచ్‌కు వెళ్లాలనుకుంటున్నారు?',
    details: { intent: 'open_account', bank: 'SBI', town: null, branch: null },
    awaiting: 'location',
  };
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify(fakeTurn), { status: 200, headers: { 'Content-Type': 'application/json' } })));
  const response = await apiRequest('/api/conversation', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text: fakeTurn.transcript }),
  });
  const data = await response.json();
  expect(data.details.bank).toBe('SBI');
  expect(data.details.intent).toBe('open_account');
  expect(data.awaiting).toBe('location');
});
