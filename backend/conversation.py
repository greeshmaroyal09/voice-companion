"""Conservative Telugu/English slot dialogue; no banking requirements database.

Only explicitly supplied facts are retained. Unsupported requests get a
clarification, never a guessed procedure or eligibility requirement.
"""
import re
import time
from dataclasses import dataclass, field
from uuid import uuid4

from fastapi import HTTPException
from backend.preparation import Preparation, ONBOARDING_QUESTIONS, LIMIT
from backend.dialogue import discuss, handle_interruption
from backend.knowledge import DOCUMENTS, ENTRIES

BANKS = {
    "SBI": r"s\s*\.?b\s*\.?i\.?|state bank(?: of india)?|స్టేట్ బ్యాంక్(?: ఆఫ్ ఇండియా)?|ఎస్\s*బి\s*ఐ|ఎస్బీఐ",
    "HDFC": r"h\s*d\s*f\s*c|హెచ్\s*డి\s*ఎఫ్\s*సి|హెచ్‌డిఎఫ్‌సి",
    "ICICI": r"i\s*c\s*i\s*c\s*i|ఐ\s*సి\s*ఐ\s*సి\s*ఐ",
    "Axis": r"axis|యాక్సిస్|ఆక్సిస్",
    "Canara": r"canara|కెనరా",
    "Union Bank": r"union(?: bank)?|యూనియన్(?: బ్యాంక్)?",
    "Bank of Baroda": r"bank of baroda|బ్యాంక్ ఆఫ్ బరోడా",
    "Indian Bank": r"indian bank|ఇండియన్ బ్యాంక్",
    "PNB": r"pnb|punjab national bank|పంజాబ్ నేషనల్ బ్యాంక్",
}
INTENTS = {
    "open_account": (r"(?:ఖాతా|అకౌంట్|account).*?(?:తెరవ|ఓపెన్|open|ప్రారంభించ|కావాలి)|(?:open|opening|new|create).*?(?:account)|(?:కొత్త|new)\s*(?:ఖాతా|అకౌంట్|account)", "ఖాతా తెరవడం"),
    "close_account": (r"(?:ఖాతా|అకౌంట్|account).*?(?:మూస|క్లోజ్|close)|close.*?account", "ఖాతా మూసివేయడం"),
    "withdraw": (r"డబ్బు.*?(?:తీయ|తీసు)|withdraw|విత్‌డ్రా", "డబ్బు తీసుకోవడం"),
    "deposit": (r"డిపాజిట్|deposit|డబ్బు.*?జమ", "డబ్బు జమ చేయడం"),
    "transfer": (r"ట్రాన్స్‌ఫర్|transfer|డబ్బు.*?పంప", "డబ్బు బదిలీ చేయడం"),
    "balance": (r"బ్యాలెన్స్|balance", "బ్యాలెన్స్ తెలుసుకోవడం"),
}
QUESTIONS = {
    "intent": "బ్యాంకులో మీకు ఏ పని కోసం సహాయం కావాలి?",
    "bank": "మీరు ఏ బ్యాంకుకు వెళ్లాలనుకుంటున్నారు?",
    "location": "మీరు ఏ పట్టణం లేదా బ్రాంచ్‌కు వెళ్లాలనుకుంటున్నారు?",
}
UNKNOWN = r"తెలియదు|ఇంకా నిర్ణయించలేదు|not sure|don.t know|వద్దు|చెప్పలేను"
NEGATION = r"^\s*(?:bank|బ్యాంకు|బ్యాంక్|లో|కి|కు|ను|ని|ని కాదు|అకౌంట్|account|ఖాతా|తెరవడం|తెరవాలి|మూసివేయడం|బ్రాంచ్|branch|శాఖ|పట్టణం|town|నగరం|city|\s)*\s*(?:కాదు|కాకుండా|వద్దు|కావద్దు|not\b)"


CHECKLIST_REQUEST = r"documents?|docs?|checklist|requirements|\u0c21\u0c3e\u0c15\u0c4d\u0c2f\u0c41\u0c2e\u0c46\u0c02\u0c1f\u0c4d\u0c38\u0c4d?|\u0c21\u0c3e\u0c15\u0c4d\u0c2f\u0c41\u0c2e\u0c46\u0c02\u0c1f\u0c4d\u200c\u0c38\u0c4d?|\u0c2a\u0c24\u0c4d\u0c30\u0c3e\u0c32\u0c41|\u0c2a\u0c24\u0c4d\u0c30\u0c3e\u0c32|\u0c0f\u0c02\s*\u0c2a\u0c24\u0c4d\u0c30\u0c3e\u0c32\u0c41|\u0c0f\s*\u0c2a\u0c24\u0c4d\u0c30\u0c3e\u0c32\u0c41|\u0c0f\u0c2e\u0c47\u0c2e\u0c3f\s*\u0c2a\u0c24\u0c4d\u0c30\u0c3e\u0c32\u0c41|\u0c26\u0c3e\u0c28\u0c3f\u0c15\u0c3f\s*\u0c0f\u0c02.*\u0c15\u0c3e\u0c35\u0c3e\u0c32\u0c3f|\u0c2a\u0c24\u0c4d\u0c30\u0c3e\u0c32\s*\u0c1c\u0c3e\u0c2c\u0c3f\u0c24\u0c3e|\u0c2a\u0c24\u0c4d\u0c30\u0c3e\u0c32\u0c41\s*\u0c15\u0c3e\u0c35\u0c3e\u0c32\u0c3f|\u0c0f\u0c2e\u0c3f\s*\u0c15\u0c3e\u0c35\u0c3e\u0c32\u0c3f"
FORM_MENTION = r"\bform\b|ఫా\s*రం|ఫారమ్"
FORM_QUESTION = r"\?|ఏంటి|ఏమిటి|అంటే|వివరించ|చెప్పు|explain|what|which|tell me|meaning"
UNCLEAR_FORM = r"ఇంకో|మరో|రెండో|second|another|other|అర్థం కాలేదు|స్పష్టంగా లేదు|గుర్తులేదు|unclear|couldn.t hear"
EXPLICIT_CORRECTION = r"కాదు|కాకుండా|బదులు|instead|actually|i meant|change|మార్చు|తప్పు|సరిచేయ"


def checklist_request(text, interpretation):
    return bool((interpretation and interpretation.request_kind == 'document_checklist')
                or re.search(CHECKLIST_REQUEST, text, re.I))


def form_discussion_reply(text, interpretation, prep, bank=None):
    has_form = re.search(FORM_MENTION, text, re.I) is not None
    is_question = re.search(FORM_QUESTION, text, re.I) is not None
    interpreted_form = bool(interpretation and interpretation.document == 'declaration')
    continuing_form = prep.interrupted and prep.last_document == 'declaration'
    if not has_form or not (is_question or interpreted_form or continuing_form):
        return None

    numbers = set(re.findall(r"(?:form\s*(?:no\.?\s*)?|ఫా\s*రం\s*)(\d{1,3})", text, re.I))
    if interpretation:
        numbers.update(interpretation.form_numbers)
    unclear = bool(interpretation and interpretation.unclear_form_reference) or bool(re.search(UNCLEAR_FORM, text, re.I))
    if '60' in numbers and unclear:
        reply = (
            "PAN లేకపోతే సాధారణంగా Form 60 ప్రకటన ఇస్తారు. "
            "ప్రస్తుత ఫారాన్ని SBI శాఖతో నిర్ధారించండి. మీరు అడిగిన మరో ఫారం నంబర్ ఏది?"
        )
    elif '97' in numbers:
        reply = (
            "మీరు Form 97 అన్నారు. PAN లేకపోతే సాధారణంగా Form 60 ప్రకటన ఇస్తారు. "
            "మీకు ప్రస్తుతం వర్తించే ఫారాన్ని SBI శాఖతో నిర్ధారించండి."
        )
    elif '60' in numbers:
        reply = DOCUMENTS['declaration']['explanation']
    else:
        reply = "RBI మార్గదర్శకంలో PAN ఇవ్వని సందర్భానికి Form 60 ప్రస్తావన ఉంది. మీరు అడిగిన ఫారం నంబర్‌ను స్పష్టంగా చెబుతారా?"
    if bank:
        reply = reply.replace('మీ బ్యాంకుతో', f'{bank} శాఖతో')
    discuss(prep, 'declaration', reply)
    return reply


def clean_location(value: str) -> str:
    value = re.sub(r"^(?:లేదు|కాదు|అది|అసలు|మార్చండి|బదులుగా|actually|instead|no)[,\s:]*", "", value.strip(), flags=re.I)
    value = re.sub(r"^(?:నేను|నాకు|మా|నా|in|at)\s+", "", value, flags=re.I)
    value = re.sub(r"(?:లో|కు|కి)?\s*(?:వెళ్లాలి|వెళ్ళాలి|కావాలి|అనుకుంటున్నాను|ఉన్న|ఉంది|అని మార్చండి|మార్చండి|please)[.!\s]*$", "", value, flags=re.I)
    return re.sub(r"(?:లో|కు|కి)$", "", value.strip(" .,!?:;—\u200c\u200b"))[:100]


@dataclass
class Conversation:
    id: str = field(default_factory=lambda: str(uuid4()))
    details: dict = field(default_factory=lambda: {"intent": None, "bank": None, "town": None, "branch": None})
    awaiting: str = "intent"
    turns: list = field(default_factory=list)
    touched: float = field(default_factory=time.monotonic)
    preparation: Preparation = field(default_factory=Preparation)
    quick_checklist_shown: bool = False

    def _checklist_reply(self) -> str:
        if not self.details['bank']:
            self.awaiting = 'bank'
            return QUESTIONS['bank']
        if self.details['bank'] != 'SBI' or self.details['intent'] != 'open_account':
            return LIMIT if self.details['bank'] == 'SBI' else (
                'నా దగ్గర ధృవీకరించిన పత్రాల సమాచారం SBI సాధారణ savings account కోసమే ఉంది. '
                'మీ బ్యాంకు పేరు చెబుతారా?'
            )
        if self.preparation.answers.get('scope') == 'unsupported' or any(
            self.preparation.answers.get(key) == 'no' for key in ('single', 'adult', 'resident')
        ):
            return LIMIT
        self.preparation.reply_source_ids = list(dict.fromkeys(
            ENTRIES['identity']['source_ids'] + ENTRIES['address']['source_ids']
            + ENTRIES['tax']['source_ids'] + ENTRIES['visit']['source_ids']
            + ENTRIES['existing']['source_ids']
        ))
        if self.preparation.answers.get('existing') == 'yes':
            return (
                'చిన్న SBI జాబితా:\n• KYC వివరాలు మారకపోతే, SBIలో ఇప్పటికే పూర్తైన KYC మళ్లీ అవసరం కాకపోవచ్చు; '
                'మార్పులుంటే సరైన ఆధారాన్ని బ్రాంచ్‌తో నిర్ధారించండి.\n'
                '• PAN సిద్ధంగా ఉంచండి; లేకపోతే వర్తించే ప్రకటన ఏదో బ్రాంచ్‌ను అడగండి.\n'
                '• దరఖాస్తు, ఫోటో/కాపీల సంఖ్యను SBI బ్రాంచ్‌తో నిర్ధారించండి.'
            )
        return (
            'చిన్న SBI జాబితా:\n• పేరు, చిరునామా ఉన్న అనుమతించిన గుర్తింపు పత్రం.\n'
            '• ఆ పత్రంలో ప్రస్తుత చిరునామా లేకుంటే, అనుమతించిన చిరునామా ఆధారాన్ని కూడా అడగండి.\n'
            '• PAN సిద్ధం చేసుకోండి; లేకపోతే వర్తించే ప్రకటన ఏదో బ్రాంచ్‌తో నిర్ధారించండి.\n'
            '• దరఖాస్తు, ఫోటో/కాపీల ఖచ్చితమైన సంఖ్యను ఊహించకుండా బ్రాంచ్‌ను అడగండి.'
        )

    def _quick_sbi_checklist_reply(self) -> str:
        """Short reviewed checklist without asserting eligibility answers."""
        location = self.details.get('town') or self.details.get('branch')
        heading = f"SBI {location} కోసం" if location else "SBI కోసం"
        self.preparation.reply_source_ids = list(dict.fromkeys(
            ENTRIES['identity']['source_ids'] + ENTRIES['tax']['source_ids']
            + ENTRIES['address']['source_ids'] + ENTRIES['visit']['source_ids']
        ))
        return (
            f"{heading} — సాధారణ సేవింగ్స్ ఖాతా కోసం 18 ఏళ్లు పైబడిన భారత నివాసి, వ్యక్తిగత ఖాతా అని ఊహిస్తున్నాను:\n"
            "• పేరు, చిరునామా ఉన్న చెల్లుబాటు అయ్యే గుర్తింపు/చిరునామా పత్రం తీసుకెళ్లండి; ఉదాహరణకు పాస్‌పోర్ట్, డ్రైవింగ్ లైసెన్స్, ఓటరు కార్డు, ఆధార్ ఆధార పత్రం, NREGA జాబ్ కార్డు లేదా NPR లేఖ. ఆధార్ ఒక్కటే మార్గం కాదు.\n"
            "• PAN తీసుకెళ్లండి; PAN లేకపోతే మీకు వర్తించే ప్రకటన ఏదో SBI శాఖతో నిర్ధారించండి.\n"
            "• గుర్తింపు పత్రంలో ప్రస్తుత చిరునామా లేకపోతే, అదనపు చిరునామా ఆధారం అవసరమవచ్చు.\n"
            "దరఖాస్తు, ఫోటో/కాపీల వివరాలు మరియు వర్తించే ఫారమ్‌ను శాఖతో నిర్ధారించండి; వాటి సంఖ్యలను ఇక్కడ ఊహించడం లేదు."
        )

    def advance(self, text: str, interpretation=None) -> dict:
        text = text.strip()
        full_list = bool(re.fullmatch(r'\s*(మొత్తం జాబితా చెప్పు|full list|మొత్తం జాబితా)[.!\s]*', text, re.I))
        if self.preparation.focus == 'done' and not self.preparation.interrupted and re.fullmatch(r'\s*(అవును|yes|సరే|okay|ok)[.!\s]*', text, re.I):
            full_list = True
        if full_list and self.details['bank'] == 'SBI' and self.details['intent'] == 'open_account':
            return self.save_turn(text, self._checklist_reply() if self.preparation.supported(self.details) and 'existing' in self.preparation.answers else self._quick_sbi_checklist_reply())
        form_reply = form_discussion_reply(text, interpretation, self.preparation, self.details['bank'])
        if form_reply is not None:
            return self.save_turn(text, form_reply)
        wants_checklist = checklist_request(text, interpretation)
        pending_question = QUESTIONS.get(self.awaiting) or ONBOARDING_QUESTIONS.get(self.preparation.pending, '')
        previous_answers = self.preparation.answers.copy()
        previous_self = self.preparation.account_for_self
        onboarding_pending = self.preparation.pending in ('single', 'adult')
        preprocessed_onboarding = onboarding_pending and (
            self.preparation.has_onboarding_cue(text) or bool(interpretation and (
                interpretation.account_for_self_explicit or interpretation.age_explicit
            ))
        )
        if preprocessed_onboarding:
            self.preparation.ingest(text)
        if preprocessed_onboarding and interpretation:
            if interpretation.account_for_self_explicit:
                self.preparation.account_for_self = interpretation.account_for_self
                if interpretation.account_for_self:
                    self.preparation.answers['single'] = 'yes'
                    self.preparation.answers.pop('scope', None)
                else:
                    self.preparation.age_subject = interpretation.age_subject if interpretation.age_subject != 'unknown' else 'unclear'
            if interpretation.age_explicit and interpretation.age_years:
                self.preparation.answers['age_years'] = interpretation.age_years
                if interpretation.age_subject != 'unknown':
                    self.preparation.age_subject = interpretation.age_subject
                if interpretation.adult_explicit and interpretation.age_subject in ('speaker', 'account_holder'):
                    self.preparation.answers['adult'] = 'yes' if interpretation.adult else 'no'
        onboarding_answer = previous_answers != self.preparation.answers or previous_self != self.preparation.account_for_self
        interruption = None if wants_checklist or self.preparation.walkthrough_answer(text) else handle_interruption(
            text, self.preparation, self.turns[-1]['reply'] if self.turns else '', pending_question, self.details['bank']
        )
        if interruption is not None and not onboarding_answer:
            return self.save_turn(text, interruption)
        if not preprocessed_onboarding:
            self.preparation.ingest(text)
        previous = self.details.copy()
        recognized = False
        # A negated old value never wins over its replacement.
        bank_hits = []
        for bank, pattern in BANKS.items():
            for hit in re.finditer(r"(?<![a-z])(?:" + pattern + r")(?![a-z])", text, re.I):
                if not re.match(NEGATION, text[hit.end():], re.I):
                    bank_hits.append((hit.start(), bank))
                elif self.details["bank"] == bank:
                    self.details["bank"] = None
                    recognized = True
        if bank_hits:
            bank_candidate = max(bank_hits)[1]
            if previous['bank'] is None or previous['bank'] == bank_candidate or re.search(EXPLICIT_CORRECTION, text, re.I):
                self.details["bank"] = bank_candidate
                recognized = True
        elif re.search(r'\b([A-Za-z]+)\s+bank(?:లో|కు|కి)?', text, re.I):
            candidate = re.search(r'\b([A-Za-z]+)\s+bank(?:లో|కు|కి)?', text, re.I)[1]
            if candidate.lower() not in ('a', 'the', 'my', 'new', 'which', 'open') and (
                previous['bank'] is None or previous['bank'].casefold() == candidate.casefold()
                or re.search(EXPLICIT_CORRECTION, text, re.I)
            ):
                self.details['bank'] = candidate
                recognized = True
        elif self.awaiting == 'bank' and re.fullmatch(r'[A-Za-z ]{2,40}(?:బ్యాంక్|బ్యాంకు)?', text) and not re.search(UNKNOWN, text, re.I):
            self.details['bank'] = text.strip()
            recognized = True
        intent_hits = []
        for intent, (pattern, _) in INTENTS.items():
            for hit in re.finditer(pattern, text, re.I):
                if not re.match(r"\s*(?:డం|ాలి|ాలి)?\s*(?:కాదు|వద్దు|కావద్దు)", text[hit.end():]):
                    intent_hits.append((hit.start(), intent))
                elif self.details["intent"] == intent:
                    self.details["intent"] = None
                    recognized = True
        if intent_hits:
            intent_candidate = max(intent_hits)[1]
            if previous['intent'] is None or previous['intent'] == intent_candidate or re.search(EXPLICIT_CORRECTION, text, re.I):
                self.details["intent"] = intent_candidate
                recognized = True

        # An explicit town/branch value is extracted from its own clause. Never
        # interpret a bank-only correction as an answer to the location question.
        # Remove explicitly rejected values before extracting replacements. A
        # label such as 'branch' must not turn a negated value back into a fact.
        location_text = text
        for slot in ("town", "branch"):
            old = previous[slot]
            if old:
                rejected = re.compile(re.escape(old) + r"(?:లో|కు|కి)?\s*(?:(?:బ్రాంచ్|శాఖ|branch|పట్టణం|town)\s*)?(?:కాదు|కాకుండా|వద్దు)", re.I)
                if rejected.search(location_text):
                    self.details[slot] = None
                    recognized = True
                    location_text = rejected.sub("", location_text)
        location_text = re.sub(r"[^,;.!?]*(?:కాదు|కాకుండా)\s*", "", location_text)
        clauses = re.split(r"[,;.!?]|\s+బదులుగా\s*", location_text)
        location_changed = False
        if re.match(r'^\s*(?:కాదు|లేదు|actually|instead)[,\s]+', text, re.I) and not bank_hits and not intent_hits and previous['town']:
            candidate = clean_location(text)
            if candidate and len(candidate.split()) <= 3 and not re.search(r'లేదు|పాన్|PAN|పత్రం|ఆధార్|account|ఖాతా|సేవింగ్స్', candidate, re.I):
                self.details['town'] = candidate
                recognized = location_changed = True
        for clause in clauses:
            if not clause.strip() or location_changed:
                continue
            # Extract a location supplied alongside the bank and intent, e.g.
            # 'గుంటూరులో SBI bankలో ఖాతా తెరవాలి'. Do not guess place names.
            contains_fact = any(re.search(pattern, clause, re.I) for pattern in BANKS.values()) or any(re.search(pattern, clause, re.I) for pattern, _ in INTENTS.values())
            if contains_fact:
                location_clause = clause
                for pattern in BANKS.values():
                    location_clause = re.sub(r"(?<![a-z])(?:" + pattern + r")(?![a-z])(?:\s*(?:bank|బ్యాంకు|బ్యాంక్))?(?:లో|కు|కి)?", " ", location_clause, flags=re.I)
                embedded = re.search(r"([^\s,]+?)లో\s", location_clause)
                if embedded and embedded[1] not in ("bank", "బ్యాంకు", "బ్యాంక్", "ఖాతా", "account", "భారతదేశం", "ఇండియా"):
                    self.details["town"] = embedded[1]
                    recognized = location_changed = True
                continue
            if re.search(UNKNOWN, clause, re.I):
                continue
            # Named labels allow towns and branches not present in a hardcoded list.
            for slot, label in (("branch", r"బ్రాంచ్|శాఖ|branch"), ("town", r"పట్టణం|నగరం|town|city")):
                match = re.search(rf"^\s*(.+?)\s*(?:{label})(?:లో|కు|కి)?(?:\s|$)", clause, re.I)
                if not match:
                    match = re.search(rf"(?:{label})\s*[:\-]?\s+(.+)$", clause, re.I)
                if match:
                    value = clean_location(match[1])
                    if value and value not in ("నా", "మా", "the", "my"):
                        self.details[slot] = value
                        recognized = location_changed = True
            if (self.awaiting == "location" or self.quick_checklist_shown or any(previous[s] and self.details[s] is None for s in ("town", "branch"))) and not location_changed:
                value = clean_location(clause)
                if value and len(value.split()) <= 4 and not re.search(r"[?]|ధన్యవాద|సరే|అవును|thanks|okay|yes|ఎందుకు|ఏమిటి|ఏంటి|ఎలా|పత్రాలు|documents|లేదు|PAN|ఆధార్|మళ్ళీ|మళ్లీ|repeat|adult|resident|సేవింగ్స్|తర్వాత|తరువాత|next|skip|కొనసాగించు|continue|ఉంది|ఉన్నాయి|no|నిండాయి", clause, re.I):
                    slot = "branch" if previous["branch"] and self.details["branch"] is None else "town"
                    self.details[slot] = value
                    recognized = location_changed = True

        # Corrections can replace the previous location even after a summary.
        if not location_changed and re.search(r"కాదు|instead|actually", text, re.I) and not bank_hits and not intent_hits:
            old_slot = next((s for s in ("branch", "town") if previous[s] and previous[s].casefold() in text.casefold()), None)
            replacement = clean_location(clauses[-1])
            if old_slot and replacement and len(replacement.split()) <= 4:
                replacement = re.sub(r"\s*(?:బ్రాంచ్|శాఖ|branch|పట్టణం|town)$", "", replacement, flags=re.I)
                self.details[old_slot] = replacement
                recognized = location_changed = True
            elif old_slot and not replacement:
                self.details[old_slot] = None
                recognized = location_changed = True

        # Gemini can supply semantic values the bounded regexes missed. It may
        # fill empty slots, but a confirmed value changes only after an explicit
        # correction whose replacement text is actually present in this turn.
        if interpretation:
            explicit = {item.field: item.value for item in interpretation.corrections if item.explicit}
            if self.details['intent'] is None and interpretation.intent != 'unknown':
                self.details['intent'] = interpretation.intent
                recognized = True
            elif 'intent' in explicit and interpretation.intent != 'unknown':
                self.details['intent'] = interpretation.intent
                recognized = True
            if self.details['bank'] is None and interpretation.bank:
                self.details['bank'] = interpretation.bank
                recognized = True
            elif 'bank' in explicit:
                self.details['bank'] = explicit['bank']
                recognized = True
            for slot in ('town', 'branch'):
                if slot in explicit:
                    self.details[slot] = explicit[slot]
                    recognized = True

        if previous["bank"] != self.details["bank"] and self.details["branch"] == previous["branch"]:
            self.details["branch"] = None
            self.preparation.focus = ''
            if previous['bank']:
                self.preparation.answers.pop('existing', None)
        if previous["town"] != self.details["town"] and self.details["branch"] == previous["branch"]:
            self.details["branch"] = None
            if previous['town']:
                self.preparation.answers.pop('address', None)

        if not self.details["intent"]:
            self.awaiting = "intent"
        elif not self.details["bank"]:
            self.awaiting = "bank"
        elif not (self.details["town"] or self.details["branch"] or self.preparation.location_skipped):
            self.awaiting = "location"
        else:
            self.awaiting = ""

        unsupported_scope = (
            self.preparation.answers.get('scope') == 'unsupported'
            or any(self.preparation.answers.get(key) == 'no' for key in ('single', 'adult', 'resident'))
        )
        if self.quick_checklist_shown and unsupported_scope:
            self.preparation.pending = ''
            self.awaiting = ''
            return self.save_turn(text, LIMIT)
        if self.details['bank'] == 'SBI' and self.details['intent'] == 'open_account':
            self.quick_checklist_shown = True
            self.awaiting = ''
            return self.save_turn(text, self.preparation.respond(
                text, self.details, '', self.turns[-1]['reply'] if self.turns else ''
            ))

        if wants_checklist:
            return self.save_turn(text, self._checklist_reply())

        if self.awaiting:
            known = ""
            if recognized and self.details["bank"] and self.details["intent"]:
                known = f"{self.details['bank']} బ్యాంకులో {INTENTS[self.details['intent']][1]} కోసం సహాయం కావాలని గుర్తుంచుకున్నాను. "
            if re.search(UNKNOWN, text, re.I):
                reply = "పరవాలేదు. ఆ వివరాన్ని నిర్ణయించుకున్న తర్వాత చెప్పండి; తెలిసిన వివరాలను గుర్తుంచుకుంటాను."
            else:
                reply = known + QUESTIONS[self.awaiting]
        else:
            location = " · ".join(str(self.details[s]) for s in ("town", "branch") if self.details[s])
            summary = f"{self.details['bank']} బ్యాంకు, {location}: {INTENTS[self.details['intent']][1]} కోసం సహాయం కావాలి."
            if not recognized and re.search(r"పత్రాలు|documents|requirements|అవసర|చార్జీ|fees|minimum|కనీస", text, re.I):
                reply = summary + " అవసరమైన పత్రాలు, అర్హతలు, రుసుములను ఆ బ్యాంకు అధికారిక వనరు లేదా సిబ్బందితో నిర్ధారించండి; ఇక్కడ ఊహించి చెప్పను."
            elif not recognized and not re.search(r"సరే|అవును|ధన్యవాద|thanks|okay|yes", text, re.I):
                reply = summary + " మీరు ఏ వివరాన్ని మార్చాలనుకుంటున్నారు?"
            else:
                reply = summary + " ఈ వివరాలతో బ్యాంకు సిబ్బందిని సంప్రదించవచ్చు. ఏదైనా మారితే చెప్పండి."
        if self.awaiting == 'location' and re.search(UNKNOWN, text, re.I):
            self.preparation.location_skipped = True
            self.awaiting = ''
            reply = 'బ్రాంచ్ పేరు తెలియకపోయినా పరవాలేదు. తెలిసినప్పుడు చెప్పవచ్చు.'
        else:
            reply = self.preparation.respond(text, self.details, reply, self.turns[-1]['reply'] if self.turns else '')
        if not recognized and previous_answers == self.preparation.answers and previous_self == self.preparation.account_for_self and not re.search(r'సరే|అవును|లేదు|తెలియదు|thanks|okay|yes|next|తర్వాత|continue|కొనసాగించు|నమస్తే|నమస్కారం|hello', text, re.I):
            context = QUESTIONS.get(self.awaiting) or ONBOARDING_QUESTIONS.get(self.preparation.pending, '')
            reply = 'మీ ఉద్దేశం స్పష్టంగా అర్థం కాలేదు. ' + (context or 'ఏ పత్రం లేదా ఏ వివరాన్ని గురించి చెబుతున్నారు?')
            self.preparation.reply_source_ids = []
        return self.save_turn(text, reply)

    def save_turn(self, text: str, reply: str) -> dict:
        """All routes commit through one path, including TTS replay/history."""
        turn = {"turn_id": str(uuid4()), "transcript": text, "reply": reply}
        self.turns.append(turn)
        self.turns = self.turns[-50:]
        self.touched = time.monotonic()
        return {**turn, "session_id": self.id, "details": self.details.copy(), "awaiting": self.awaiting, 'preparation': self.preparation.view(self.details)}


class ConversationStore:
    def __init__(self):
        self.sessions: dict[str, Conversation] = {}

    def get(self, session_id: str | None = None) -> Conversation:
        now = time.monotonic()
        self.sessions = {key: value for key, value in self.sessions.items() if now - value.touched < 3600}
        if session_id:
            if session_id not in self.sessions:
                raise HTTPException(404, "This conversation expired or the backend restarted. Start a new conversation.")
            session = self.sessions[session_id]
            session.touched = now
            return session
        if len(self.sessions) >= 100:
            raise HTTPException(503, "Too many active conversations. Try again later.")
        session = Conversation()
        self.sessions[session.id] = session
        return session


store = ConversationStore()
