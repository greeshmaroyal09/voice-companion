import httpx
import pytest
from fastapi.testclient import TestClient
from backend import main
from backend.conversation import Conversation, store
from backend.knowledge import ENTRIES, checklist
from backend.preparation import ONBOARDING_QUESTIONS
from backend.test_main import mock_gnani, wav_bytes


def ready():
    c = Conversation()
    c.details.update(intent='open_account', bank='SBI', town='అనంతపురం')
    c.preparation.answers.update(single='yes', adult='yes', resident='yes')
    c.preparation.pending = 'existing'
    result = c.advance('లేదు')
    assert result['preparation']['checklist']
    return c


def test_sbi_retained_and_location_correction_with_no_old_name():
    c = ready()
    result = c.advance('కాదు, బెంగళూరు')
    assert result['details']['town'] == 'బెంగళూరు'
    assert result['details']['bank'] == 'SBI'
    assert result['details']['intent'] == 'open_account'
    assert result['preparation']['checklist']
    assert result['preparation']['pending'] == ''
    result = c.advance('SBI కాదు HDFC bank')
    assert not result['preparation']['checklist']
    assert 'వర్తింపజేయను' in result['reply']


def test_unknown_branch_never_blocks_checklist():
    c = ready()
    result = c.advance('బ్రాంచ్ తెలియదు')
    assert result['details']['branch'] is None
    assert result['preparation']['checklist']
    assert 'ఏ బ్రాంచ్' not in result['reply']


def test_pan_missing_repeat_and_sources():
    c = ready()
    c.advance('PAN అంటే ఏంటి?')
    result = c.advance('నాకు అది లేదు')
    assert result['preparation']['answers']['pan'] == 'no'
    assert 'Form 60' in result['reply'] and 'Form 97' not in result['reply']
    assert 'SBI శాఖతో' in result['reply'] and 'మీ బ్యాంకుతో' not in result['reply']
    assert c.advance('మళ్ళీ చెప్పు')['reply'] == result['reply']
    tax = next(i for i in result['preparation']['checklist'] if i['id'] == 'tax')
    assert tax['status'] == 'needs_confirmation'
    assert tax['branch_confirmation']
    assert 'Form 97' in tax['exceptions']
    assert 'Form No. 97' in tax['sources'][1]['title']
    assert all(s['checked_on'] == '2026-11-08' and s['url'].startswith('https://') for s in tax['sources'])
    result = c.advance('PAN ఉంది')
    assert result['preparation']['answers']['pan'] == 'yes'
    assert 'PAN లేదని చెప్పారు' not in str(result['preparation']['checklist'])


def test_no_aadhaar_has_alternatives_and_no_ovd_has_limited_route():
    c = ready()
    result = c.advance('ఆధార్ లేదు')
    assert 'ఒక్కటే మార్గం కాదు' in result['reply']
    assert 'పాస్‌పోర్ట్' in result['reply']
    result = c.advance('ఏ పత్రమూ లేదు')
    assert 'Small Account' in result['reply']
    assert result['preparation']['checklist'][0]['id'] == 'small'
    result = c.advance('పాస్‌పోర్ట్ ఉంది')
    assert result['preparation']['checklist'][0]['id'] == 'identity'


def test_contextual_missing_identity_and_unlisted_bank():
    c = ready()
    c.advance('నాకు అది లేదు')
    assert c.preparation.pending == 'identity_options'
    result = c.advance('లేదు')
    assert result['preparation']['answers']['identity'] == 'none'
    assert result['preparation']['checklist'][0]['id'] == 'small'
    result = Conversation().advance('Kotak bankలో account తెరవాలి')
    assert result['details']['bank'] == 'Kotak'
    assert not result['preparation']['checklist']


def test_upfront_scope_answers_not_reasked():
    c = Conversation()
    c.advance('నా ఒక్కరి సాధారణ సేవింగ్స్ SBI account తెరవాలి, 30 ఏళ్ల భారత నివాసి, ఇప్పటికే SBI KYC ఉంది')
    result = c.advance('అనంతపురం')
    assert result['preparation']['answers']['adult'] == 'yes'
    assert result['preparation']['answers']['existing'] == 'yes'
    assert result['preparation']['pending'] == ''
    assert result['preparation']['checklist'][0]['id'] == 'existing'


def test_unsupported_customer_and_recovery():
    c = ready()
    result = c.advance('పిల్ల కోసం minor account')
    assert not result['preparation']['checklist']
    assert 'నిర్ధారించండి' in result['reply']
    result = c.advance('కాదు నా ఒక్కరి సాధారణ సేవింగ్స్')
    assert result['preparation']['checklist']


def test_unverified_counts_and_address_dependency():
    c = ready()
    result = c.advance('జిరాక్స్ కాపీలు ఎన్ని?')
    assert 'ధృవీకరించలేదు' in result['reply']
    assert ENTRIES['visit']['status'] == 'unverified'
    result = c.advance('చిరునామా పాతది')
    assert any(i['id'] == 'address' for i in result['preparation']['checklist'])
    result = c.advance('చిరునామా ప్రస్తుతది')
    assert not any(i['id'] == 'address' for i in result['preparation']['checklist'])


def test_tts_failure_preserves_checklist_history_and_retry(monkeypatch):
    monkeypatch.setenv('GNANI_API_KEY', 'test-only')
    responses = iter([httpx.Response(500), httpx.Response(200, content=wav_bytes(rate=24000))])
    mock_gnani(monkeypatch, lambda _: next(responses))
    store.sessions.clear()
    session = Conversation()
    session.details.update(intent='open_account', bank='SBI', town='అనంతపురం')
    session.preparation.answers.update(single='yes', adult='yes', resident='yes', existing='no')
    store.sessions[session.id] = session
    with TestClient(main.app) as client:
        sid = session.id
        turn = client.post('/api/conversation', json={'text': 'documents', 'session_id': sid}).json()
        assert turn['preparation']['checklist']
        request = {'session_id': sid, 'turn_id': turn['turn_id']}
        assert client.post('/api/reply-audio', json=request).status_code == 502
        restored = client.post('/api/conversation/restore', json={'session_id': sid}).json()
        assert restored['preparation'] == turn['preparation']
        assert len(restored['turns']) == 1
        assert restored['turns'][-1]['reply'] == turn['reply']
        assert client.post('/api/reply-audio', json=request).status_code == 200


def natural_walkthrough():
    c = Conversation()
    opening = c.advance('నేను SBIలో ఖాతా తెరవాలనుకుంటున్నా.')
    assert 'SBI' in opening['reply'] and '4' in opening['reply']
    assert len(opening['reply']) < 200
    assert opening['reply'].count('?') == 1
    for key, answer in [('single', 'అవును'), ('adult', 'అవును'), ('resident', 'అవును'), ('existing', 'లేదు')]:
        question = c.advance('అవును') if key == 'single' else result
        assert question['reply'] == ONBOARDING_QUESTIONS[key]
        result = c.advance(answer)
    assert result['preparation']['focus'] == 'identity'
    return c, result


def test_natural_opening_onboards_then_covers_one_item_per_turn():
    c, identity = natural_walkthrough()
    assert 'PAN' not in identity['reply'] and 'కాపీల' not in identity['reply']
    address = c.advance('ఉంది')
    assert address['preparation']['focus'] == 'address'
    assert 'PAN' not in address['reply']
    pan = c.advance('అవును')
    assert pan['preparation']['focus'] == 'tax' and 'PAN' in pan['reply']
    visit = c.advance('PAN ఉంది')
    assert visit['preparation']['focus'] == 'visit'
    assert visit['preparation']['answers']['pan'] == 'yes'
    assert 'PAN' not in visit['reply']
    for turn in (identity, address, pan, visit):
        assert turn['reply'].count('?') == 1
        assert len(turn['reply']) < 200
        assert turn['preparation']['checklist'] == checklist(turn['preparation']['answers'])


@pytest.mark.parametrize('answer', ['లేదు', 'PAN లేదు'])
def test_walkthrough_no_pan_keeps_fact_on_continue(answer):
    c, _ = natural_walkthrough()
    c.advance('తర్వాత')
    c.advance('తర్వాత')
    missing = c.advance(answer)
    assert 'Form 60' in missing['reply'] and 'Form 97' not in missing['reply']
    assert missing['reply'].count('SBI శాఖతో') == 1
    assert missing['reply'].count('?') == 1
    assert c.advance('మళ్ళీ చెప్పు')['reply'] == missing['reply']
    visit = c.advance('అవును')
    assert visit['preparation']['focus'] == 'visit'
    assert visit['preparation']['answers']['pan'] == 'no'


@pytest.mark.parametrize('bank', [None, 'SBI', 'HDFC'])
def test_hypothetical_pan_reply_uses_known_bank_without_saving_possession(bank):
    c = Conversation()
    c.details['bank'] = bank
    reply = c.advance('PAN లేకపోతే ఏం చేయాలి?')
    assert 'Form 60' in reply['reply'] and 'Form 97' not in reply['reply']
    assert (f'{bank} శాఖతో' if bank else 'మీ బ్యాంకుతో') in reply['reply']
    assert 'pan' not in reply['preparation']['answers']


def test_repeat_next_full_list_preserve_panel_and_do_not_answer_onboarding():
    c = Conversation()
    first = c.advance('SBI account open')
    assert c.advance('మళ్ళీ చెప్పు')['reply'] == first['reply']
    c.advance('అవును')
    full = c.advance('మొత్తం జాబితా చెప్పు')
    assert 'PAN' in full['reply'] and 'పాస్‌పోర్ట్' in full['reply']
    assert c.preparation.pending == 'single' and c.preparation.answers == {}
    skipped = c.advance('తర్వాత')
    assert skipped['reply'] == ONBOARDING_QUESTIONS['adult']
    assert skipped['preparation']['answers'] == {}
    c, identity = natural_walkthrough()
    full = c.advance('మొత్తం జాబితా చెప్పు')
    assert 'PAN' in full['reply'] and 'ఫోటో' in full['reply']
    assert full['preparation']['focus'] == 'identity'
    assert full['preparation']['checklist'] == identity['preparation']['checklist']
    assert c.advance('మళ్ళీ చెప్పు')['reply'] == full['reply']
    assert c.advance('తర్వాత')['preparation']['focus'] == 'address'


@pytest.mark.parametrize('command', ['కొనసాగించు', 'తర్వాత'])
def test_document_interruption_resumes_same_item_then_progresses(command):
    c, identity = natural_walkthrough()
    explanation = c.advance('PAN అంటే ఏంటి?')
    assert 'Permanent Account Number' in explanation['reply']
    assert c.preparation.saved_focus == 'identity'
    c.advance('నాకు అది లేదు')
    resumed = c.advance(command)
    assert resumed['reply'] == identity['reply']
    assert resumed['preparation']['focus'] == 'identity'
    assert resumed['preparation']['answers']['pan'] == 'no'
    assert c.advance('ఉంది')['preparation']['focus'] == 'address'


def test_address_no_explains_one_item_and_continue_preserves_old_address():
    c, _ = natural_walkthrough()
    c.advance('ఉంది')
    missing = c.advance('లేదు')
    assert 'మూడు నెలల్లో' in missing['reply'] and 'PAN' not in missing['reply']
    pan = c.advance('అవును')
    assert pan['preparation']['focus'] == 'tax'
    assert pan['preparation']['answers']['address'] == 'old'
