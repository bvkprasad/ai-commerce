"""FastAPI routes for product discovery, comparison, and search."""
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request as HttpRequest
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from .catalog import load_catalog
from .llm import LLMUnavailable, OpenRouter
from .request import CompareRequest, Request, SearchRequest
from .service import CommerceService

MAX_BODY = 16384


def create_app(service=None):
    @asynccontextmanager
    async def lifespan(app):
        if service is not None:
            app.state.service = service
            yield
            return
        interpreter = OpenRouter.from_env()
        catalog = None
        try:
            catalog = load_catalog()
            app.state.service = CommerceService(catalog, interpreter=interpreter)
            yield
        finally:
            if catalog is not None:
                catalog.close()
            if interpreter is not None:
                interpreter.close()

    app = FastAPI(title='AI Commerce', version='0.1.0', lifespan=lifespan)

    @app.middleware('http')
    async def check_body(request: HttpRequest, call_next):
        if request.method == 'POST':
            content_type = request.headers.get('content-type', '').split(';')[0].strip()
            if content_type != 'application/json':
                return JSONResponse({'detail': 'application/json required'}, status_code=415)
            length = request.headers.get('content-length')
            if length is not None:
                try:
                    size = int(length)
                    if size < 0:
                        raise ValueError
                except ValueError:
                    return JSONResponse({'detail': 'Invalid content length'}, status_code=400)
                if size > MAX_BODY:
                    return JSONResponse({'detail': 'Request exceeds 16 KiB'}, status_code=413)
            body = await request.body()
            if len(body) > MAX_BODY:
                return JSONResponse({'detail': 'Request exceeds 16 KiB'}, status_code=413)
            if length is not None and len(body) != size:
                return JSONResponse({'detail': 'Truncated body'}, status_code=400)
        return await call_next(request)

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request, error):
        # Omit raw inputs so nonfinite JSON values cannot break error serialization.
        details = [{key: item[key] for key in ('loc', 'msg', 'type')} for item in error.errors()]
        return JSONResponse({'detail': details}, status_code=422)

    @app.exception_handler(ValueError)
    async def invalid_requirement(request, error):
        return JSONResponse({'detail': str(error)}, status_code=400)

    @app.exception_handler(LLMUnavailable)
    async def unavailable_interpretation(request, error):
        return JSONResponse({'detail': str(error)}, status_code=502)

    @app.get('/health')
    def health():
        return {'status': 'ok', 'synthetic': True, 'database': 'sqlite-memory',
                'language_understanding': 'openrouter' if app.state.service.interpreter else 'rules'}

    @app.post('/discover')
    def discover(request: Request):
        return app.state.service.discover(request.model_dump())

    @app.post('/compare')
    def compare(request: CompareRequest):
        return app.state.service.compare(request.product_ids)

    @app.post('/search')
    def search(request: SearchRequest):
        return {'matches': app.state.service.catalog.search(**request.model_dump()),
                'eligibility_checked': False}

    return app
