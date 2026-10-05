"""Read products from SQLite and resolve evidence into verified answers."""
from datetime import timedelta
from pathlib import Path

from .request import FeatureRegistry, utcnow
from .storage import CatalogData, Database, read_database


class Catalog:
    def __init__(self, data, features=None):
        self.features = features or FeatureRegistry()
        self.db = Database()
        try:
            self.replace(data)
        except Exception:
            self.db.close()
            raise

    def replace(self, data):
        """Validate and commit a release with its search index atomically."""
        release = CatalogData.model_validate(data)
        release.validate_references(self.features)
        data = release.model_dump(exclude_none=True)
        self.db.replace(data)

    def products(self, category=None):
        return self.db.records('products', category)

    def product(self, product_id):
        return self.db.get('products', product_id)

    def source(self, source_id):
        return self.db.get('sources', source_id)

    def offer(self, product_id):
        return self.db.get('offers', product_id)

    def sources(self):
        return {row['id']: row for row in self.db.records('sources')}

    def update(self, table, record_id, **changes):
        """Update a database record, validate references, and refresh search."""
        if table not in ('products', 'sources', 'offers'):
            raise ValueError('Unknown catalog table')
        with self.db.lock:
            data = self.db.export()
            key = 'product_id' if table == 'offers' else 'id'
            record = next((row for row in data[table] if row[key] == record_id), None)
            if record is None:
                raise ValueError('Unknown catalog record')
            record.update(changes)
            self.replace(data)

    def delete_offer(self, product_id):
        with self.db.lock:
            data = self.db.export()
            data['offers'] = [row for row in data['offers'] if row['product_id'] != product_id]
            self.replace(data)

    def search(self, query, category=None, limit=20):
        return self.db.search(query, category, limit)

    def evidence_active(self, source_ids):
        """Every cited source must exist, be reviewed, and remain active."""
        sources = [self.source(source_id) for source_id in source_ids]
        return bool(sources) and all(source and source['reviewed'] and source['active'] for source in sources)

    def verified_feature(self, product, name):
        """Unknown unless reviewed facts agree on both value and prerequisites."""
        facts = [fact for fact in product['facts'] if fact['name'] == name and self.evidence_active(fact['evidence'])]
        if not facts:
            return {'status': 'UNKNOWN', 'value': None, 'evidence': []}
        first = facts[0]
        if any(fact['value'] != first['value'] or set(fact['prerequisites']) != set(first['prerequisites']) for fact in facts):
            return {'status': 'UNKNOWN', 'value': None, 'evidence': []}
        return {'status': 'VERIFIED', 'value': first['value'], 'prerequisites': first['prerequisites'],
                'evidence': sorted({source_id for fact in facts for source_id in fact['evidence']})}

    def compatibility(self, product, configuration):
        """Match an exact reviewed configuration, then check displays and drivers."""
        keys = ('host', 'os', 'display_mode', 'resolution', 'cable_set')
        if not set((*keys, 'display_count', 'driver_allowed')).issubset(configuration):
            return {'status': 'UNKNOWN', 'reason': 'Exact host, OS and display configuration required', 'evidence': []}
        matches = [record for record in product['assessments']
                   if all(record[key] == configuration[key] for key in keys) and self.evidence_active(record['evidence'])]
        if not matches:
            return {'status': 'UNKNOWN', 'reason': 'No exact reviewed assessment', 'evidence': []}
        if len({(record['display_count'], record['driver_required']) for record in matches}) != 1:
            return {'status': 'UNKNOWN', 'reason': 'Conflicting assessments', 'evidence': []}
        assessment = matches[0]
        status, reason = 'SUPPORTED', 'Exact reviewed configuration matches'
        if assessment['display_count'] < configuration['display_count']:
            status, reason = 'UNSUPPORTED', 'Insufficient independent displays'
        elif assessment['driver_required'] and not configuration['driver_allowed']:
            status, reason = 'UNSUPPORTED', 'Required driver is forbidden'
        elif assessment['driver_required'] and not configuration.get('driver_installed'):
            status, reason = 'CONDITIONAL', 'Required driver installation is unconfirmed'
        return {'status': status, 'reason': reason,
                'evidence': sorted({source_id for record in matches for source_id in record['evidence']})}

    def close(self):
        self.db.close()


def load_catalog(path=None, now=None):
    data = read_database(path or Path(__file__).parent / 'data' / 'catalog.sqlite3')
    if path is None:
        now = now or utcnow()
        for offer in data['offers']:
            offer.update(valid_from=now.isoformat(), expires_at=(now + timedelta(minutes=30)).isoformat(),
                         delivery_at=(now + timedelta(hours=20)).isoformat())
    return Catalog(data)
