# Banking preparation phase

Implemented locally; no publishing, translation, or helper matching.

## Architecture and limits

`backend/conversation.py` extracts bank, intent, town and branch with explicit regular expressions. `backend/preparation.py` is a bounded state machine for categorical answers and current explanation focus. Neither is an LLM or general language understanding. Unrecognized phrases can need rephrasing; Telugu/English variants are deliberately limited. No generative banking requirements are produced.

`backend/knowledge.py` is the reviewed knowledge catalog, separate from dialogue and audio. Each entry carries category, conditions, exceptions, verification status, branch-confirmation flag and source references; referenced sources carry official URL/title, checked date, published/updated date and effective date if known. Unknown dates remain null. Telugu text is our explanatory paraphrase, not an official translation. New banks or languages should add reviewed catalogs and locale handlers rather than reuse SBI facts indiscriminately.

Scope: branch-visit preparation for a resident adult's single-holder ordinary SBI savings account. Minor, NRI, joint, business, salary/pension and explicitly requested basic savings situations receive a coverage-limit response. Small Account is an alternate route to discuss with the branch, not a complete eligibility flow. Location does not determine KYC requirements. Branch name is optional. Existing SBI KYC is checked before displaying the checklist. Address evidence appears conditionally; no document number, exact income, full address or upload is requested.

Sessions retain the last 50 turns, categorical answers and checklist state in backend memory for one hour of inactivity. Refresh restores through sessionStorage. Restart/new conversation clears it. TTS failure does not mutate the conversation. Reply audio remains tied to the exact turn; browser replay reuses its object URL. Source and checklist explanations are separate short turns, never a whole checklist readout.

## Official sources reviewed 2026-11-08

Full pages were opened, not just search snippets:

- [RBI KYC Master Direction](https://www.rbi.org.in/Scripts/BS_ViewMasDirections.aspx?id=11566), page updated 2025-08-14: sections 3, 10, 16 and 23. Distinguishes regulatory identification options and tax evidence from bank product terms.
- [RBI KYC FAQ](https://rbi.org.in/Scripts/FAQDisplay.aspx?Id=173), dated 2025-06-09: questions 4–10, covering existing KYC, address conditions, document alternatives and Small Accounts.
- [SBI individual KYC documents](https://sbi.bank.in/web/personal-banking/information-services/kyc-guidelines/kyc-documents-individuals), updated 2026-06-09: identity/address options and a separate Small Account route.
- [SBI ordinary savings account](https://sbi.bank.in/web/personal-banking/accounts/saving-account/savings-bank-account), updated 2026-03-13: product scope and NIL monthly average balance. This is not a statement that every service is free.
- [SBI's link labelled Form 60](https://sbi.bank.in/documents/16012/0/11052026_form_no_97.pdf/098d5eb8-95dd-e86b-89dd-05754752ba37?t=1778501367720) currently serves **Form No. 97**. Its effective date is not stated in the reviewed PDF. RBI's available text names Form 60. The current no-PAN form and applicability therefore remain explicitly **branch-confirmation required**; the app does not claim universal Form 60 acceptance.

The older account-opening PDF at `https://retail.sbi.bank.in/sbi/downloads/common_deposit_account_opening_form_effective_from_01.11.2023.pdf` redirected to a registration page, so its contents were not used. Fixed photo/copy counts and visit-specific forms/fees remain unverified. The app gives no photocopy-shop count and does not infer requirements from rural/urban location. Sources are a dated manual review, not an automatically updated legal database. Re-review before extending coverage or treating a changed rule as current.

## Local test journey

1. Start FastAPI: `.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000`.
2. In a second PowerShell window, run `npm.cmd run dev`.
3. Open http://127.0.0.1:5173/ and select **New conversation**. Existing server processes should be stopped before starting duplicates.
4. Type or speak `నాకు SBIలో account తెరవాలి.` Expect the town/branch question, not a bank question.
5. Say `అనంతపురం`. Confirm single-holder ordinary savings, age 18+, and Indian residence with `అవును` to each question. Answer the existing-SBI-KYC question with `లేదు` for this synthetic example.
6. Review the checklist. Expand **Official sources** and **Illustrative sample**. The sample has no real identity details and is labelled **SAMPLE — NOT A VALID DOCUMENT**.
7. Say `కాదు, బెంగళూరు`. SBI and account-opening intent remain; the town changes. Say `బ్రాంచ్ తెలియదు`; the checklist remains available.
8. Say `PAN అంటే ఏంటి?`, then `నాకు అది లేదు`. Expect the no-PAN declaration discrepancy and branch-confirmation guidance. `మళ్ళీ చెప్పు` repeats the previous explanation; `తర్వాత` advances to another short item. Use the speaker button to hear/replay the reply.
9. Try `ఆధార్ లేదు`, `ఏ పత్రమూ లేదు`, `చిరునామా పాతది`, and `జిరాక్స్ కాపీలు ఎన్ని?`. Expect alternatives, a limited Small Account referral, conditional address guidance and no invented copy count.
10. Say `SBI కాదు HDFC bank` or `పిల్ల కోసం minor account`. SBI checklist disappears and coverage limits are explained. Earlier messages remain visible.
11. If audio fails, confirm the checklist and history remain visible; use **Retry reply audio**. Refresh to verify session restoration. A backend restart requires a new conversation.

Never enter actual identity numbers or credentials during testing. `verify_live.py` sends only the previously approved generic Telugu greeting; it does not read conversation history.

## Validation

Run `.\.venv\Scripts\python.exe -m pytest backend -q`, `npm.cmd test`, and `npm.cmd run build`.

The local Vite-proxy smoke test `.\.venv\Scripts\python.exe verify_preparation.py` passed an 11-turn synthetic journey including corrections, missing PAN, checklist restoration and unsupported-bank invalidation. It makes no speech-provider calls.

Regression tests cover bank retention/corrections, location corrections without repeating the old town, unknown branch, missing PAN and identity alternatives, unsupported situations, unverified counts, conditional address evidence, source metadata, synthetic sample labelling, TTS failure/restore/retry, and the existing STT/TTS contracts and WAV normalization.

Actual browser verification was attempted but blocked: the computer-use tool could not determine Chrome's current URL reliably and stopped. No browser journey, microphone recognition, or audible playback pass is claimed for this phase. The frontend test renders checklist markup; it is not an interactive browser test.

Live TTS using only the approved generic greeting succeeded: HTTP 200, 24 kHz mono PCM WAV, 65,280 frames / 2.72 seconds, non-silent samples. The streaming header was repaired; TLS verification stayed enabled. Measurements are saved in `artifacts/live-tts/verification.json`. This confirms synthesis and file validation, not audible browser playback.
