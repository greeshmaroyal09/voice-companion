import io
import struct
import wave

import httpx
import pytest
from fastapi.testclient import TestClient

from backend import main
from backend.audio import playable_wav
from backend.conversation import Conversation, ConversationStore, store
from backend.preparation import ONBOARDING_QUESTIONS
from backend.test_main import mock_gnani, wav_bytes


def test_telugu_multiturn_corrections():
    c = Conversation()
    first = c.advance("నేను SBI bankలో ఖాతా తెరవాలి")
    assert first["details"] == {"intent": "open_account", "bank": "SBI", "town": None, "branch": None}
    assert first["awaiting"] == ""
    assert "SBI" in first["reply"] and len(first["reply"]) < 200
    second = c.advance("విజయవాడ")
    assert second["details"]["town"] == "విజయవాడ"
    assert second["awaiting"] == ""
    bank_correction = c.advance("SBI కాదు HDFC bank")
    assert bank_correction["details"]["bank"] == "HDFC"
    assert bank_correction["details"]["town"] == "విజయవాడ"
    town_correction = c.advance("విజయవాడ కాదు గుంటూరు")
    assert town_correction["details"]["town"] == "గుంటూరు"
    assert town_correction["details"]["intent"] == "open_account"
    c.advance("లక్ష్మీపురం బ్రాంచ్")
    branch_correction = c.advance("లక్ష్మీపురం బ్రాంచ్ కాదు అరండల్‌పేట బ్రాంచ్")
    assert branch_correction["details"]["branch"] == "అరండల్‌పేట"
    assert "లక్ష్మీపురం" not in branch_correction["reply"]
    assert len(c.turns) == 6


def test_bank_correction_does_not_become_town():
    c = Conversation()
    c.advance("SBI bankలో ఖాతా తెరవాలి")
    result = c.advance("కాదు HDFC bank")
    assert result["details"]["bank"] == "HDFC"
    assert result["details"]["town"] is None
    assert result["awaiting"] == "location"


def test_bank_correction_invalidates_only_branch():
    c = Conversation()
    c.advance("SBI account open")
    c.advance("గుంటూరు")
    c.advance("లక్ష్మీపురం branch")
    result = c.advance("SBI కాదు HDFC bank")
    assert result["details"]["town"] == "గుంటూరు"
    assert result["details"]["branch"] is None


def test_intent_negation_and_change():
    c = Conversation()
    first = c.advance("నాకు SBIలో ఖాతా తెరవాలి")
    assert first["details"]["intent"] == "open_account"
    cleared = c.advance("ఖాతా తెరవడం కాదు")
    assert cleared["details"]["intent"] is None
    assert cleared["awaiting"] == "intent"
    changed = c.advance("డబ్బులు విత్‌డ్రా చేయాలి")
    assert changed["details"]["intent"] == "withdraw"
    assert changed["details"]["bank"] == "SBI"
    assert changed["awaiting"] == "location"


def test_location_negation_without_replacement():
    c = Conversation()
    c.advance("నేను SBI bankలో ఖాతా తెరవాలి")
    c.advance("విజయవాడ")
    assert c.details["town"] == "విజయవాడ"
    assert c.awaiting == ""
    cleared = c.advance("విజయవాడ కాదు")
    assert cleared["details"]["town"] is None
    assert cleared["awaiting"] == ""
    assert cleared["reply"] == ONBOARDING_QUESTIONS['single']


def test_telugu_account_variations():
    for phrase in ["కొత్త ఖాతా కావాలి", "SBI ఖాతా ప్రారంభించాలి", "SBI account opening"]:
        c = Conversation()
        res = c.advance(phrase)
        assert res["details"]["intent"] == "open_account"


def test_unknown_location_is_not_stored_or_repeatedly_demanded():
    c = Conversation()
    c.advance("SBI ఖాతా తెరవాలి")
    result = c.advance("ఇంకా తెలియదు")
    assert result["details"]["town"] is None
    assert result['reply'] == ONBOARDING_QUESTIONS['single']


def test_checklist_request_waits_for_onboarding_without_assuming_answers():
    c = Conversation()
    c.advance("SBI ఖాతా తెరవాలి")
    c.advance("గుంటూరు")
    result = c.advance("ఏ పత్రాలు అవసరం?")
    assert result['preparation']['checklist'] == []  # Assumptions stay out of saved eligibility facts.
    assert result['reply'] == ONBOARDING_QUESTIONS['single']
    assert result['preparation']['answers'].get('adult') is None
    assert result['preparation']['answers'].get('resident') is None
    assert result['preparation']['answers'].get('single') is None


def test_document_request_synonyms_are_checklist_requests():
    from backend.conversation import checklist_request
    for phrase in ["ఏం పత్రాలు కావాలి?", "ఏం డాక్యుమెంట్స్ కావాలి?", "what documents do I need?"]:
        assert checklist_request(phrase, None)


def test_quick_checklist_updates_for_joint_minor_and_nonresident_scope():
    for followup in ["joint account", "minor account", "NRI account"]:
        c = Conversation()
        first = c.advance("నేను SBI బ్యాంకులో ఖాతా తెరవాలనుకుంటున్నాను")
        result = c.advance(followup)
        assert first["preparation"]["answers"] == {}
        assert result["preparation"]["checklist"] == []
        assert "ప్రస్తుతం SBIలో భారత నివాసి" in result["reply"]
        assert result["awaiting"] == ""


def _ready_for_preparation():
    c = Conversation()
    c.details.update(intent="open_account", bank="SBI", town="విజయవాడ")
    c.preparation.pending = "single"
    return c


def _answer_onboarding(c):
    # The first turn asks scope; the following answers establish eligibility
    # until the existing-SBI-KYC question is pending.
    for answer in ("అవును", "అవును", "అవును"):
        c.advance(answer)
    return c


def test_scope_yes_sets_only_account_type_then_asks_age():
    c = _ready_for_preparation()
    result = c.advance("అవును")
    assert c.preparation.answers == {"single": "yes"}
    assert c.preparation.pending == "adult"
    assert result["reply"] == ONBOARDING_QUESTIONS["adult"]


def test_pan_interruption_keeps_onboarding_question_and_routes_pronoun_to_pan():
    c = _ready_for_preparation()
    _answer_onboarding(c)
    pending = c.preparation.pending
    assert pending == "existing"

    explanation = c.advance("PAN అంటే ఏంటి?")
    assert "Permanent Account Number" in explanation["reply"]
    assert explanation["preparation"]["pending"] == pending
    assert explanation["preparation"]["interrupted"] is True

    missing = c.advance("నాకు అది లేదు")
    assert c.preparation.answers["pan"] == "no"
    assert c.preparation.pending == pending
    assert "Form" in missing["reply"]

    repeated = c.advance("మళ్ళీ చెప్పు")
    assert repeated["reply"] == missing["reply"]
    explained = c.advance("అది ఏంటి?")
    assert "PAN" in explained["reply"]
    resumed = c.advance("తర్వాత")
    assert resumed["reply"] == "ఇప్పటికే SBIలో KYC పూర్తయిన ఖాతా ఉందా?"
    assert c.preparation.pending == pending

    answered = c.advance("లేదు")
    assert answered["preparation"]["answers"]["existing"] == "no"
    assert answered["preparation"]["answers"]["pan"] == "no"


def test_pan_interruption_after_checklist_restores_checklist_position():
    c = _ready_for_preparation()
    _answer_onboarding(c)
    c.advance("అవును")
    checklist = c.advance("పత్రాల జాబితా")
    assert checklist["preparation"]["checklist"]
    c.advance("తర్వాత")
    original_focus = c.preparation.focus
    ids = [item["id"] for item in checklist["preparation"]["checklist"]]

    c.advance("PAN అంటే ఏంటి?")
    missing = c.advance("నాకు అది లేదు")
    assert c.preparation.answers["pan"] == "no"
    assert c.preparation.pending == ""
    assert "Form" in missing["reply"]
    c.advance("మళ్ళీ చెప్పు")
    c.advance("అది ఏంటి?")
    resumed = c.advance("తర్వాత")
    assert c.preparation.focus.removesuffix('_missing') == original_focus
    assert resumed["preparation"]["checklist"]


def test_intent_asked_once_then_bank_then_walkthrough():
    c = Conversation()
    assert c.advance("నమస్తే")["awaiting"] == "intent"
    assert c.advance("ఖాతా తెరవాలి")["awaiting"] == "bank"
    result = c.advance("ఎస్ బి ఐ")
    assert result["awaiting"] == ""
    assert result['preparation']['focus'] == 'intro'
    assert result["reply"].count("?") == 1


def test_sessions_are_isolated_and_expire():
    sessions = ConversationStore()
    one, two = sessions.get(), sessions.get()
    one.advance("SBI ఖాతా తెరవాలి")
    assert two.details["bank"] is None
    one.touched -= 3601
    with pytest.raises(main.HTTPException) as error:
        sessions.get(one.id)
    assert error.value.status_code == 404


def test_unknown_length_tts_wav_is_repaired_without_changing_samples():
    normal = wav_bytes(rate=24000)
    streaming = bytearray(normal)
    struct.pack_into("<I", streaming, 4, 0xFFFFFFFF)
    struct.pack_into("<I", streaming, 40, 0xFFFFFFFF)
    fixed = playable_wav(bytes(streaming))
    assert fixed == normal
    with wave.open(io.BytesIO(fixed), "rb") as wav:
        assert wav.getnframes() == 24000
        assert len(wav.readframes(24000)) == 48000


def test_real_truncation_and_unaligned_pcm_are_rejected():
    with pytest.raises(ValueError):
        playable_wav(wav_bytes(rate=24000)[:-10])
    streaming = bytearray(wav_bytes(rate=24000)[:-1])
    struct.pack_into("<I", streaming, 4, 0xFFFFFFFF)
    struct.pack_into("<I", streaming, 40, 0xFFFFFFFF)
    with pytest.raises(ValueError):
        playable_wav(bytes(streaming))


def test_streaming_data_size_with_finalized_riff():
    normal = wav_bytes(rate=24000)
    streaming = bytearray(normal)
    struct.pack_into('<I', streaming, 40, 0xFFFFFFFF)
    assert playable_wav(bytes(streaming)) == normal


def test_town_in_first_sentence_is_not_requested_again():
    result = Conversation().advance('నేను గుంటూరులో SBI bankలో ఖాతా తెరవాలి')
    assert result['details'] == {'intent': 'open_account', 'bank': 'SBI', 'town': 'గుంటూరు', 'branch': None}
    assert result['awaiting'] == ''


def test_location_answer_with_immediate_self_correction():
    c = Conversation()
    c.advance('SBI ఖాతా తెరవాలి')
    result = c.advance('విజయవాడ కాదు గుంటూరు')
    assert result['details']['town'] == 'గుంటూరు'
    assert 'విజయవాడ' not in result['reply']


def test_remove_labeled_branch_then_replace_and_correct_intent():
    c = Conversation()
    c.advance('SBI ఖాతా తెరవాలి')
    c.advance('గుంటూరు')
    c.advance('లక్ష్మీపురం బ్రాంచ్')
    result = c.advance('లక్ష్మీపురం బ్రాంచ్ కాదు')
    assert result['details']['branch'] is None
    assert result['details']['town'] == 'గుంటూరు'
    c.advance('అరండల్‌పేట బ్రాంచ్')
    result = c.advance('ఖాతా తెరవడం కాదు ఖాతా మూసివేయాలి')
    assert result['details']['intent'] == 'close_account'
    assert result['details']['branch'] == 'అరండల్‌పేట'
    assert result['details']['bank'] == 'SBI'


def test_api_multiturn_voice_text_restore_and_exact_turn_tts(monkeypatch):
    store.sessions.clear()
    monkeypatch.setenv("GNANI_API_KEY", "test-only")
    texts = iter(["నేను SBI bankలో ఖాతా తెరవాలి", "విజయవాడ"])
    spoken = []
    def handler(request):
        if str(request.url) == main.STT_URL:
            return httpx.Response(200, json={"success": True, "transcript": next(texts)})
        import json
        spoken.append(json.loads(request.read())["text"])
        return httpx.Response(200, content=wav_bytes(rate=24000))
    mock_gnani(monkeypatch, handler)
    with TestClient(main.app) as client:
        first = client.post('/api/transcribe', files={'audio': ('recording.wav', wav_bytes(), 'audio/wav')}).json()
        sid = first['session_id']
        second = client.post('/api/transcribe', data={'session_id': sid}, files={'audio': ('recording.wav', wav_bytes(), 'audio/wav')}).json()
        third = client.post('/api/conversation', json={'session_id': sid, 'text': 'SBI కాదు HDFC bank'}).json()
        assert third['details']['town'] == 'విజయవాడ'
        assert third['details']['bank'] == 'HDFC'
        restored = client.post('/api/conversation/restore', json={'session_id': sid}).json()
        assert len(restored['turns']) == 3
        for turn in [first, third]:
            response = client.post('/api/reply-audio', json={'session_id': sid, 'turn_id': turn['turn_id']})
            assert response.status_code == 200
            assert spoken[-1] == turn['reply']
        other = client.post('/api/conversation', json={'text': 'నమస్తే'}).json()
        assert client.post('/api/reply-audio', json={'session_id': other['session_id'], 'turn_id': first['turn_id']}).status_code == 404
        assert client.post('/api/conversation/reset', json={'session_id': sid}).status_code == 200
        assert client.post('/api/conversation/restore', json={'session_id': sid}).status_code == 404
