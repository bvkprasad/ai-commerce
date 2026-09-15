import argparse
import json
from .ingestion import load_catalog
from .service import CommerceService
from .evaluation import evaluate
from .ontology import demo


def main():
    parser = argparse.ArgumentParser(description='Synthetic AI Commerce learning application')
    parser.add_argument('--catalog')
    parser.add_argument('--vocabulary-limit', type=int, default=500)
    sub = parser.add_subparsers(dest='command', required=True)
    discover = sub.add_parser('discover')
    group = discover.add_mutually_exclusive_group(required=True)
    group.add_argument('--request', help='JSON request file')
    group.add_argument('--query', help='Conservative English query')
    search = sub.add_parser('search')
    search.add_argument('query')
    search.add_argument('--method', choices=['bm25', 'tfidf', 'ppmi', 'hybrid', 'reranked'], default='reranked')
    compare = sub.add_parser('compare')
    compare.add_argument('product_ids', nargs='+')
    sub.add_parser('evaluate')
    sub.add_parser('ontology-demo')
    server = sub.add_parser('serve')
    server.add_argument('--port', type=int, default=8000)
    server.add_argument('--host', default='127.0.0.1')
    args = parser.parse_args()
    try:
        if args.command == 'serve':
            from wsgiref.simple_server import make_server
            from .api import create_app
            service = CommerceService(load_catalog(args.catalog, vocabulary_limit=args.vocabulary_limit))
            with make_server(args.host, args.port, create_app(service)) as http:
                print(f'Local synthetic API: http://{args.host}:{args.port}', flush=True)
                http.serve_forever()
            return
        catalog = load_catalog(args.catalog, vocabulary_limit=args.vocabulary_limit)
        service = CommerceService(catalog)
        if args.command == 'discover':
            if args.request:
                with open(args.request) as source:
                    data = json.load(source)
            else:
                data = {'query': args.query}
            result = service.discover(data)
        elif args.command == 'search':
            result = catalog.search(args.query, method=args.method)
        elif args.command == 'compare':
            result = service.compare(args.product_ids)
        elif args.command == 'evaluate':
            result = evaluate(catalog)
        else:
            result = demo()
        print(json.dumps(result, indent=2))
    except (ValueError, KeyError, TypeError, OSError) as error:
        parser.error(str(error))


if __name__ == '__main__':
    main()
