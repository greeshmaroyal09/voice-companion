# Preparation UX changes and verification

The existing Preparation class now handles the invitation, onboarding, and one-item voice walkthrough. No classes were added. The reviewed ENTRIES, SOURCES, and checklist() payloads are unchanged; only the PAN/declaration conversational wording in DOCUMENTS changed.

## Previous onboarding trigger

- Original conversation.py:359–379 detected a fresh SBI opening with no extracted preparation answers, cleared pending, and returned the quick checklist. Location updates and later checklist requests reused this early return.
- Original conversation.py:195–199 routed PAN/document interruptions and returned before onboarding. A PAN follow-up therefore did not start onboarding.
- Original preparation.py:129–140 required SBI/open_account, supported scope, and a known town/branch or skipped location before reaching onboarding.
- Original preparation.py:146–155 asked single, adult, resident, then existing when unanswered. Original conversation.py:118–129 could also ask onboarding via a checklist request if the quick-checklist route had not intercepted it.
- Reachability: the reported plain first message did not trigger onboarding. A more specific natural first message did: “నా కోసం గుంటూరులో SBI ఖాతా తెరవాలి” extracted single=yes and town=గుంటూరు, bypassed the no-answers quick route, and asked “మీకు 18 ఏళ్లు నిండాయా?”. This was reproduced against the original snapshots.

## Current trigger

- conversation.py:354–359 routes SBI/open_account to Preparation.respond without requiring a location.
- preparation.py:190–193 returns the short invitation on the first turn.
- preparation.py:199–205 asks unanswered ONBOARDING_QUESTIONS on following turns. Explicitly supplied answers are retained and skipped. Next/skip rotates unanswered questions without assuming eligibility; all must be answered before item delivery.
- preparation.py:207–235 covers one checklist item at a time. Explanation focus preserves no-PAN/old-address answers when the user agrees to continue.
- dialogue.py:54–65 restores the saved focus/question after interruptions. Repeat replays the exact last reply. conversation.py:155–160 returns the complete reply for the full-list command while preserving position.

## Verification

- `.venv/Scripts/python.exe -m pytest backend -q`: 94 passed; one existing Starlette/AnyIO deprecation warning.
- `verify_preparation.py`: PASS, 22 synthetic turns through isolated Vite 5174 → edited backend 8001, with Gemini disabled. Covers onboarding, progression, no PAN, repeat/full list, same-item resume, SBI retention, location correction, unknown branch, restore/reset, and unsupported-bank invalidation.
- Knowledge comparison against original snapshots: ENTRIES and SOURCES equal; complete checklist payloads equal for default, existing-KYC, no-PAN, no-OVD, old-address, and current-address profiles.
- Speech tests use mocked providers. This smoke run did not make live STT/TTS calls.
- The original development servers were left running; restart the development backend to load these changes.

Full conversation: [preparation-smoke-transcript.md](preparation-smoke-transcript.md). Exact patch: [preparation-changes.diff](preparation-changes.diff).

## Changed lines in current files

| File | Changed line spans |
| --- | --- |
| backend/conversation.py | 56, 70–71, 75–76, 82–83, 118 (deletion point), 155–160, 190–191, 288, 354–355, 357–359 |
| backend/preparation.py | 4, 124–174, 176–177, 190–193, 196, 198–205, 207–235 |
| backend/dialogue.py | 50, 58, 63–64, 116–117, 125–128 |
| backend/knowledge.py | 60, 62 |
| backend/test_conversation.py | 21, 79, 94–97, 103, 196, 200, 205–206 |
| backend/test_preparation.py | 2, 6–7, 47–48, 53–54, 135–235 |
| backend/test_gemini.py | 91, 99, 106, 122, 202, 219, 221, 235 |
| backend/test_main.py | 104, 158 |
| verify_preparation.py | 1, 3, 9, 12–15, 21–55, 58, 65–67, 70–71, 75–80 |
