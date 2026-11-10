"""Synthetic API smoke journey through Vite; use a backend with Gemini disabled."""
import os
from pathlib import Path
import httpx


if __name__ == '__main__':
    base_url = os.getenv('VOICE_COMPANION_BASE_URL', 'http://127.0.0.1:5173')
    transcript = ['# Guided SBI preparation smoke transcript', '']
    with httpx.Client(base_url=base_url, timeout=15) as client:
        sid = None
        turns = []

        def say(text, *, focus=None, pending=None):
            global sid
            response = client.post('/api/conversation', json={'text': text, 'session_id': sid})
            response.raise_for_status()
            turn = response.json()
            sid = turn['session_id']
            assert turn['reply'].count('?') <= 1
            if focus is not None:
                assert turn['preparation']['focus'] == focus, turn
            if pending is not None:
                assert turn['preparation']['pending'] == pending, turn
            turns.append(turn)
            transcript.extend([f'## Turn {len(turns)}', '', f'User: {text}', '', f"Assistant: {turn['reply']}", ''])
            return turn

        first = say('నేను SBIలో ఖాతా తెరవాలనుకుంటున్నా.', focus='intro')
        assert len(first['reply']) < 200 and 'SBI' in first['reply']
        say('అవును', pending='single')
        say('అవును', pending='adult')
        say('అవును', pending='resident')
        say('అవును', pending='existing')
        identity = say('లేదు', focus='identity', pending='')
        say('అనంతపురం', focus='identity')
        say('కాదు, బెంగళూరు', focus='identity')
        say('బ్రాంచ్ తెలియదు', focus='identity')
        say('ఉంది', focus='address')
        say('అవును', focus='tax')
        say('PAN అంటే ఏంటి?')
        say('నాకు అది లేదు')
        resumed = say('కొనసాగించు', focus='tax_missing')
        assert resumed['preparation']['answers']['pan'] == 'no'
        missing = resumed
        assert 'Form 60' in missing['reply'] and 'Form 97' not in missing['reply']
        assert 'SBI శాఖతో' in missing['reply']
        assert say('మళ్ళీ చెప్పు')['reply'] == missing['reply']
        full = say('మొత్తం జాబితా చెప్పు', focus='tax_missing')
        assert 'PAN' in full['reply'] and 'ఫోటో' in full['reply']
        visit = say('అవును', focus='visit')
        assert visit['preparation']['answers']['pan'] == 'no'
        say('PAN లేకపోతే ఏం చేయాలి?')
        assert say('తర్వాత', focus='visit')['reply'] == visit['reply']
        turn = say('అవును', focus='done')
        assert turn['details']['bank'] == 'SBI'
        assert turn['details']['town'] == 'బెంగళూరు'
        assert turn['details']['branch'] is None
        assert turn['preparation']['answers']['pan'] == 'no'
        assert turn['preparation']['answers']['single'] == 'yes'
        assert turn['preparation']['answers']['adult'] == 'yes'
        assert turn['preparation']['answers']['resident'] == 'yes'
        assert turn['preparation']['answers']['existing'] == 'no'
        assert turn['preparation']['checklist']
        assert identity['preparation']['checklist']
        turn = say('అవును', focus='done')
        assert 'PAN' in turn['reply'] and 'ఫోటో' in turn['reply']
        restored = client.post('/api/conversation/restore', json={'session_id': sid}).json()
        assert restored['preparation'] == turn['preparation']
        assert restored['turns'] == [{key: t[key] for key in ('turn_id', 'transcript', 'reply')} for t in turns]
        changed = say('SBI కాదు HDFC bank')
        assert changed['details']['bank'] == 'HDFC'
        assert not changed['preparation']['checklist']
        client.post('/api/conversation/reset', json={'session_id': sid}).raise_for_status()
        assert client.post('/api/conversation/restore', json={'session_id': sid}).status_code == 404
        output = Path('artifacts/preparation-smoke-transcript.md')
        output.parent.mkdir(exist_ok=True)
        output.write_text('\n'.join(transcript), encoding='utf-8')
        print('\n'.join(transcript))
        print(f'PASS: {len(turns)} synthetic turns; onboarding, one-item progression, PAN absence, repeat/full list, interruption/resume, corrections, restore/reset, unsupported bank. Vite proxy healthy. Transcript: {output}')
