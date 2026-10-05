from concurrent.futures import ThreadPoolExecutor
import copy
from pathlib import Path
import tempfile
import unittest

from ai_commerce.catalog import Catalog, load_catalog
from ai_commerce.service import CommerceService


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.catalog = load_catalog()
        self.addCleanup(self.catalog.close)

    def test_database_is_source_of_truth(self):
        product = self.catalog.product('wash-connect')
        product['title'] = 'Uncommitted change'
        self.assertNotEqual(self.catalog.product('wash-connect')['title'], product['title'])
        self.catalog.update('products', 'wash-connect', title='Committed title')
        self.assertEqual(self.catalog.product('wash-connect')['title'], 'Committed title')

    def test_invalid_update_is_atomic(self):
        before = self.catalog.db.export()
        with self.assertRaises(ValueError):
            self.catalog.update('offers', 'wash-connect', stock=-1)
        self.assertEqual(self.catalog.db.export(), before)
        wrong = copy.deepcopy(self.catalog.product('wash-connect')['facts'])
        wrong[0]['evidence'] = ['wash-basic-manual-v1']
        with self.assertRaises(ValueError):
            self.catalog.update('products', 'wash-connect', facts=wrong)
        self.assertEqual(self.catalog.db.export(), before)

    def test_database_foreign_keys(self):
        enabled = self.catalog.db.connection.execute('PRAGMA foreign_keys').fetchone()[0]
        self.assertEqual(enabled, 1)

    def test_in_memory_instances_are_isolated(self):
        other = load_catalog()
        self.addCleanup(other.close)
        original_stock = other.offer('wash-connect')['stock']
        self.catalog.update('offers', 'wash-connect', stock=0)
        self.assertEqual(other.offer('wash-connect')['stock'], original_stock)

    def test_database_round_trip_preserves_quotes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'catalog.sqlite3'
            self.catalog.db.save(path)
            loaded = load_catalog(path)
            self.addCleanup(loaded.close)
            self.assertEqual(loaded.db.export(), self.catalog.db.export())

    def test_withdrawn_source_disappears_from_search(self):
        source_id = 'wash-connect-manual-v1'
        self.catalog.update('sources', source_id, active=False)
        self.assertFalse(any(match['source_id'] == source_id for match in self.catalog.search('wifi washing machine')))

    def test_concurrent_api_workers_can_read_sqlite(self):
        service = CommerceService(self.catalog)
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda _: service.discover({'category': 'washing_machine', 'features': {'built_in_wifi': True}}), range(12)))
        for result in results:
            self.assertEqual([card['product_id'] for card in result['cards']], ['wash-connect'])

    def test_category_query_and_parameterized_lookup(self):
        self.assertTrue(all(product['category'] == 'dock' for product in self.catalog.products('dock')))
        self.assertIsNone(self.catalog.product("' OR 1=1 --"))

    def test_sqlite_search_handles_empty_and_operator_inputs(self):
        self.assertEqual(self.catalog.search(''), [])
        self.assertEqual(self.catalog.search('" * ( )'), [])
        for query in ['wifi OR "washer"', 'wifi; DROP TABLE products;', 'Wi-Fi']:
            with self.subTest(query=query):
                matches = self.catalog.search(query, 'washing_machine')
                self.assertTrue(matches)
                self.assertTrue(all(self.catalog.product(match['product_id'])['category'] == 'washing_machine' for match in matches))
        self.assertEqual(len(self.catalog.products()), 12)
