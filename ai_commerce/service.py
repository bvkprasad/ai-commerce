"""Relevance, evidence eligibility and purchasability are separate decisions."""
from dataclasses import asdict
from .domain import Request, check_offer, utcnow
from .intent import interpret


class CommerceService:
    def __init__(self, catalog, clock=utcnow):
        self.catalog, self.clock = catalog, clock

    def discover(self, data):
        request, questions = interpret(data, self.catalog.ontology)
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
        for pid, product in self.catalog.products.items():
            if product['category'] != request.category:
                continue
            facts = {name: self.catalog.graph.feature(product, name) for name in request.features}
            reasons = []
            for name, required in request.features.items():
                fact = facts[name]
                if fact['status'] != 'VERIFIED':
                    reasons.append(f'{name}: UNKNOWN')
                elif fact['value'] != required:
                    reasons.append(f'{name}: verified requirement fails')
                elif required is True and set(fact.get('prerequisites', [])) - set(request.confirmed_prerequisites):
                    reasons.append(f'{name}: prerequisites unconfirmed')
            compatibility = self.catalog.graph.compatibility(product, request.configuration) if request.category == 'dock' else None
            if compatibility and compatibility['status'] != 'SUPPORTED':
                reasons.append('Compatibility: ' + compatibility['status'] + ': ' + compatibility['reason'])
            commerce = check_offer(pid, self.catalog.offers.get(pid), request, now)
            if commerce['status'] != 'ELIGIBLE':
                reasons.append('Commerce: ' + commerce['status'] + ': ' + commerce['reason'])
            if reasons:
                excluded.append({'product_id': pid, 'reasons': reasons, 'features': facts,
                                 'compatibility': compatibility, 'commerce': commerce})
                continue
            citations = sorted({sid for fact in facts.values() for sid in fact['evidence']} |
                               set(compatibility['evidence'] if compatibility else []))
            card = {'product_id': pid, 'title': product['title'], 'features': facts,
                    'compatibility': compatibility, 'commerce': commerce,
                    'evidence': {sid: self.catalog.sources[sid] for sid in citations},
                    'relevance': relevance.get(pid), 'synthetic': True}
            card['explanation'] = self.render(card)
            self.validate_card(card, request, now)
            cards.append(card)
        cards.sort(key=lambda card: (-(card['relevance'] or {}).get('score', 0),
                                     card['commerce']['total_paise'], card['product_id']))
        return {'status': 'OK', 'cards': cards, 'excluded': excluded,
                'interpreted_request': asdict(request), 'synthetic': True}

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
        product = self.catalog.products[card['product_id']]
        if card['title'] != product['title']:
            raise ValueError('Ungrounded title')
        expected = check_offer(product['id'], self.catalog.offers.get(product['id']), request, now)
        if card['commerce'] != expected or expected['status'] != 'ELIGIBLE':
            raise ValueError('Ungrounded commerce data')
        for name, value in request.features.items():
            fact = self.catalog.graph.feature(product, name)
            if card['features'].get(name) != fact or fact['status'] != 'VERIFIED' or fact['value'] != value:
                raise ValueError('Ungrounded feature claim')
        if set(card['features']) != set(request.features):
            raise ValueError('Unexpected feature claim')
        if request.category == 'dock':
            if card['compatibility'] != self.catalog.graph.compatibility(product, request.configuration):
                raise ValueError('Ungrounded compatibility claim')
        expected_citations = {sid for fact in card['features'].values() for sid in fact['evidence']}
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
        for sid, source in card['evidence'].items():
            if source != self.catalog.sources.get(sid) or not self.catalog.graph.active([sid]):
                raise ValueError('Invalid citation')
        if card['explanation'] != self.render(card):
            raise ValueError('Explanation does not match approved facts')

    def compare(self, product_ids):
        if not isinstance(product_ids, list) or not 2 <= len(product_ids) <= 5 or any(
                not isinstance(pid, str) or pid not in self.catalog.products for pid in product_ids):
            raise ValueError('Provide 2 to 5 known product IDs')
        if len(set(product_ids)) != len(product_ids):
            raise ValueError('Comparison IDs must be distinct')
        now = self.clock()
        return {'synthetic': True, 'products': [
            {'product_id': pid, 'title': self.catalog.products[pid]['title'],
             'features': {name: self.catalog.graph.feature(self.catalog.products[pid], name)
                          for name in self.catalog.ontology.definitions},
             'commerce': check_offer(pid, self.catalog.offers.get(pid), Request(), now)}
            for pid in product_ids],
            'sources': self.catalog.sources}
