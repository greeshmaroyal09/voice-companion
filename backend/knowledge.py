"""Reviewed banking facts. No retrieval, provider calls, or dialogue logic here.

Checked against full official pages on 2026-11-08. Dates are source dates,
not inferred effective dates. Telugu text is our plain-language paraphrase.
"""
from copy import deepcopy

CHECKED = '2026-11-08'
SOURCES = {
    'rbi': {'title': 'RBI Master Direction — KYC, 2016', 'url': 'https://www.rbi.org.in/Scripts/BS_ViewMasDirections.aspx?id=11566', 'published_or_updated': '2025-08-14', 'effective_date': None},
    'faq': {'title': 'RBI FAQs on Master Direction on KYC', 'url': 'https://rbi.org.in/Scripts/FAQDisplay.aspx?Id=173', 'published_or_updated': '2025-06-09', 'effective_date': None},
    'sbi_kyc': {'title': 'SBI KYC Documents — Individuals', 'url': 'https://sbi.bank.in/web/personal-banking/information-services/kyc-guidelines/kyc-documents-individuals', 'published_or_updated': '2026-06-09', 'effective_date': None},
    'sbi_savings': {'title': 'SBI Savings Bank Account', 'url': 'https://sbi.bank.in/web/personal-banking/accounts/saving-account/savings-bank-account', 'published_or_updated': '2026-03-13', 'effective_date': None},
    'sbi_declaration': {'title': 'SBI link labelled Form 60 — PDF titled Form No. 97', 'url': 'https://sbi.bank.in/documents/16012/0/11052026_form_no_97.pdf/098d5eb8-95dd-e86b-89dd-05754752ba37?t=1778501367720', 'published_or_updated': None, 'effective_date': None},
}
for source in SOURCES.values():
    source['checked_on'] = CHECKED


def entry(id, title, kind, text, sources, conditions, exceptions, confirm=False, status='verified'):
    return dict(id=id, title=title, kind=kind, text=text, source_ids=sources,
                category='SBI; resident adult; single-holder ordinary savings; branch visit',
                conditions=conditions, exceptions=exceptions, branch_confirmation=confirm,
                status=status, checked_on=CHECKED)


ENTRIES = {
    'identity': entry('identity', 'గుర్తింపు, చిరునామా పత్రం', 'alternatives',
        'పేరు, చిరునామా ఉన్న పాస్‌పోర్ట్, డ్రైవింగ్ లైసెన్స్, ఓటర్ కార్డు, ఆధార్ ఆధారం, అధికారి సంతకం చేసిన NREGA జాబ్ కార్డు లేదా NPR లేఖలో సరిపోయే ఒక పత్రం గురించి బ్యాంకుతో మాట్లాడండి. ఆధార్ ఒక్కటే మార్గం కాదు.',
        ['sbi_kyc', 'rbi'], 'Individual KYC; valid identity/address evidence.',
        'Equivalent e-documents and CKYC retrieval are possible under RBI procedures; section 7 subsidy cases have Aadhaar conditions.', True),
    'tax': entry('tax', 'PAN లేదా వర్తించే ప్రకటన', 'required',
        'PAN పన్ను గుర్తింపుకు ఉపయోగించే పత్రం. ఉంటే బ్యాంకుకు చూపించడానికి సిద్ధం చేసుకోండి; నంబరు ఇక్కడ చెప్పవద్దు. PAN లేకపోతే వర్తించే ప్రకటన గురించి బ్రాంచ్‌ను అడగండి.',
        ['rbi', 'sbi_declaration'], 'RBI section 16 lists PAN/e-document or Form 60.',
        'SBI Form 60 link now serves Form 97. Applicable current declaration and eligibility need branch confirmation.', True, 'needs_confirmation'),
    'address': entry('address', 'పత్రంలో పాత చిరునామా ఉంటే', 'conditional',
        'పత్రంలో ప్రస్తుత చిరునామా లేకపోతే, రెండు నెలలు దాటని యుటిలిటీ బిల్లు వంటి అనుమతించిన చిరునామా ఆధారం ఉపయోగపడవచ్చు. ఈ మార్గంలో మూడు నెలల్లో ప్రస్తుత చిరునామాతో OVD ఇవ్వాలి. మీ పత్రానికి వర్తించే విధానాన్ని బ్యాంకుతో నిర్ధారించండి.',
        ['faq'], 'Only when OVD lacks current address; FAQ 7–8.',
        'Other deemed address documents exist. Aadhaar e-KYC address self-declaration is a distinct RBI route.', True),
    'existing': entry('existing', 'ఇప్పటికే SBI KYC ఉంటే', 'conditional',
        'ఇప్పటికే SBIలో KYC పూర్తై, గుర్తింపు లేదా చిరునామా వివరాలు మారకపోతే, మరో ఖాతాకు మళ్లీ అవే KYC పత్రాలు ఇవ్వనవసరం లేదని RBI FAQ చెబుతోంది. మీ రికార్డు స్థితిని బ్యాంకుతో నిర్ధారించండి.',
        ['faq'], 'Existing KYC-compliant customer of same bank; FAQ 4.', 'Changed identity/address requires review.', True),
    'small': entry('small', 'ఏ గుర్తింపు పత్రమూ లేకపోతే', 'branch_confirmation',
        'OVD లేకపోతే పరిమితులతో ఉండే Small Account గురించి SBIని అడగవచ్చు. ఇది సాధారణ సేవింగ్స్ ఖాతాతో సమానం కాదు; లావాదేవీ పరిమితులు, కాలపరిమితి వర్తిస్తాయి.',
        ['faq', 'sbi_kyc'], 'No OVD; separate Small Account process.', 'Do not apply ordinary-account checklist as sufficient.', True),
    'visit': entry('visit', 'బ్రాంచ్‌లో నిర్ధారించాల్సినవి', 'branch_confirmation',
        'మీకు వర్తించే దరఖాస్తు, ఫోటో విధానం, కాపీల సంఖ్యను బ్రాంచ్‌తో నిర్ధారించండి. ఈ జాబితాలో వాటి సంఖ్య ధృవీకరించలేదు. కాపీల దుకాణంలో ఊహించి కాపీలు తీయించాల్సిన అవసరం లేదు.',
        ['rbi', 'sbi_savings'], 'Branch-specific preparation details not established by reviewed sources.',
        'No fixed copy/photo count or fee asserted.', True, 'unverified'),
    'balance': entry('balance', 'నెలవారీ సగటు నిల్వ', 'product',
        'పరిశీలించిన SBI సాధారణ Savings Bank Account పేజీలో నెలవారీ సగటు నిల్వ NIL అని ఉంది. ఇది అన్ని సేవలు ఉచితం అన్న అర్థం కాదు; ఎంచుకున్న ఖాతా, సేవల ఛార్జీలను నిర్ధారించండి.',
        ['sbi_savings'], 'Ordinary SBI Savings Bank Account only.', 'Not a claim about other products or service fees.', True),
}

# General explanations are not gated by the SBI preparation category.
# These reuse the reviewed regulatory facts; they are not eligibility advice.
DOCUMENTS = {
    'pan': {'entry': 'tax', 'source_ids': ['rbi', 'sbi_declaration'],
            'explanation': 'PAN అంటే Permanent Account Number. ఇది పన్ను గుర్తింపుకు ఉపయోగించే సంఖ్య. బ్యాంకు KYCలో PAN లేదా వర్తించే ప్రకటన గురించి అడుగుతుంది. మీ PAN నంబరు ఇక్కడ చెప్పవద్దు.',
            'missing': 'PAN లేకపోతే సాధారణంగా Form 60 ప్రకటన ఇస్తారు. ప్రస్తుతం వర్తించే ఫారాన్ని మీ బ్యాంకుతో నిర్ధారించండి.'},
    'declaration': {'entry': 'tax', 'source_ids': ['rbi', 'sbi_declaration'],
                    'explanation': 'PAN లేనప్పుడు సాధారణంగా Form 60లో వివరాలను తెలియజేస్తారు. ప్రస్తుతం వర్తించే ఫారాన్ని మీ బ్యాంకుతో నిర్ధారించండి; ఇక్కడ ఫారం నింపాల్సిన అవసరం లేదు.'},
    'kyc': {'entry': 'existing', 'source_ids': ['faq'],
            'explanation': 'KYC అంటే Know Your Customer. బ్యాంకు మీ గుర్తింపు, చిరునామా వంటి వివరాలను తనిఖీ చేసే ప్రక్రియ. అది ప్రత్యేకంగా మీ దగ్గర ఉండాల్సిన ఒక కార్డు కాదు.'},
    'identity': {'entry': 'identity', 'source_ids': ['rbi', 'sbi_kyc'], 'explanation': ENTRIES['identity']['text']},
    'address': {'entry': 'address', 'source_ids': ['faq'], 'explanation': ENTRIES['address']['text']},
    'visit': {'entry': 'visit', 'source_ids': ['rbi', 'sbi_savings'], 'explanation': ENTRIES['visit']['text']},
}
for key, title in [('aadhaar', 'ఆధార్'), ('passport', 'పాస్‌పోర్ట్'), ('voter', 'ఓటర్ కార్డు'), ('licence', 'డ్రైవింగ్ లైసెన్స్')]:
    DOCUMENTS[key] = {'entry': 'identity', 'source_ids': ['rbi', 'sbi_kyc'],
                      'explanation': f'{title} బ్యాంకు KYCలో అనుమతించిన గుర్తింపు పత్రాలలో ఒకటి. పేరు, చిరునామా వివరాలను బ్యాంకు పరిశీలిస్తుంది. ఆధార్ ఒక్కటే మార్గం కాదు; ఇతర అనుమతించిన పత్రాలు కూడా ఉన్నాయి. పత్రం సంఖ్య ఇక్కడ చెప్పవద్దు.'}


def checklist(answers):
    keys = ['existing' if answers.get('existing') == 'yes' else 'identity', 'tax', 'visit']
    if answers.get('identity') == 'none':
        keys = ['small', 'tax', 'visit']
    if answers.get('address') == 'old' or (answers.get('address') != 'current' and answers.get('identity') != 'none' and answers.get('existing') != 'yes'):
        keys.insert(1, 'address')
    items = [deepcopy(ENTRIES[key]) for key in keys]
    for item in items:
        item['sources'] = [SOURCES[key] for key in item['source_ids']]
        if item['id'] == 'tax' and answers.get('pan') == 'no':
            item['text'] = 'PAN లేదని చెప్పారు. RBIలో Form 60 ప్రస్తావన ఉంది; SBI లింకు Form 97 చూపుతోంది. మీకు వర్తించే తాజా ప్రకటన, అర్హతను బ్రాంచ్‌తో నిర్ధారించండి.'
    return items
