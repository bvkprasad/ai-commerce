import io
import json
import unittest
from ai_commerce.api import create_app, MAX_BODY


class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.app=staticmethod(create_app())

    def request(self,path='/discover',body=b'{}',method='POST',content_type='application/json',length=None):
        status=[]
        result=self.app({'PATH_INFO':path,'REQUEST_METHOD':method,'CONTENT_TYPE':content_type,
                         'CONTENT_LENGTH':str(len(body) if length is None else length),'wsgi.input':io.BytesIO(body)},
                        lambda code,headers:status.append(code))
        return status[0],json.loads(b''.join(result))

    def test_health(self): self.assertEqual(self.request('/health',method='GET')[0],'200 OK')
    def test_invalid_json(self): self.assertEqual(self.request(body=b'{')[0],'400 Bad Request')
    def test_non_object(self): self.assertEqual(self.request(body=b'[]')[0],'400 Bad Request')
    def test_unknown_route(self): self.assertEqual(self.request('/nope')[0],'404 Not Found')
    def test_wrong_method(self): self.assertEqual(self.request(method='GET')[0],'405 Method Not Allowed')
    def test_wrong_content_type(self): self.assertEqual(self.request(content_type='text/plain')[0],'415 Unsupported Media Type')
    def test_body_limit(self): self.assertEqual(self.request(length=MAX_BODY+1)[0],'413 Payload Too Large')
    def test_truncated(self): self.assertEqual(self.request(length=100)[0],'400 Bad Request')
    def test_invalid_utf8(self): self.assertEqual(self.request(body=b'\xff')[0],'400 Bad Request')
    def test_bad_type(self): self.assertEqual(self.request(body=b'{"features":false}')[0],'400 Bad Request')
    def test_unsupported_field(self): self.assertEqual(self.request(body=b'{"purchase":true}')[0],'400 Bad Request')
    def test_discovery(self):
        status,result=self.request(body=b'{"category":"washing_machine","features":{"built_in_wifi":true}}')
        self.assertEqual(status,'200 OK')
        self.assertEqual([c['product_id'] for c in result['cards']],['wash-connect'])
