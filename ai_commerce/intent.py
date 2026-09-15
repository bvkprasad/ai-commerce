"""Deliberately narrow grammar: ambiguous or unparsed requirements trigger clarification."""
import re
from dataclasses import asdict
from .domain import Request, paise


def interpret(data, ontology):
    request = Request.parse(data, ontology)
    text = request.query.lower().strip()
    if not text:
        return request, []
    original = text
    text = re.sub(r'\bwi[\s-]*fi\b', 'wifi', text)
    if re.search(r'\bsmart\b', text):
        return request, ['Does smart control mean app control, voice control, remote access, or built-in Wi-Fi?']
    if re.search(r'\b(tomorrow|today)\b', text):
        return request, ['Supply delivery_by as an exact timestamp with timezone.']
    features = dict(request.features)
    issues = []
    for phrase, name in [('built-in wifi', 'built_in_wifi'), ('built in wifi', 'built_in_wifi'),
                         ('app control', 'app_control'), ('voice control', 'voice_control'),
                         ('remote access', 'remote_access')]:
        if phrase in text:
            if re.search(r'\b(no|not|without)\b', text):
                issues.append('Express negated requirements explicitly in features using false.')
            elif name in features and features[name] is False:
                issues.append(f'Query conflicts with structured feature {name}.')
            else:
                features[name] = True
            text = text.replace(phrase, ' ')
    category = request.category
    for pattern, value in [(r'\bwashing\s*machines?\b', 'washing_machine'),
                            (r'\b(?:acs?|air conditioners?)\b', 'ac'), (r'\bdocks?\b', 'dock')]:
        if re.search(pattern, text):
            if category and category != value:
                issues.append('Choose one product category.')
            category = value
            text = re.sub(pattern, ' ', text)
    budget = request.budget_paise
    match = re.search(r'\bunder\s*(?:₹|inr\s*|rs\.?\s*)?(\d+(?:,\d{3})*(?:\.\d{1,2})?)(?![\d.])', text)
    if match:
        extracted = paise(match.group(1).replace(',', ''))
        if budget is not None and budget != extracted:
            issues.append('Query budget conflicts with budget_paise.')
        budget = extracted
        text = text[:match.start()] + ' ' + text[match.end():]
    text = re.sub(r'\b(find|a|an|the|with|and|please|me|show)\b', ' ', text)
    remainder = text.strip(' .,?!')
    if remainder:
        issues.append('Uninterpreted requirement: ' + remainder + '. Use structured fields or clarify.')
    values = asdict(request)
    values.update(category=category, features=features, budget_paise=budget)
    return Request.parse(values, ontology), issues
