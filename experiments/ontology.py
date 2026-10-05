"""In-memory schema migration demo, separate from request handling."""
from dataclasses import dataclass
from ai_commerce.request import Definition, FeatureRegistry


@dataclass(frozen=True)
class Proposal:
    base_version: int
    definition: Definition
    reviewer: str = ''


class Ontology(FeatureRegistry):
    def approve(self, proposal):
        if not proposal.reviewer.strip():
            raise ValueError('Explicit named review is required')
        if proposal.base_version != self.version:
            raise ValueError('Stale proposal')
        definition = proposal.definition
        if definition.name in self.definitions:
            raise ValueError('Cannot overwrite existing semantics')
        if definition.kind not in (bool, int, str) or not definition.name or not definition.meaning:
            raise ValueError('Invalid definition')
        self.definitions[definition.name] = definition
        self.version += 1


def demo():
    from ai_commerce.catalog import Catalog, load_catalog
    ontology = Ontology()
    original = load_catalog()
    data = original.db.export()
    original.close()
    ontology.approve(Proposal(1, Definition('energy_metering', bool,
        'Reports measured energy consumption in the app.'), 'Demo reviewer'))
    data['ontology_version'] = ontology.version
    # Existing feature meanings are unchanged; explicitly migrate their version tags.
    for product in data['products']:
        for fact in product['facts']:
            fact['ontology_version'] = ontology.version
    sid = 'wash-connect-energy-demo-v2'
    data['sources'].append(dict(id=sid, product_id='wash-connect',
        text='The Connect washing machine reports measured energy consumption in its app.',
        locator='synthetic://' + sid, publisher='Fictional demo reviewer', version='2',
        reviewed=True, active=True))
    product = next(p for p in data['products'] if p['id'] == 'wash-connect')
    product['source_ids'].append(sid)
    product['facts'].append(dict(name='energy_metering', value=True,
        evidence=[sid], prerequisites=[], ontology_version=ontology.version))
    catalog = Catalog(data, features=ontology)
    verified = [product['id'] for product in catalog.products()
                if catalog.verified_feature(product, 'energy_metering')['value'] is True]
    result = {'version': ontology.version, 'reviewer': 'Demo reviewer', 'persistent': False,
            'backfilled_products': verified, 'evidence': catalog.source(sid),
            'regression': {'wifi_value_preserved': catalog.verified_feature(
                catalog.product('wash-connect'), 'built_in_wifi')['value'] is True},
            'retrieval': catalog.search('measured energy consumption')}

    catalog.close()
    return result
