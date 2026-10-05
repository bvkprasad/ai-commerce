"""Supported features, request parsing, and offer checks. Money is INR paise."""
import re
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

CATEGORIES = {'washing_machine', 'ac', 'dock'}
CONFIG_FIELDS = {'host', 'os', 'display_mode', 'resolution', 'cable_set',
                 'display_count', 'driver_allowed', 'driver_installed'}


def utcnow():
    return datetime.now(timezone.utc)


def timestamp(value):
    if not isinstance(value, str):
        raise ValueError('Timestamp must be text')
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if result.tzinfo is None:
        raise ValueError('Timestamp must have timezone')
    return result


def paise(value):
    try:
        amount = Decimal(str(value))
        if not amount.is_finite() or amount < 0 or amount * 100 != (amount * 100).to_integral_value():
            raise ValueError('Amount must be nonnegative with at most two decimal places')
        return int(amount * 100)
    except InvalidOperation as error:
        raise ValueError('Invalid amount') from error


def nonnegative(value, name):
    if type(value) is not int or value < 0:
        raise ValueError(f'{name} must be a nonnegative integer')


@dataclass(frozen=True)
class Definition:
    name: str
    kind: type
    meaning: str


class FeatureRegistry:
    def __init__(self):
        self.version = 1
        self.definitions = {name: Definition(name, bool, meaning) for name, meaning in {
            'built_in_wifi': 'Wi-Fi hardware is built in; no optional module required.',
            'app_control': 'An app can control the appliance, possibly with prerequisites.',
            'voice_control': 'Supports a named voice ecosystem; prerequisites must be checked.',
            'remote_access': 'Can be controlled from outside the local network.',
        }.items()}

    def validate(self, name, value):
        if name not in self.definitions:
            raise ValueError(f'Unknown feature: {name}')
        if type(value) is not self.definitions[name].kind:
            raise ValueError(f'Invalid type for feature: {name}')


class RequestModel(BaseModel):
    model_config = ConfigDict(strict=True, extra='forbid', allow_inf_nan=False)


Category = Literal['washing_machine', 'ac', 'dock']


class CompareRequest(RequestModel):
    product_ids: list[str] = Field(min_length=2, max_length=5)


class SearchRequest(RequestModel):
    query: str = Field(max_length=2000)
    category: Category | None = None


class Request(RequestModel):
    query: str = Field(default='', max_length=2000)
    category: Category | None = None
    features: dict[str, bool] = Field(default_factory=dict)
    budget_paise: int | None = Field(default=None, ge=0)
    delivery_by: str | None = None
    configuration: dict = Field(default_factory=dict)
    confirmed_prerequisites: list[str] = Field(default_factory=list)

    @classmethod
    def parse(cls, data, features_registry):
        request = cls.model_validate(data)
        for name, value in request.features.items():
            features_registry.validate(name, value)
        if request.delivery_by is not None:
            timestamp(request.delivery_by)
        if not isinstance(request.configuration, dict) or set(request.configuration) - CONFIG_FIELDS:
            raise ValueError('Invalid configuration fields')
        for key, value in request.configuration.items():
            if key in ('driver_allowed', 'driver_installed'):
                if type(value) is not bool:
                    raise ValueError(f'{key} must be boolean')
            elif key == 'display_count':
                if type(value) is not int or value < 1:
                    raise ValueError('display_count must be a positive integer')
            elif not isinstance(value, str) or not value:
                raise ValueError(f'{key} must be nonempty text')
        if request.configuration and request.category != 'dock':
            raise ValueError('Display configuration is supported only for docks')
        return request


def check_offer(product_id, offer, request, now):
    if not offer or offer.get('product_id') != product_id or offer.get('currency') != 'INR':
        return {'status': 'UNKNOWN', 'reason': 'Missing or mismatched offer'}
    if not timestamp(offer['valid_from']) <= now < timestamp(offer['expires_at']):
        return {'status': 'UNKNOWN', 'reason': 'Offer is expired or not yet valid'}
    total = offer['price_paise'] + offer['accessories_paise'] + offer['shipping_paise']
    result = dict(status='ELIGIBLE', total_paise=total, currency='INR', offer_id=offer['id'],
                  price_paise=offer['price_paise'], accessories_paise=offer['accessories_paise'],
                  shipping_paise=offer['shipping_paise'], delivery_at=offer['delivery_at'],
                  expires_at=offer['expires_at'])
    if offer['stock'] < 1:
        result.update(status='INELIGIBLE', reason='Out of stock')
    elif request.budget_paise is not None and total > request.budget_paise:
        result.update(status='INELIGIBLE', reason='Full bundle exceeds budget')
    elif request.delivery_by and timestamp(offer['delivery_at']) > timestamp(request.delivery_by):
        result.update(status='INELIGIBLE', reason='Delivery misses deadline')
    elif timestamp(offer['delivery_at']) < now:
        result.update(status='UNKNOWN', reason='Delivery quote is stale')
    elif request.configuration and offer.get('cable_set') != request.configuration.get('cable_set'):
        result.update(status='UNKNOWN', reason='Offer does not include the reviewed cable set')
    return result


def interpret(data, features_registry):
    request = Request.parse(data, features_registry)
    text = request.query.lower().strip()
    if not text:
        return request, []
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
    values = request.model_dump()
    values.update(category=category, features=features, budget_paise=budget)
    return Request.parse(values, features_registry), issues
