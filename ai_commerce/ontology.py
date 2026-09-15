"""Explicit in-memory schema evolution. Reviewer names are demo metadata, not auth."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Definition:
    name: str
    kind: type
    meaning: str


@dataclass(frozen=True)
class Proposal:
    base_version: int
    definition: Definition
    reviewer: str = ''


class Ontology:
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
    import json
    from pathlib import Path
    from .ingestion import Catalog
    ontology = Ontology()
    data = json.loads((Path(__file__).parent / 'data' / 'catalog.json').read_text())
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
    catalog = Catalog(data, ontology=ontology)
    verified = [pid for pid, p in catalog.products.items()
                if catalog.graph.feature(p, 'energy_metering')['value'] is True]
    return {'version': ontology.version, 'reviewer': 'Demo reviewer', 'persistent': False,
            'backfilled_products': verified, 'evidence': catalog.sources[sid],
            'regression': {'wifi_value_preserved': catalog.graph.feature(
                catalog.products['wash-connect'], 'built_in_wifi')['value'] is True},
            'retrieval': catalog.search('measured energy consumption')}
