import json

import httpx
import pytest
from fastapi.testclient import TestClient

from backend import gemini, main
from backend.conversation import Conversation, store
from backend.test_main import wav_bytes


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("GNANI_API_KEY", "test-gnani-key")
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-3.8-flash")
    store.sessions.clear()
    with TestClient(main.app) as test_client:
        yield test_client


def interpreted(kind, *, intent="open_account", document="none", numbers=None, unclear=False):
    return {
        "request_kind": kind,
        "intent": intent,
        "bank": "",
        "document": document,
        "form_numbers": numbers or [],
        "unclear_form_reference": unclear,
        "account_for_self": False,
        "account_for_self_explicit": False,
        "age_years": 0,
        "age_explicit": False,
        "age_subject": "unknown",
        "adult": False,
        "adult_explicit": False,
        "corrections": [],
    }


def prepare_known_sbi_session():
    session = Conversation()
    session.details.update(intent="open_account", bank="SBI", town="విజయవాడ")
    session.preparation.answers.update(single="yes", adult="yes", resident="yes", existing="yes")
    store.sessions[session.id] = session
    return session


def mock_providers(monkeypatch, responses, transcript):
    outputs = iter(responses)
    original = httpx.AsyncClient
    seen_gemini = []

    def handler(request):
        if request.url.host == "generativelanguage.googleapis.com":
            assert request.headers["x-goog-api-key"] == "test-gemini-key"
            payload = json.loads(request.read())
            assert request.url.path.endswith("/models/gemini-3.8-flash:generateContent")
            assert payload["generationConfig"]["responseMimeType"] == "application/json"
            assert "responseSchema" in payload["generationConfig"]
            schema = payload["generationConfig"]["responseSchema"]
            assert schema["type"] == "OBJECT" and "$defs" not in schema
            assert "$ref" not in json.dumps(schema)
            user_input = payload["contents"][0]["parts"][0]["text"]
            seen_gemini.append(json.loads(user_input))
            return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": json.dumps(next(outputs), ensure_ascii=False)}]}}]})
        if request.url.host == "api.vachana.ai":
            assert request.url.path == "/stt/v3"
            return httpx.Response(200, json={"success": True, "transcript": transcript, "model": "prisma-v3.0"})
        pytest.fail(f"Unexpected outbound host: {request.url.host}")

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(gemini.httpx, "AsyncClient", lambda **kwargs: original(transport=transport, **kwargs))
    return seen_gemini


def test_typed_checklist_form_clarification_and_followup_share_handler(client, monkeypatch):
    session = prepare_known_sbi_session()
    unclear_form_text = "PAN గురించి Form 60 చెప్పండి, ఇంకో form number స్పష్టంగా అర్థం కాలేదు. ఏది?"
    followup_text = "అది Form 97"
    seen = mock_providers(monkeypatch, [
        interpreted("document_checklist", document="checklist"),
        interpreted("document_question", document="declaration", numbers=["60"], unclear=True),
        interpreted("document_question", document="declaration", numbers=["97"]),
    ], unclear_form_text)

    first = client.post("/api/conversation", json={
        "session_id": session.id,
        "text": "నాకు బ్యాంక్ అకౌంట్ తెరవాలి. దానికి ఏం పత్రాలు కావాలి?",
    }).json()
    assert "SBI" in first["reply"] and len(first["reply"]) < 200
    assert first["details"]["bank"] == "SBI"
    assert first["details"]["town"] == "విజయవాడ"

    session.preparation.pending = "existing"
    second = client.post("/api/transcribe", data={"session_id": session.id}, files={
        "audio": ("recording.wav", wav_bytes(), "audio/wav"),
    }).json()
    assert "Form 60" in second["reply"] and "Form 97" not in second["reply"]
    assert "Permanent Account Number" not in second["reply"]
    assert session.preparation.pending == "existing"
    assert second["preparation"]["pending"] == "existing"

    third = client.post("/api/conversation", json={"session_id": session.id, "text": followup_text}).json()
    assert "Form 97" in third["reply"]
    assert "SBI శాఖతో" in third["reply"]
    assert session.preparation.pending == "existing"
    assert [turn["session"]["bank"] for turn in seen] == ["SBI", "SBI", "SBI"]
    assert seen[1]["message"] == unclear_form_text


def test_gemini_failure_falls_back_without_losing_confirmed_facts(client, monkeypatch):
    session = prepare_known_sbi_session()
    original = httpx.AsyncClient
    monkeypatch.setattr(gemini.httpx, "AsyncClient", lambda **kwargs: original(
        transport=httpx.MockTransport(lambda _: httpx.Response(503)), **kwargs
    ))
    response = client.post("/api/conversation", json={
        "session_id": session.id,
        "text": "నాకు బ్యాంక్ అకౌంట్ తెరవాలి. దానికి ఏం పత్రాలు కావాలి?",
    }).json()
    assert "SBI" in response["reply"] and len(response["reply"]) < 200
    assert response["details"]["bank"] == "SBI"
    assert response["details"]["town"] == "విజయవాడ"


def test_gemini_input_redacts_identifiers_but_keeps_request_words():
    original = "Open bank account; PAN ABCDE1234F, Aadhaar 123456789012, OTP 123456; my address is 10 Main Road."
    filtered = gemini.redact_sensitive_identifiers(original)
    assert "Open bank account" in filtered
    for secret in ("ABCDE1234F", "123456789012", "OTP 123456", "10 Main Road"):
        assert secret not in filtered


def test_interpretation_drops_unstated_form_numbers_and_unconfirmed_corrections():
    raw = json.dumps(interpreted("document_question", document="declaration", numbers=["60", "97"], unclear=True))
    result = gemini.validate_interpretation(raw, "Form 60 గురించి చెప్పండి?")
    assert result.form_numbers == ["60"]
    assert result.unclear_form_reference is False

    correction = interpreted("correction", document="none")
    correction["corrections"] = [{"field": "bank", "value": "HDFC", "explicit": True}]
    result = gemini.validate_interpretation(json.dumps(correction), "HDFC bank documents?")
    assert result.corrections == []

    corrected = gemini.validate_interpretation(
        json.dumps(correction), "SBI కాదు, HDFC bank అని సరిచేయండి"
    )
    assert [(item.field, item.value) for item in corrected.corrections] == [("bank", "HDFC")]


def test_confirmed_details_change_only_on_explicit_correction():
    session = prepare_known_sbi_session()
    uncorrected = interpreted("other", intent="unknown")
    uncorrected["bank"] = "HDFC"
    session.advance("HDFC bank documents?", gemini.TurnInterpretation.model_validate(uncorrected))
    assert session.details["bank"] == "SBI"
    assert session.details["town"] == "విజయవాడ"

    correction = interpreted("correction", intent="open_account")
    correction["corrections"] = [{"field": "bank", "value": "HDFC", "explicit": True}]
    session.advance(
        "SBI కాదు, HDFC bank అని సరిచేయండి",
        gemini.TurnInterpretation.model_validate(correction),
    )
    assert session.details["bank"] == "HDFC"
    assert session.details["town"] == "విజయవాడ"


@pytest.mark.parametrize("raw", ["not json", json.dumps({"request_kind": "invented"})])
def test_invalid_gemini_output_is_rejected(raw):
    with pytest.raises(ValueError):
        gemini.validate_interpretation(raw, "hello")


def test_gemini_http_error_is_categorized_without_exposing_message():
    response = httpx.Response(400, json={"error": {
        "message": "Invalid JSON payload: responseSchema field was rejected with private data",
        "status": "INVALID_ARGUMENT",
    }})
    assert gemini.safe_error_category(response) == "structured_schema_rejected"
    assert gemini.safe_error_category(httpx.Response(503, text="private upstream body")) == "provider_unavailable"


@pytest.mark.parametrize(
    ("prompt", "kind"),
    [
        ("నేను SBI బ్యాంకులో ఖాతా తెరవాలనుకుంటున్నాను", "account_request"),
        ("నాకు SBIలో అకౌంట్ తెరవాలి. ఏం డాక్యుమెంట్స్ కావాలి?", "document_checklist"),
    ],
)
def test_fresh_sbi_open_request_gets_reviewed_checklist_through_api(client, monkeypatch, prompt, kind):
    seen = mock_providers(monkeypatch, [interpreted(kind)], prompt)
    response = client.post("/api/conversation", json={"text": prompt}).json()
    assert response["details"]["intent"] == "open_account"
    assert response["details"]["bank"] == "SBI"
    assert response["awaiting"] == ""
    assert response["preparation"]["pending"] == ""
    assert response["preparation"]["answers"].get("single") is None
    assert response["preparation"]["answers"].get("adult") is None
    assert response["preparation"]["answers"].get("resident") is None
    assert "ఒక్కొక్కటిగా" in response["reply"] and len(response["reply"]) < 200
    assert seen[0]["message"] == prompt


def test_location_added_after_sbi_opening_reuses_intent_and_checklist(client, monkeypatch):
    seen = mock_providers(monkeypatch, [interpreted("account_request"), interpreted("other")], "")
    first = client.post("/api/conversation", json={
        "text": "నాకు SBIలో అకౌంట్ తెరవాలి",
    }).json()
    second = client.post("/api/conversation", json={
        "session_id": first["session_id"],
        "text": "SBI Bank అనంతపూర్లో ఉన్నది",
    }).json()
    assert second["details"]["intent"] == "open_account"
    assert second["details"]["bank"] == "SBI"
    assert second["details"]["town"] == "అనంతపూర్"
    assert second["awaiting"] == ""
    assert second["preparation"]["pending"] == "single"
    assert second["preparation"]["answers"] == {}
    assert second["reply"] == gemini.ONBOARDING_QUESTIONS['single']
    assert [item["session"]["pending_onboarding_step"] for item in seen] == ["none", "none"]


def test_fresh_sbi_checklist_uses_local_fallback_when_gemini_unavailable(client, monkeypatch):
    original = httpx.AsyncClient
    monkeypatch.setattr(gemini.httpx, "AsyncClient", lambda **kwargs: original(
        transport=httpx.MockTransport(lambda _: httpx.Response(503)), **kwargs
    ))
    response = client.post("/api/conversation", json={
        "text": "నేను SBI బ్యాంకులో ఖాతా తెరవాలనుకుంటున్నాను",
    }).json()
    assert response["details"]["intent"] == "open_account"
    assert response["details"]["bank"] == "SBI"
    assert "SBI" in response["reply"] and len(response["reply"]) < 200
    assert response["preparation"]["answers"] == {}


def pending_single_session():
    session = Conversation()
    session.details.update(intent="open_account", bank="SBI", town="Anantapur")
    session.preparation.pending = "single"
    store.sessions[session.id] = session
    return session


def onboarding_result(*, self_account=False, age=0, subject="unknown"):
    result = interpreted("onboarding_answer")
    result.update(
        account_for_self=self_account,
        account_for_self_explicit=self_account,
        age_years=age,
        age_explicit=bool(age),
        age_subject=subject,
        adult=age >= 18,
        adult_explicit=bool(age),
    )
    return result


def test_onboarding_answer_saves_self_and_age_then_asks_only_residency(client, monkeypatch):
    session = pending_single_session()
    prompt = "\u0c28\u0c3e\u0c15\u0c41 \u0c07\u0c30\u0c35\u0c48 \u0c12\u0c15\u0c4d\u0c15 \u0c0f\u0c33\u0c4d\u0c32\u0c41, \u0c28\u0c3e \u0c12\u0c15\u0c4d\u0c15\u0c26\u0c3e\u0c28\u0c3f \u0c15\u0c4b\u0c38\u0c2e\u0c47."
    seen = mock_providers(monkeypatch, [onboarding_result(self_account=True, age=21, subject="speaker")], prompt)
    payload = client.post("/api/conversation", json={"session_id": session.id, "text": prompt}).json()
    assert seen[0]["session"]["pending_onboarding_step"] == "single"
    assert seen[0]["session"]["pending_onboarding_question"] == gemini.ONBOARDING_QUESTIONS["single"]
    assert payload["preparation"]["account_for_self"] is True
    assert payload["preparation"]["answers"]["single"] == "yes"
    assert payload["preparation"]["answers"]["age_years"] == 21
    assert payload["preparation"]["answers"]["adult"] == "yes"
    assert payload["preparation"]["answers"].get("resident") is None
    assert payload["preparation"]["pending"] == "resident"
    assert payload["reply"] == gemini.ONBOARDING_QUESTIONS["resident"]


def test_short_self_answer_saves_only_account_scope_then_asks_age(client, monkeypatch):
    session = pending_single_session()
    prompt = "\u0c28\u0c3e \u0c12\u0c15\u0c4d\u0c15\u0c26\u0c3e\u0c28\u0c3f \u0c15\u0c4b\u0c38\u0c2e\u0c47"
    mock_providers(monkeypatch, [onboarding_result(self_account=True)], prompt)
    payload = client.post("/api/conversation", json={"session_id": session.id, "text": prompt}).json()
    assert payload["preparation"]["account_for_self"] is True
    assert payload["preparation"]["answers"]["single"] == "yes"
    assert "adult" not in payload["preparation"]["answers"]
    assert payload["preparation"]["pending"] == "adult"
    assert payload["reply"] == gemini.ONBOARDING_QUESTIONS["adult"]


def test_short_self_answer_still_progresses_when_gemini_is_unavailable(client, monkeypatch):
    session = pending_single_session()
    original = httpx.AsyncClient
    monkeypatch.setattr(gemini.httpx, "AsyncClient", lambda **kwargs: original(
        transport=httpx.MockTransport(lambda _: httpx.Response(503)), **kwargs
    ))
    prompt = "\u0c28\u0c3e \u0c12\u0c15\u0c4d\u0c15\u0c26\u0c3e\u0c28\u0c3f \u0c15\u0c4b\u0c38\u0c2e\u0c47"
    payload = client.post("/api/conversation", json={"session_id": session.id, "text": prompt}).json()
    assert payload["preparation"]["account_for_self"] is True
    assert payload["preparation"]["pending"] == "adult"
    assert payload["reply"] == gemini.ONBOARDING_QUESTIONS["adult"]


def test_other_account_holder_prompts_who_age_applies_to(client, monkeypatch):
    session = pending_single_session()
    prompt = "\u0c16\u0c3e\u0c24\u0c3e \u0c35\u0c47\u0c30\u0c4a\u0c15\u0c30\u0c3f \u0c15\u0c4b\u0c38\u0c02, \u0c07\u0c30\u0c35\u0c48 \u0c12\u0c15\u0c4d\u0c15 \u0c0f\u0c33\u0c4d\u0c33\u0c41."
    result = onboarding_result(self_account=False, age=21, subject="unclear")
    result["account_for_self_explicit"] = True
    mock_providers(monkeypatch, [result], prompt)
    payload = client.post("/api/conversation", json={"session_id": session.id, "text": prompt}).json()
    assert payload["preparation"]["account_for_self"] is False
    assert payload["preparation"]["pending"] == "age_subject"
    assert payload["preparation"]["answers"]["age_years"] == 21
    assert "adult" not in payload["preparation"]["answers"]
    assert "resident" not in payload["preparation"]["answers"]
    assert "\u0c35\u0c2f\u0c38\u0c41" in payload["reply"]
