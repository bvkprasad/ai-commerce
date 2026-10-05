import json
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from ai_commerce.api import MAX_BODY, create_app


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(create_app())
        self.client.__enter__()
        self.addCleanup(self.client.__exit__, None, None, None)

    def test_health(self):
        response = self.client.get('/health')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['status'], 'ok')

    def test_invalid_requests(self):
        cases = [
            (b'{', 422),
            (b'[]', 422),
            (b'\xff', 400),
            (b'{"features":false}', 422),
            (b'{"purchase":true}', 422),
            (b'{"budget_paise":NaN}', 422),
            (b'{"budget_paise":true}', 422),
            (b'{"features":{"built_in_wifi":"true"}}', 422),
        ]
        for body, expected in cases:
            with self.subTest(body=body):
                response = self.client.post('/discover', content=body, headers={'Content-Type': 'application/json'})
                self.assertEqual(response.status_code, expected)
                self.assertIn('detail', response.json())

    def test_unknown_route(self):
        self.assertEqual(self.client.get('/nope').status_code, 404)

    def test_wrong_method(self):
        response = self.client.get('/discover')
        self.assertEqual(response.status_code, 405)
        self.assertIn('POST', response.headers['allow'])

    def test_wrong_content_type(self):
        self.assertEqual(self.client.post('/discover', content='{}', headers={'Content-Type': 'text/plain'}).status_code, 415)

    def test_body_limit(self):
        body = json.dumps({'query': 'a' * MAX_BODY})
        self.assertEqual(self.client.post('/discover', content=body, headers={'Content-Type': 'application/json'}).status_code, 413)

    def test_streamed_body_limit(self):
        response = self.client.post('/discover', content=iter([b' ' * MAX_BODY, b'{}']), headers={'Content-Type': 'application/json'})
        self.assertEqual(response.status_code, 413)

    def test_truncated(self):
        response = self.client.post('/discover', content='{}', headers={'Content-Type': 'application/json', 'Content-Length': '100'})
        self.assertEqual(response.status_code, 400)

    def test_discovery(self):
        response = self.client.post('/discover', json={'category': 'washing_machine', 'features': {'built_in_wifi': True}})
        self.assertEqual(response.status_code, 200)
        self.assertEqual([c['product_id'] for c in response.json()['cards']], ['wash-connect'])

    def test_dock_discovery(self):
        fixture = Path(__file__).parent.parent / 'examples/dual_monitor_dock.json'
        response = self.client.post('/discover', json=json.loads(fixture.read_text()))
        self.assertEqual(response.status_code, 200)
        self.assertEqual([c['product_id'] for c in response.json()['cards']], ['dock-d'])

    def test_invalid_feature(self):
        response = self.client.post('/discover', json={'category': 'washing_machine', 'features': {'imaginary': True}})
        self.assertEqual(response.status_code, 400)

    def test_search(self):
        response = self.client.post('/search', json={'query': 'wifi washer'})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['matches'])
        self.assertFalse(response.json()['eligibility_checked'])
        for data in [{'query': 'x', 'method': 'invalid'}, {'query': 'x', 'category': 'invalid'}, {'query': 'x', 'extra': True}]:
            with self.subTest(data=data):
                self.assertEqual(self.client.post('/search', json=data).status_code, 422)

    def test_compare(self):
        response = self.client.post('/compare', json={'product_ids': ['wash-connect', 'wash-basic']})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()['products']), 2)
        self.assertEqual(self.client.post('/compare', json={'product_ids': ['wash-connect']}).status_code, 422)
        self.assertEqual(self.client.post('/compare', json={'product_ids': ['wash-connect', 'unknown']}).status_code, 400)

    def test_documentation(self):
        self.assertEqual(self.client.get('/docs').status_code, 200)
        schema = self.client.get('/openapi.json').json()
        self.assertEqual(set(schema['paths']), {'/health', '/discover', '/compare', '/search'})
        self.assertIn('Request', schema['components']['schemas'])
        self.assertIn('SearchRequest', schema['components']['schemas'])
