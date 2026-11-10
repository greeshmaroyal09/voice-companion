"""Question-first interruption routing. Bounded rules, not general NLU.

This layer never advances onboarding. A handled turn can update only the
explicit document fact and discussion context; the saved question survives.
"""
import re
from backend.knowledge import ENTRIES, DOCUMENTS

TOPICS = {
    'pan': r'(?<![a-z])p\.?a\.?n\.?(?![a-z])|పాన్|ప్యాన్|పన్ను గుర్తింపు',
    'declaration': r'form\s*(?:60|97)|ఫా(?:రం|రమ్)\s*(?:60|97)',
    'aadhaar': r'aadh?aar|ఆధార్|ఆధార కార్డు',
    'passport': r'passport|పాస్\s*పోర్ట్|పాస్‌పోర్ట్',
    'voter': r'voter|ఓటర్|వోటర్',
    'licence': r'driving licen[cs]e|డ్రైవింగ్ లైసెన్స్',
    'kyc': r'\bkyc\b|కేవైసీ|కెవైసి',
    'address': r'address|చిరునామా',
    'identity': r'\bovd\b|గుర్తింపు పత్ర|identity document',
    'visit': r'ఫోటో|copies|photocopy|జిరాక్స్|కాపీలు',
}
QUESTION = r'\?|ఏంటి|ఏమిటి|అంటే|ఎందుకు|ఎలా|వివరించ|చెప్పు|చెప్పండి|తెలుప|తెలియజే|అర్థం|ఎన్ని|what|why|how|explain|tell me|meaning'
MISSING = r'లేదు|లేవు|లేదండి|లేకపోతే|లేకుండా|don.t have|do not have|without|not available|lost|పోయింది'
PRESENT = r'ఉంది|ఉన్నది|ఉన్నాయి|ఉన్నది|i have|got (it|one)'
REPEAT = r'మళ్ళీ|మళ్లీ|మరొకసారి|ఇంకోసారి|repeat|say (it |that )?again'
RESUME = r'\s*(కొనసాగించు|కొనసాగించండి|ముందుకు వెళ్దాం|సరే|అర్థమైంది|continue|resume|okay|ok|next|తర్వాత)[.!\s]*'
CLARIFY = r'అది|ఇది|దాని|దీని|అర్థం కాలేదు|అర్థం కావడం లేదు|సులభంగా|this|that|it|simpler|understand'


def matches(pattern, text):
    return re.search(pattern, text, re.I) is not None


def topic_in(text):
    hits = [(hit.start(), topic) for topic, pattern in TOPICS.items() for hit in re.finditer(pattern, text, re.I)]
    return max(hits)[1] if hits else None


def discuss(prep, topic, reply=None):
    document = DOCUMENTS[topic]
    # Keep checklist position separate from the temporary document discussion.
    if not prep.interrupted:
        prep.saved_focus = prep.focus
    prep.last_document = topic
    prep.interrupted = True
    prep.focus = document['entry']
    prep.reply_source_ids = document['source_ids']
    return reply or document['explanation']


def handle_interruption(text, prep, last_reply, pending_question, bank=None):
    """Return a reply or None to allow a factual answer/correction to progress."""
    if matches(REPEAT, text):
        return last_reply or 'ఇంకా సమాధానం ఇవ్వలేదు. ఏ విషయం గురించి తెలుసుకోవాలనుకుంటున్నారు?'
    if prep.interrupted and re.fullmatch(RESUME, text, re.I):
        prep.interrupted = False
        prep.side_pending = ''
        prep.reply_source_ids = []
        prep.focus = prep.saved_focus
        prep.saved_focus = ''
        # Re-present the saved question without interpreting 'okay' as consent.
        if pending_question:
            return pending_question
        if prep.focus:
            return prep.walkthrough_reply()
        return None

    topic = topic_in(text)
    question = matches(QUESTION, text)
    missing = matches(MISSING, text)
    present = matches(PRESENT, text)
    pronoun = matches(CLARIFY, text)
    if matches(r'ఏ పత్రమూ లేదు|పత్రాలు లేవు|no documents|no ovd', text):
        prep.answers['identity'] = 'none'
        prep.side_pending = ''
        return discuss(prep, 'identity', ENTRIES['small']['text'])
    if prep.side_pending == 'identity_options' and re.fullmatch(r'\s*(లేదు|లేవు|no|none)[.!\s]*', text, re.I):
        prep.answers['identity'] = 'none'
        prep.side_pending = ''
        return discuss(prep, 'identity', ENTRIES['small']['text'])

    # An explicit noun beats a pronoun and the saved onboarding question.
    if not topic and ((pronoun and (question or missing or present)) or (prep.interrupted and re.fullmatch(r'\s*(లేదు|లేవు|ఉంది|no)[.!\s]*', text, re.I))):
        topic = prep.last_document if prep.interrupted or missing or present else None
        if not topic and prep.focus and not prep.pending:
            topic = {'tax': 'pan', 'identity': 'identity', 'existing': 'kyc', 'address': 'address', 'visit': 'visit', 'small': 'identity'}.get(prep.focus)
        if not topic:
            if missing or present:
                return 'ఏ పత్రం గురించి చెబుతున్నారు? పేరు మాత్రమే చెప్పండి; నంబరు వద్దు.'
            return ('మీరు అడిగినది స్పష్టంగా అర్థం కాలేదు. ' + pending_question) if pending_question else 'ఏ పత్రం లేదా విషయం గురించి వివరించాలి?'

    # A KYC statement containing banking/profile facts still belongs to the
    # normal extractor. Questions, named document facts and pronouns do not.
    profile_statement = matches(r'ఖాతా.*తెరవ|account.*open|సాధారణ సేవింగ్స్|ఏళ్ల|years old', text) and not question
    if topic and not profile_statement:
        if prep.side_pending:
            prep.side_pending = ''
        # Hypothetical questions must not become possession facts.
        hypothetical = matches(r'లేకపోతే|without|what if|if i', text)
        if (missing or present) and not hypothetical:
            value = 'no' if missing else 'yes'
            if topic == 'pan':
                prep.answers['pan'] = value
            elif topic in ('aadhaar', 'passport', 'voter', 'licence'):
                prep.answers[topic] = value
                if present and not missing:
                    prep.answers['identity'] = 'available'
            elif topic == 'address':
                prep.answers['address'] = 'old' if missing else 'current'
        if topic == 'address':
            if matches(r'పాత|మారింది|old', text) and not question:
                prep.answers['address'] = 'old'
            elif matches(r'ప్రస్తుత|సరైన|current', text) and not question:
                prep.answers['address'] = 'current'
        if missing:
            if topic == 'pan':
                branch = f'{bank} శాఖతో' if bank else 'మీ బ్యాంకుతో'
                return discuss(prep, topic, DOCUMENTS['pan']['missing'].replace('మీ బ్యాంకుతో', branch))
            if topic in ('aadhaar', 'passport', 'voter', 'licence', 'identity'):
                prep.side_pending = 'identity_options'
                # Reuse the pending slot only when onboarding has no saved
                # question; never replace an active onboarding question.
                if not prep.pending:
                    prep.pending = 'identity_options'
                return discuss(prep, topic, ENTRIES['identity']['text'] + ' వీటిలో ఏదైనా పత్రం ఉందా?')
            reply = DOCUMENTS[topic].get('missing', 'ఈ పత్రానికి వర్తించే ప్రత్యామ్నాయం మీ బ్యాంకుతో నిర్ధారించండి. పత్రం నంబరు ఇక్కడ చెప్పవద్దు.')
            return discuss(prep, topic, reply.replace('మీ బ్యాంకుతో', f'{bank} శాఖతో') if bank else reply)
        reply = DOCUMENTS[topic]['explanation']
        return discuss(prep, topic, reply.replace('మీ బ్యాంకుతో', f'{bank} శాఖతో') if bank else reply)

    if question or matches(r'అర్థం కాలేదు|అర్థం కావడం లేదు|నాకు తెలియట్లేదు|confused|huh', text):
        if prep.pending and not topic:
            # Explain the actual pending question only for an unqualified
            # clarification, never for a named document or unknown question.
            if matches(r'అది ఏంటి|అర్థం కాలేదు|what does that mean|explain that', text):
                return 'ముందు అడిగింది: ' + pending_question
        return 'ఏ పత్రం లేదా ఏ విషయం గురించి తెలుసుకోవాలనుకుంటున్నారు? పేరు లేదా కొంచెం వివరంగా చెప్పండి.'
    return None
