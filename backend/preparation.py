"""Bounded Telugu/English preparation state machine, not an LLM."""
import re
from dataclasses import dataclass, field
from backend.knowledge import ENTRIES, SOURCES, DOCUMENTS, checklist

SCOPE = 'ఇది మీ ఒక్కరి పేరుతో సాధారణ సేవింగ్స్ ఖాతానా?'
LIMIT = 'ప్రస్తుతం SBIలో భారత నివాసి అయిన పెద్దవారి వ్యక్తిగత సాధారణ సేవింగ్స్ ఖాతా సందర్శనకే ధృవీకరించిన సహాయం ఉంది. మీ పరిస్థితికి SBI నియమాలను వర్తింపజేయను; సంబంధిత బ్యాంకుతో నిర్ధారించండి.'
PRIVACY = 'పత్రాలు అప్‌లోడ్ చేయవద్దు. ఆధార్/PAN నంబర్లు, OTP, PIN, పాస్‌వర్డ్‌లు ఇక్కడ చెప్పవద్దు.'
ONBOARDING_QUESTIONS = {
    'single': SCOPE,
    'adult': 'మీకు 18 ఏళ్లు నిండాయా?',
    'resident': 'మీరు భారతదేశంలో నివసిస్తున్నారా?',
    'existing': 'ఇప్పటికే SBIలో KYC పూర్తయిన ఖాతా ఉందా?',
}


@dataclass
class Preparation:
    answers: dict = field(default_factory=dict)
    pending: str = ''
    account_for_self: bool | None = None
    age_subject: str = 'unknown'
    focus: str = ''
    location_skipped: bool = False
    last_document: str = ''
    side_pending: str = ''
    interrupted: bool = False
    saved_focus: str = ''
    reply_source_ids: list = field(default_factory=list)

    @staticmethod
    def has_onboarding_cue(text):
        return bool(re.search(
            r'myself|for me|in my name|my account|someone else|another person|for him|for her|'
            r'\u0c28\u0c3e.{0,40}\u0c15\u0c4b\u0c38|\u0c35\u0c47\u0c30\u0c4a\u0c15\u0c30\u0c3f|'
            r'\u0c2e\u0c30\u0c4a\u0c15\u0c30\u0c3f|\u0c07\u0c02\u0c15\u0c4a\u0c15\u0c30\u0c3f|'
            r'\d{1,3}\s*(?:\u0c0f\u0c33\u0c4d\u0c32\u0c41|\u0c0f\u0c33\u0c4d\u0c33\u0c41|years? old)|'
            r'\u0c07\u0c30\u0c35\u0c48.{0,16}(?:\u0c0f\u0c33\u0c4d\u0c32\u0c41|\u0c0f\u0c33\u0c4d\u0c33\u0c41)', text, re.I))

    def ingest(self, text):
        # Only categorical facts, never document numbers, are requested.
        if re.search(r'myself|for me|in my name|my account|\u0c28\u0c3e.{0,40}\u0c15\u0c4b\u0c38', text, re.I):
            self.account_for_self = True
            self.answers['single'] = 'yes'
            self.answers.pop('scope', None)
        elif re.search(r'someone else|another person|for him|for her|\u0c35\u0c47\u0c30\u0c4a\u0c15\u0c30\u0c3f|\u0c2e\u0c30\u0c4a\u0c15\u0c30\u0c3f|\u0c07\u0c02\u0c15\u0c4a\u0c15\u0c30\u0c3f|\u0c35\u0c47\u0c30\u0c47\s+\u0c35\u0c4d\u0c2f\u0c15\u0c4d\u0c24\u0c3f', text, re.I):
            self.account_for_self = False
            self.age_subject = 'unclear'
        years = r'(?:\u0c0f\u0c33\u0c4d\u0c32\u0c41|\u0c0f\u0c33\u0c4d\u0c33\u0c41|\u0c38\u0c02\u0c35\u0c24\u0c4d\u0c38\u0c30\u0c3e\u0c32\u0c41|\u0c35\u0c2f\u0c38\u0c41|years? old)'
        age_match = re.search(r'(\d{1,3})\s*' + years, text, re.I)
        if age_match:
            age_value = int(age_match[1])
        else:
            age_words = [
                (r'\u0c07\u0c30\u0c35\u0c48\s+\u0c12\u0c15\u0c4d\u0c15', 21),
                (r'\u0c07\u0c30\u0c35\u0c48\s+\u0c30\u0c46\u0c02\u0c21\u0c41', 22),
                (r'\u0c07\u0c30\u0c35\u0c48\s+\u0c2e\u0c42\u0c21\u0c41', 23),
                (r'\u0c07\u0c30\u0c35\u0c48\s+\u0c28\u0c3e\u0c32\u0c41\u0c17\u0c41', 24),
                (r'\u0c07\u0c30\u0c35\u0c48\s+\u0c05\u0c48\u0c26\u0c41', 25),
                (r'\u0c07\u0c30\u0c35\u0c48', 20),
            ]
            age_value = next((value for phrase, value in age_words if re.search(phrase + r'.{0,20}' + years, text, re.I)), None)
        if age_value is not None:
            self.answers['age_years'] = age_value
            if self.account_for_self is True:
                self.age_subject = 'speaker'
                self.answers['adult'] = 'yes' if age_value >= 18 else 'no'
            elif self.account_for_self is not False:
                self.age_subject = 'unclear'
        if self.pending == 'age_subject' and re.search(r'\u0c28\u0c3e\s*\u0c35\u0c2f\u0c38\u0c41|\u0c28\u0c3e\u0c26\u0c3f|my age|speaker', text, re.I):
            self.age_subject = 'speaker'
            self.pending = 'adult'
        elif self.pending == 'age_subject' and re.search(r'\u0c06\s*\u0c35\u0c4d\u0c2f\u0c15\u0c4d\u0c24\u0c3f|\u0c16\u0c3e\u0c24\u0c3e\u0c26\u0c3e\u0c30\u0c41|account holder|their age', text, re.I):
            self.age_subject = 'account_holder'
            self.pending = 'adult'
        if re.search(r'మైనర్|minor|NRI|ప్రవాస|joint|జాయింట్|వ్యాపార|business|current account|కరెంట్|పిల్ల|విదేశాల్లో|salary|జీతం|పెన్షన్|pension|BSBD|basic savings', text, re.I):
            self.answers['scope'] = 'unsupported'
        elif re.search(r'సాధారణ సేవింగ్స్|ordinary savings|నా ఒక్కరి|నా కోసం.*సేవింగ్స్', text, re.I):
            self.answers['single'] = 'yes'
            self.answers.pop('scope', None)
        if re.search(r'భారత.*నివాస|resident indian|ఇండియాలో ఉంటాను', text, re.I):
            self.answers['resident'] = 'yes'
        age = re.search(r'(\d{1,3})\s*(?:ఏళ్లు|ఏళ్ల|సంవత్సరాలు|years old)', text, re.I)
        if age:
            self.answers['adult'] = 'yes' if int(age[1]) >= 18 else 'no'
        if re.search(r'18.*నిండ|పెద్దవా|adult', text, re.I) and not re.search(r'నిండలేదు|not.*adult', text, re.I):
            self.answers['adult'] = 'yes'
        if self.pending in ('single', 'adult', 'resident', 'existing') and re.fullmatch(r'\s*(అవును|yes|ఉంది|ఉన్నాను|నిండాయి)[.!\s]*', text, re.I):
            self.answers[self.pending] = 'yes'
        elif self.pending in ('single', 'adult', 'resident', 'existing') and re.fullmatch(r'\s*(కాదు|లేదు|no)[.!\s]*', text, re.I):
            self.answers[self.pending] = 'no'
        if self.pending == 'existing' and re.search(r'నాకు అది లేదు|don.t have (it|this)', text, re.I):
            self.answers['existing'] = 'no'
        if self.pending == 'identity_options':
            if re.fullmatch(r'\s*(లేదు|లేవు|no|none)[.!\s]*', text, re.I):
                self.answers['identity'] = 'none'
            elif re.fullmatch(r'\s*(ఉంది|అవును|yes)[.!\s]*', text, re.I):
                self.answers['identity'] = 'available'
        if re.search(r'ఇప్పటికే.*(?:SBI|ఎస్).*KYC|existing.*kyc', text, re.I):
            self.answers['existing'] = 'no' if re.search(r'లేదు|not', text, re.I) else 'yes'
        if re.search(r'చిరునామా.*(?:పాత|మారింది)|old address', text, re.I):
            self.answers['address'] = 'old'
        elif re.search(r'చిరునామా.*(?:సరైన|ప్రస్తుత)|current address', text, re.I):
            self.answers['address'] = 'current'
        if re.search(r'PAN|పాన్', text, re.I) and not re.search(r'ఏంటి|అంటే|what|explain', text, re.I):
            self.answers['pan'] = 'no' if re.search(r'లేదు|లేదు|don.t have|కాదు', text, re.I) else 'yes' if re.search(r'ఉంది|ఉన్న|have', text, re.I) else self.answers.get('pan', 'unknown')
        if re.search(r'ఏ పత్రమూ లేదు|పత్రాలు లేవు|no documents|no ovd', text, re.I):
            self.answers['identity'] = 'none'
        elif re.search(r'(పాస్‌పోర్ట్|passport|వోటర్|ఓటర్|driving licence|ఆధార్).*(ఉంది|ఉన్న|have)', text, re.I):
            self.answers['identity'] = 'available'

    def supported(self, details):
        return details['bank'] == 'SBI' and details['intent'] == 'open_account' and self.answers.get('scope') != 'unsupported' and all(self.answers.get(k) == 'yes' for k in ('single', 'adult', 'resident'))

    def view(self, details):
        return {'answers': self.answers.copy(), 'pending': self.pending, 'focus': self.focus,
                'account_for_self': self.account_for_self, 'age_subject': self.age_subject,
                'last_document': self.last_document, 'side_pending': self.side_pending, 'interrupted': self.interrupted,
                'checklist': checklist(self.answers) if self.supported(details) and 'existing' in self.answers else [],
                'coverage': 'SBI • resident adult • individual ordinary savings • branch visit',
                'reply_sources': [SOURCES[k] for k in self.reply_source_ids],
                'notice': 'ఇది సందర్శనకు సన్నాహం మాత్రమే. ఖాతా తప్పకుండా తెరుస్తారని హామీ కాదు.'}

    def walkthrough_answer(self, text):
        """Only answers to the active item advance it; document questions interrupt."""
        if self.pending or self.interrupted or self.focus not in ('identity', 'address', 'tax', 'existing', 'visit', 'small'):
            return None
        if re.fullmatch(r'\s*(అవును|ఉంది|ఉన్నాయి|yes|i have it)[.!\s]*', text, re.I):
            return 'yes'
        if re.fullmatch(r'\s*(లేదు|లేవు|కాదు|no|నాకు అది లేదు)[.!\s]*', text, re.I):
            return 'no'
        if re.search(r'\?|ఏంటి|అంటే|ఏం|ఎలా|what|why|how|లేకపోతే|without', text, re.I):
            return None
        topics = {'identity': r'ఆధార్|పాస్.?పోర్ట్|passport|వోటర్|ఓటర్|identity|OVD',
                  'tax': r'PAN|పాన్', 'address': r'చిరునామా|address'}
        if self.focus in topics and re.search(topics[self.focus], text, re.I):
            if re.search(r'లేదు|లేవు|కాదు|పాత|old|don.t have|do not have', text, re.I):
                return None if self.focus == 'identity' else 'no'
            if re.search(r'ఉంది|ఉన్నాయి|ప్రస్తుత|current|i have', text, re.I):
                return 'yes'
        return None

    def walkthrough_reply(self):
        """Voice summaries only; the complete sourced checklist stays in view()."""
        if self.focus == 'identity' and self.answers.get('identity') == 'none':
            self.focus = 'small'
        if self.focus == 'tax' and self.answers.get('pan') == 'no':
            self.focus = 'tax_missing'
        if self.focus == 'tax_missing' and self.answers.get('pan') == 'yes':
            self.focus = 'tax'
        if self.focus == 'intro':
            count = len(checklist(self.answers))
            return f'SBI ఖాతా కోసం {count} ప్రధాన అంశాలు చూసుకోవాలి. ఒక్కొక్కటిగా చూద్దామా?'
        if self.focus == 'tax_missing':
            self.reply_source_ids = ENTRIES['tax']['source_ids']
            return DOCUMENTS['pan']['missing'].replace('మీ బ్యాంకుతో', 'SBI శాఖతో') + ' తర్వాతి అంశానికి వెళ్దామా?'
        if self.focus == 'address_missing':
            self.reply_source_ids = ENTRIES['address']['source_ids']
            return 'రెండు నెలలు దాటని యుటిలిటీ బిల్లు వంటి అనుమతించిన ఆధారం ఉపయోగపడవచ్చు. ఈ మార్గంలో మూడు నెలల్లో ప్రస్తుత చిరునామాతో OVD ఇవ్వాలి. తర్వాతి అంశానికి వెళ్దామా?'
        replies = {
            'identity': 'పేరు, చిరునామా ఉన్న అనుమతించిన గుర్తింపు పత్రం కావాలి; ఆధార్ ఒక్కటే మార్గం కాదు. మీ దగ్గర అలాంటి పత్రం ఉందా?',
            'address': 'గుర్తింపు పత్రంలో ప్రస్తుత చిరునామా ఉండాలి. మీ పత్రంలో ప్రస్తుత చిరునామా ఉందా?',
            'tax': 'PAN ఉంటే SBIకి చూపించడానికి సిద్ధంగా ఉంచండి; నంబరు ఇక్కడ చెప్పవద్దు. మీ దగ్గర PAN ఉందా?',
            'existing': 'SBIలో KYC పూర్తై వివరాలు మారకపోతే, అవే పత్రాలు మళ్లీ అవసరం కాకపోవచ్చు. మీ వివరాలు మారలేదా?',
            'visit': 'దరఖాస్తు, ఫోటో విధానం, కాపీల సంఖ్యను SBI శాఖతో నిర్ధారించండి. ఈ వివరాలు శాఖను అడుగుతారా?',
            'small': 'గుర్తింపు పత్రం లేకపోతే పరిమితులున్న Small Account గురించి SBIని అడగవచ్చు. దీని గురించి శాఖను అడుగుతారా?',
            'done': 'ప్రధాన అంశాలు పూర్తయ్యాయి. మొత్తం జాబితా చెప్పాలా?',
        }
        if self.focus in ENTRIES:
            self.reply_source_ids = ENTRIES[self.focus]['source_ids']
        self.last_document = {'tax': 'pan', 'identity': 'identity', 'address': 'address',
                              'existing': 'kyc', 'small': 'identity', 'visit': 'visit'}.get(self.focus, self.last_document)
        return replies.get(self.focus, replies['done'])

    def respond(self, text, details, fallback, last_reply):
        # Questions/pronouns have already been handled by dialogue.py.
        answer = self.walkthrough_answer(text)
        self.interrupted = False
        self.saved_focus = ''
        self.side_pending = ''
        self.reply_source_ids = []
        if details['bank'] and (details['bank'] != 'SBI' or details['intent'] not in (None, 'open_account')):
            self.pending = self.focus = ''
            return LIMIT
        if self.answers.get('scope') == 'unsupported' or any(self.answers.get(k) == 'no' for k in ('single', 'adult', 'resident')):
            self.pending = self.focus = ''
            return LIMIT
        if details['bank'] != 'SBI' or details['intent'] != 'open_account':
            return fallback
        # A natural opening starts here; location is optional for preparation.
        if not self.focus and not self.pending:
            self.focus = 'intro'
            return self.walkthrough_reply()
        if self.account_for_self is False and self.age_subject == 'unclear':
            self.pending = 'age_subject'
            return 'ఖాతా ఎవరి కోసం? వయసు ఖాతాదారిదా లేదా మీదా?'
        if self.pending == 'age_subject':
            return 'వయసు మీదా, లేదా ఖాతా తెరిచే వ్యక్తిదా?'
        unanswered = [key for key in ONBOARDING_QUESTIONS if key not in self.answers]
        if unanswered:
            key = unanswered[0]
            if self.pending in unanswered and re.fullmatch(r'\s*(తర్వాత|తరువాత|next|skip)[.!\s]*', text, re.I):
                key = unanswered[(unanswered.index(self.pending) + 1) % len(unanswered)]
            self.pending = key
            return ONBOARDING_QUESTIONS[key]
        self.pending = ''
        keys = [item['id'] for item in checklist(self.answers)]
        if self.focus in ('', 'intro'):
            self.focus = keys[0]
            return self.walkthrough_reply()
        if answer:
            if self.focus == 'tax':
                self.answers['pan'] = answer
                if answer == 'no':
                    self.focus = 'tax_missing'
                    return self.walkthrough_reply()
            elif self.focus == 'identity':
                if answer == 'no':
                    self.pending = self.side_pending = 'identity_options'
                    return 'ఆధార్ ఒక్కటే మార్గం కాదు; పాస్‌పోర్ట్, ఓటర్ కార్డు వంటి ఇతర అనుమతించిన పత్రాలు కూడా ఉన్నాయి. వీటిలో ఏదైనా ఉందా?'
                self.answers['identity'] = 'available'
            elif self.focus == 'address':
                self.answers['address'] = 'current' if answer == 'yes' else 'old'
                if answer == 'no':
                    self.focus = 'address_missing'
                    return self.walkthrough_reply()
        if answer or re.fullmatch(r'\s*(తర్వాత|తరువాత|next|skip|సరే|కొనసాగించు|continue|yes|అవును)[.!\s]*', text, re.I):
            # Use the old position when an answer removes the current item.
            current = self.focus.removesuffix('_missing')
            if current in keys:
                index = keys.index(current) + 1
                self.focus = keys[index] if index < len(keys) else 'done'
            elif current == 'address':
                self.focus = 'tax'
        return self.walkthrough_reply()
