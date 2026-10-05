"""Run optional learning tools separately from the application."""
import argparse
import json


def main():
    parser = argparse.ArgumentParser(description='AI Commerce learning experiments')
    parser.add_argument('--catalog')
    parser.add_argument('--vocabulary-limit', type=int, default=500)
    parser.add_argument('command', choices=['evaluate', 'ontology-demo'])
    args = parser.parse_args()
    try:
        if args.command == 'evaluate':
            from ai_commerce.catalog import load_catalog
            from .evaluation import evaluate
            catalog = load_catalog(args.catalog)
            try:
                result = evaluate(catalog, args.vocabulary_limit)
            finally:
                catalog.close()
        else:
            from .ontology import demo
            result = demo()
        print(json.dumps(result, indent=2))
    except (ValueError, KeyError, TypeError, OSError) as error:
        parser.error(str(error))


if __name__ == '__main__':
    main()
