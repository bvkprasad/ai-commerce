"""Relevance, evidence eligibility and purchasability are separate decisions."""
from .request import Request, check_offer, interpret, utcnow


class CommerceService:
    def __init__(self, catalog, clock=utcnow, interpreter=None):
        self.catalog, self.clock = catalog, clock
        self.interpreter = interpreter

    def discover(self, data):
        parse = self.interpreter.interpret if self.interpreter else interpret
        request, questions = parse(data, self.catalog.features)
        if request.category is None:
            questions.append('Choose washing_machine, ac, or dock.')
        if request.category == 'dock':
            missing = [k for k in ('host', 'os', 'display_mode', 'resolution', 'cable_set',
                                  'display_count', 'driver_allowed') if k not in request.configuration]
            if missing:
                questions.append('Supply exact configuration: ' + ', '.join(missing))
        if questions:
            return {'status': 'CLARIFICATION', 'questions': questions, 'original_request': data, 'cards': []}
        now = self.clock()
        retrieval = self.catalog.search(request.query, request.category)
        relevance = {}
        for match in retrieval:
            relevance.setdefault(match['product_id'], match)
        cards, excluded = [], []
        # Full category enumeration keeps a retrieval cutoff from dropping an eligible
        # structured match. This is practical only for this small educational catalog.
        for product in self.catalog.products(request.category):
            product_id = product['id']
            facts = {name: self.catalog.verified_feature(product, name) for name in request.features}
            reasons = []
            for name, required in request.features.items():
                fact = facts[name]
                if fact['status'] != 'VERIFIED':
                    reasons.append(f'{name}: UNKNOWN')
                elif fact['value'] != required:
                    reasons.append(f'{name}: verified requirement fails')
                elif required is True and set(fact.get('prerequisites', [])) - set(request.confirmed_prerequisites):
                    reasons.append(f'{name}: prerequisites unconfirmed')
            compatibility = self.catalog.compatibility(product, request.configuration) if request.category == 'dock' else None
            if compatibility and compatibility['status'] != 'SUPPORTED':
                reasons.append('Compatibility: ' + compatibility['status'] + ': ' + compatibility['reason'])
            commerce = check_offer(product_id, self.catalog.offer(product_id), request, now)
            if commerce['status'] != 'ELIGIBLE':
                reasons.append('Commerce: ' + commerce['status'] + ': ' + commerce['reason'])
            if reasons:
                excluded.append({'product_id': product_id, 'reasons': reasons, 'features': facts,
                                 'compatibility': compatibility, 'commerce': commerce})
                continue
            citations = sorted({source_id for fact in facts.values() for source_id in fact['evidence']} |
                               set(compatibility['evidence'] if compatibility else []))
            card = {'product_id': product_id, 'title': product['title'], 'features': facts,
                    'compatibility': compatibility, 'commerce': commerce,
                    'evidence': {source_id: self.catalog.source(source_id) for source_id in citations},
                    'relevance': relevance.get(product_id), 'synthetic': True}
            card['explanation'] = self.render(card)
            self.validate_card(card, request, now)
            cards.append(card)
        cards.sort(key=lambda card: (-(card['relevance'] or {}).get('score', 0),
                                     card['commerce']['total_paise'], card['product_id']))
        return {'status': 'OK', 'cards': cards, 'excluded': excluded,
                'interpreted_request': request.model_dump(), 'synthetic': True}

    @staticmethod
    def render(card):
        total = card['commerce']['total_paise']
        claims = [f"{name}={fact['value']} [{', '.join(fact['evidence'])}]"
                  for name, fact in sorted(card['features'].items())]
        if card['compatibility']:
            claims.append('Reviewed configuration supported [' + ', '.join(card['compatibility']['evidence']) + ']')
        return (f"{card['title']}: INR {total // 100:,}.{total % 100:02d} including required accessories and shipping. "
                + '; '.join(claims) + ' (Fictional product and offer.)')

    def validate_card(self, card, request, now):
        product = self.catalog.product(card['product_id'])
        if card['title'] != product['title']:
            raise ValueError('Ungrounded title')
        expected = check_offer(product['id'], self.catalog.offer(product['id']), request, now)
        if card['commerce'] != expected or expected['status'] != 'ELIGIBLE':
            raise ValueError('Ungrounded commerce data')
        for name, value in request.features.items():
            fact = self.catalog.verified_feature(product, name)
            if card['features'].get(name) != fact or fact['status'] != 'VERIFIED' or fact['value'] != value:
                raise ValueError('Ungrounded feature claim')
        if set(card['features']) != set(request.features):
            raise ValueError('Unexpected feature claim')
        if request.category == 'dock':
            if card['compatibility'] != self.catalog.compatibility(product, request.configuration):
                raise ValueError('Ungrounded compatibility claim')
        expected_citations = {source_id for fact in card['features'].values() for source_id in fact['evidence']}
        if card['compatibility']:
            if card['compatibility']['status'] != 'SUPPORTED':
                raise ValueError('Compatibility has not passed')
            expected_citations.update(card['compatibility']['evidence'])
        elif request.category == 'dock':
            raise ValueError('Missing compatibility result')
        if set(card['evidence']) != expected_citations:
            raise ValueError('Missing or extra citations')
        if any(set(f.get('prerequisites', [])) - set(request.confirmed_prerequisites)
               for f in card['features'].values() if f['value'] is True):
            raise ValueError('Unconfirmed prerequisites')
        for source_id, source in card['evidence'].items():
            if source != self.catalog.source(source_id) or not self.catalog.evidence_active([source_id]):
                raise ValueError('Invalid citation')
        if card['explanation'] != self.render(card):
            raise ValueError('Explanation does not match approved facts')

    def compare(self, product_ids):
        if not isinstance(product_ids, list) or not 2 <= len(product_ids) <= 5 or any(
                not isinstance(product_id, str) or self.catalog.product(product_id) is None for product_id in product_ids):
            raise ValueError('Provide 2 to 5 known product IDs')
        if len(set(product_ids)) != len(product_ids):
            raise ValueError('Comparison IDs must be distinct')
        now = self.clock()
        return {'synthetic': True, 'products': [
            {'product_id': product_id, 'title': self.catalog.product(product_id)['title'],
             'features': {name: self.catalog.verified_feature(self.catalog.product(product_id), name)
                          for name in self.catalog.features.definitions},
             'commerce': check_offer(product_id, self.catalog.offer(product_id), Request(), now)}
            for product_id in product_ids],
            'sources': self.catalog.sources()}
