"""Evidence graph and conservative, configuration-specific eligibility."""
from collections import defaultdict


class EvidenceGraph:
    def __init__(self, products, sources):
        self.sources = sources
        self.nodes = {}
        self.edges = defaultdict(list)
        for sid, source in sources.items():
            self.nodes['source:' + sid] = source
        for pid, product in products.items():
            root = 'product:' + pid
            self.nodes[root] = product
            for sid in product['source_ids']:
                self.edges[root].append(('DESCRIBED_BY', 'source:' + sid))
            for kind, relation in [('facts', 'HAS_FEATURE'), ('assessments', 'HAS_ASSESSMENT')]:
                for index, record in enumerate(product[kind]):
                    key = f'{kind}:{pid}:{index}'
                    self.nodes[key] = record
                    self.edges[root].append((relation, key))
                    for sid in record['evidence']:
                        self.edges[key].append(('SUPPORTED_BY', 'source:' + sid))

    def active(self, evidence):
        return bool(evidence) and all(self.sources[sid]['reviewed'] and
                                     self.sources[sid]['active'] for sid in evidence)

    def feature(self, product, name):
        facts = [f for f in product['facts'] if f['name'] == name and self.active(f['evidence'])]
        if not facts or any(f['value'] != facts[0]['value'] or
                            f.get('prerequisites', []) != facts[0].get('prerequisites', [])
                            for f in facts):
            return {'status': 'UNKNOWN', 'value': None, 'evidence': []}
        return {'status': 'VERIFIED', 'value': facts[0]['value'],
                'evidence': sorted({sid for f in facts for sid in f['evidence']}),
                'prerequisites': facts[0].get('prerequisites', [])}

    def compatibility(self, product, config):
        keys = ('host', 'os', 'display_mode', 'resolution', 'cable_set')
        if any(key not in config for key in (*keys, 'display_count', 'driver_allowed')):
            return {'status': 'UNKNOWN', 'reason': 'Exact host, OS and display configuration required', 'evidence': []}
        records = [a for a in product['assessments'] if self.active(a['evidence']) and
                   all(a[key] == config[key] for key in keys)]
        if not records:
            return {'status': 'UNKNOWN', 'reason': 'No exact reviewed assessment', 'evidence': []}
        if len({(a['display_count'], a['driver_required']) for a in records}) != 1:
            return {'status': 'UNKNOWN', 'reason': 'Conflicting assessments', 'evidence': []}
        assessment = records[0]
        result = {'status': 'SUPPORTED', 'reason': 'Exact reviewed configuration matches',
                  'evidence': sorted({sid for a in records for sid in a['evidence']})}
        if assessment['display_count'] < config['display_count']:
            result.update(status='UNSUPPORTED', reason='Insufficient independent displays')
        elif assessment['driver_required'] and config['driver_allowed'] is False:
            result.update(status='UNSUPPORTED', reason='Required driver is forbidden')
        elif assessment['driver_required'] and config.get('driver_installed') is not True:
            result.update(status='CONDITIONAL', reason='Required driver installation is unconfirmed')
        return result
