import json
import os
import unittest
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient

from ai_commerce.api import create_app
from ai_commerce.catalog import load_catalog
from ai_commerce.llm import Configuration, Intent, LLMUnavailable, OpenRouter
from ai_commerce.service import CommerceService


def extracted(**changes):
    result = {
        'category': 'washing_machine', 'features': [{'name': 'built_in_wifi', 'value': True}],
        'budget_paise': 4000000, 'delivery_by': None,
        'configuration': {name: None for name in Configuration.model_fields}, 'questions': [],
    }
    result.update(changes)
    return result


class LLMTests(unittest.TestCase):
    def setUp(self):
        self.catalog = load_catalog()
        self.addCleanup(self.catalog.close)

    def interpreter(self, result=None, status=200, raw=None):
        def completion(request):
            self.assertEqual(request.url.path, '/api/v1/chat/completions')
            payload = json.loads(request.content)
            self.assertEqual(payload['response_format']['type'], 'json_schema')
            self.assertTrue(payload['provider']['require_parameters'])
            self.assertEqual(payload['temperature'], 0)
            body = raw if raw is not None else {'choices': [{'finish_reason': 'stop', 'message': {'content': json.dumps(result)}}]}
            return httpx.Response(status, json=body)
        client = httpx.Client(base_url='https://openrouter.ai/api/v1/', transport=httpx.MockTransport(completion))
        router = OpenRouter('test-only', 'test/model', client)
        self.addCleanup(router.close)
        return router

    def test_query_to_verified_discovery(self):
        router = self.interpreter(extracted())
        service = CommerceService(self.catalog, interpreter=router)
        with TestClient(create_app(service)) as client:
            response = client.post('/discover', json={'query': 'I need a washer I can connect to Wi-Fi, below forty thousand rupees.'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual([card['product_id'] for card in response.json()['cards']], ['wash-connect'])
        self.assertEqual(response.json()['interpreted_request']['budget_paise'], 4000000)

    def test_unsupported_requirement_returns_clarification(self):
        router = self.interpreter(extracted(questions=['Which noise level do you require? Quiet operation is not in the catalog.']))
        result = CommerceService(self.catalog, interpreter=router).discover({'query': 'a quiet Wi-Fi washer'})
        self.assertEqual(result['status'], 'CLARIFICATION')
        self.assertEqual(result['cards'], [])

    def test_structured_constraints_are_not_relaxed(self):
        router = self.interpreter(extracted())
        request, questions = router.interpret({'query': 'wifi washer under 40000', 'features': {'built_in_wifi': False}, 'budget_paise': 1000000}, self.catalog.features)
        self.assertFalse(request.features['built_in_wifi'])
        self.assertEqual(request.budget_paise, 1000000)
        self.assertEqual(len(questions), 2)

    def test_model_cannot_confirm_prerequisites(self):
        router = self.interpreter(extracted(category='ac', budget_paise=None, features=[{'name': 'app_control', 'value': True}]))
        result = CommerceService(self.catalog, interpreter=router).discover({'query': 'an AC controlled with a phone'})
        self.assertEqual([card['product_id'] for card in result['cards']], ['ac-connect'])
        forged = extracted(confirmed_prerequisites=['external_bridge'])
        with self.assertRaises(LLMUnavailable):
            self.interpreter(forged).interpret({'query': 'AC'}, self.catalog.features)

    def test_structured_requests_do_not_call_provider(self):
        router = self.interpreter(status=500)
        result = CommerceService(self.catalog, interpreter=router).discover({'category': 'washing_machine', 'features': {'built_in_wifi': True}})
        self.assertEqual(result['status'], 'OK')

    def test_invalid_provider_output_is_rejected(self):
        cases = [extracted(features=[{'name': 'magic', 'value': True}]), extracted(budget_paise=True), extracted(features=[{'name': 'built_in_wifi', 'value': 'true'}]), extracted(delivery_by='tomorrow'), extracted(features=[{'name': 'built_in_wifi', 'value': True}] * 2)]
        for output in cases:
            with self.subTest(output=output), self.assertRaises(LLMUnavailable):
                self.interpreter(output).interpret({'query': 'washer'}, self.catalog.features)

    def test_provider_errors_have_safe_http_response(self):
        service = CommerceService(self.catalog, interpreter=self.interpreter(status=429, raw={'error': {'message': 'private provider detail'}}))
        with TestClient(create_app(service)) as client:
            response = client.post('/discover', json={'query': 'washer'})
            structured = client.post('/discover', json={'category': 'washing_machine'})
        self.assertEqual(response.status_code, 502)
        self.assertNotIn('private', response.text)
        self.assertEqual(structured.status_code, 200)

    def test_timeout_and_malformed_response(self):
        def timeout(request):
            raise httpx.ReadTimeout('private detail', request=request)
        client = httpx.Client(base_url='https://openrouter.ai/api/v1/', transport=httpx.MockTransport(timeout))
        router = OpenRouter('test-only', 'test/model', client)
        self.addCleanup(router.close)
        with self.assertRaises(LLMUnavailable):
            router.interpret({'query': 'washer'}, self.catalog.features)
        for raw in [{}, {'choices': []}, {'choices': [{'finish_reason': 'length', 'message': {'content': '{}'}}]}, {'choices': [{'finish_reason': 'stop', 'message': {'content': 'invalid JSON'}}]}]:
            with self.subTest(raw=raw), self.assertRaises(LLMUnavailable):
                self.interpreter(raw=raw).interpret({'query': 'washer'}, self.catalog.features)

    def test_schema_fields_are_required(self):
        schema = Intent.model_json_schema()
        self.assertEqual(set(schema['required']), set(schema['properties']))
        for definition in schema['$defs'].values():
            if definition.get('type') == 'object':
                self.assertEqual(set(definition['required']), set(definition['properties']))
                self.assertFalse(definition['additionalProperties'])

    def test_no_key_uses_local_rules(self):
        with patch.dict(os.environ, {'OPENROUTER_API_KEY': '', 'OPENROUTER_MODEL': ''}):
            self.assertIsNone(OpenRouter.from_env())

    def test_missing_model_is_a_configuration_error(self):
        with patch.dict(os.environ, {'OPENROUTER_API_KEY': 'test-only', 'OPENROUTER_MODEL': ''}):
            with self.assertRaises(ValueError):
                OpenRouter.from_env()

    def test_negative_requirement_is_preserved(self):
        router = self.interpreter(extracted(features=[{'name': 'built_in_wifi', 'value': False}], budget_paise=None))
        result = CommerceService(self.catalog, interpreter=router).discover({'query': 'a washer without built-in Wi-Fi'})
        self.assertEqual({card['product_id'] for card in result['cards']}, {'wash-basic', 'wash-addon'})

    def test_dock_driver_confirmation_and_exact_configuration(self):
        configuration = {**{name: None for name in Configuration.model_fields},
                         'host': 'L42-r2', 'os': 'ExampleOS-1', 'display_mode': 'extended',
                         'resolution': '1080p60', 'cable_set': 'reviewed-dual-hdmi',
                         'display_count': 2, 'driver_allowed': True}
        router = self.interpreter(extracted(category='dock', features=[], budget_paise=1000000, configuration=configuration))
        result = CommerceService(self.catalog, interpreter=router).discover({'query': 'dock for two screens; drivers are allowed'})
        self.assertEqual([card['product_id'] for card in result['cards']], ['dock-d'])
        dock_b = next(product for product in result['excluded'] if product['product_id'] == 'dock-b')
        self.assertEqual(dock_b['compatibility']['status'], 'CONDITIONAL')
