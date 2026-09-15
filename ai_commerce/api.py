"""Local-only WSGI JSON interface. No identity, auth, orders or live commerce."""
import json
from wsgiref.simple_server import make_server
from .ingestion import load_catalog
from .service import CommerceService

MAX_BODY = 16384


def create_app(service=None):
    service = service or CommerceService(load_catalog())

    def app(environ, start_response):
        status, result = '200 OK', {}
        try:
            path, method = environ.get('PATH_INFO', ''), environ.get('REQUEST_METHOD', '')
            if path == '/health' and method == 'GET':
                result = {'status': 'ok', 'synthetic': True}
            elif path not in ('/discover', '/compare', '/search'):
                status, result = '404 Not Found', {'error': 'Unknown route'}
            elif method != 'POST':
                status, result = '405 Method Not Allowed', {'error': 'POST required'}
            elif environ.get('CONTENT_TYPE', '').split(';')[0].strip() != 'application/json':
                status, result = '415 Unsupported Media Type', {'error': 'application/json required'}
            elif environ.get('HTTP_TRANSFER_ENCODING'):
                status, result = '400 Bad Request', {'error': 'Transfer encoding unsupported'}
            else:
                size = int(environ.get('CONTENT_LENGTH', ''))
                if size < 0:
                    raise ValueError('Negative content length')
                if size > MAX_BODY:
                    status, result = '413 Payload Too Large', {'error': 'Request exceeds 16 KiB'}
                else:
                    raw = environ['wsgi.input'].read(size)
                    if len(raw) != size:
                        raise ValueError('Truncated body')
                    data = json.loads(raw.decode('utf-8'), parse_constant=lambda x: (_ for _ in ()).throw(ValueError('Nonfinite JSON')))
                    if not isinstance(data, dict):
                        raise ValueError('JSON object required')
                    if path == '/discover':
                        result = service.discover(data)
                    elif path == '/compare':
                        if set(data) != {'product_ids'}:
                            raise ValueError('Expected product_ids only')
                        result = service.compare(data['product_ids'])
                    else:
                        if set(data) - {'query', 'category', 'method'} or not isinstance(data.get('query'), str) or len(data['query']) > 2000:
                            raise ValueError('Invalid search request')
                        from .domain import CATEGORIES
                        if data.get('category') is not None and data['category'] not in CATEGORIES:
                            raise ValueError('Unknown category')
                        result = {'matches': service.catalog.search(**data), 'eligibility_checked': False}
        except (ValueError, TypeError, KeyError, UnicodeError) as error:
            status, result = '400 Bad Request', {'error': str(error)}
        payload = json.dumps(result, allow_nan=False).encode('utf-8')
        headers = [('Content-Type', 'application/json; charset=utf-8'), ('Content-Length', str(len(payload)))]
        if status.startswith('405'):
            headers.append(('Allow', 'POST'))
        start_response(status, headers)
        return [payload]
    return app


def serve(port=8000, host='127.0.0.1'):
    with make_server(host, port, create_app()) as server:
        print(f'Local synthetic API at http://{host}:{port}', flush=True)
        server.serve_forever()
