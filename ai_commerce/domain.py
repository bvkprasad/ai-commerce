"""Typed requests and commerce checks. All money is integer INR paise."""
from dataclasses import dataclass, field
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
class Request:
    query: str = ''
    category: str | None = None
    features: dict = field(default_factory=dict)
    budget_paise: int | None = None
    delivery_by: str | None = None
    configuration: dict = field(default_factory=dict)
    confirmed_prerequisites: list = field(default_factory=list)

    @classmethod
    def parse(cls, data, ontology):
        if not isinstance(data, dict):
            raise ValueError('Request must be a JSON object')
        unknown = set(data) - set(cls.__dataclass_fields__)
        if unknown:
            raise ValueError('Unsupported request fields: ' + ', '.join(sorted(unknown)))
        request = cls(**data)
        if not isinstance(request.query, str) or len(request.query) > 2000:
            raise ValueError('Query must be text of at most 2000 characters')
        if request.category is not None and request.category not in CATEGORIES:
            raise ValueError('Unknown category')
        if not isinstance(request.features, dict):
            raise ValueError('Features must be an object')
        for name, value in request.features.items():
            ontology.validate(name, value)
        if request.budget_paise is not None:
            nonnegative(request.budget_paise, 'budget_paise')
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
        if not isinstance(request.confirmed_prerequisites, list) or any(
                not isinstance(x, str) for x in request.confirmed_prerequisites):
            raise ValueError('confirmed_prerequisites must be a list of names')
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
