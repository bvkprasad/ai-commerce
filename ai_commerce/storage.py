"""SQLite storage and validated catalog records. No mutable in-memory catalog copies."""
import json
import re
from contextlib import closing
from pathlib import Path
import sqlite3
from threading import RLock

from pydantic import Field, model_validator

from .request import Category, RequestModel, timestamp


class Source(RequestModel):
    id: str = Field(min_length=1)
    product_id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    locator: str = Field(min_length=1)
    publisher: str = Field(min_length=1)
    version: str = Field(min_length=1)
    reviewed: bool
    active: bool


class Fact(RequestModel):
    name: str
    value: bool | int | str
    evidence: list[str]
    ontology_version: int
    prerequisites: list[str] = Field(default_factory=list)


class Assessment(RequestModel):
    host: str = Field(min_length=1)
    os: str = Field(min_length=1)
    display_mode: str = Field(min_length=1)
    resolution: str = Field(min_length=1)
    cable_set: str = Field(min_length=1)
    version: str = Field(min_length=1)
    display_count: int = Field(ge=1)
    driver_required: bool
    evidence: list[str]


class Product(RequestModel):
    id: str = Field(min_length=1)
    category: Category
    title: str = Field(min_length=1)
    source_ids: list[str]
    facts: list[Fact]
    assessments: list[Assessment]


class Offer(RequestModel):
    id: str = Field(min_length=1)
    product_id: str
    currency: str = Field(pattern='^INR$')
    price_paise: int = Field(ge=0)
    accessories_paise: int = Field(ge=0)
    shipping_paise: int = Field(ge=0)
    stock: int = Field(ge=0)
    valid_from: str
    expires_at: str
    delivery_at: str
    cable_set: str | None = None

    @model_validator(mode='after')
    def valid_dates(self):
        if timestamp(self.valid_from) >= timestamp(self.expires_at):
            raise ValueError('Invalid offer validity interval')
        timestamp(self.delivery_at)
        return self


class CatalogData(RequestModel):
    ontology_version: int
    products: list[Product]
    sources: list[Source]
    offers: list[Offer]

    def validate_references(self, features):
        if self.ontology_version != features.version:
            raise ValueError('Catalog and feature schema version mismatch')
        sources = {source.id: source for source in self.sources}
        product_ids = {product.id for product in self.products}
        if len(sources) != len(self.sources) or len(product_ids) != len(self.products):
            raise ValueError('Duplicate product or source ID')
        if any(source.product_id not in product_ids for source in self.sources):
            raise ValueError('Source refers to unknown product')
        for product in self.products:
            references = list(product.source_ids)
            for fact in product.facts:
                features.validate(fact.name, fact.value)
                if fact.ontology_version != features.version:
                    raise ValueError('Fact feature schema version mismatch')
                references.extend(fact.evidence)
            for assessment in product.assessments:
                references.extend(assessment.evidence)
            if any(source_id not in sources or sources[source_id].product_id != product.id for source_id in references):
                raise ValueError('Missing or wrong-product evidence reference')
        if len({offer.id for offer in self.offers}) != len(self.offers) or len({offer.product_id for offer in self.offers}) != len(self.offers):
            raise ValueError('Duplicate offer')
        if any(offer.product_id not in product_ids for offer in self.offers):
            raise ValueError('Offer refers to unknown product')


SCHEMA = '''
CREATE TABLE metadata (ontology_version INTEGER NOT NULL);
CREATE TABLE products (id TEXT PRIMARY KEY, category TEXT NOT NULL, document TEXT NOT NULL CHECK(json_valid(document)));
CREATE TABLE sources (id TEXT PRIMARY KEY, product_id TEXT NOT NULL REFERENCES products(id), document TEXT NOT NULL CHECK(json_valid(document)));
CREATE TABLE offers (id TEXT PRIMARY KEY, product_id TEXT NOT NULL UNIQUE REFERENCES products(id), document TEXT NOT NULL CHECK(json_valid(document)));
CREATE INDEX products_category ON products(category);
CREATE INDEX sources_product ON sources(product_id);
CREATE VIRTUAL TABLE evidence_search USING fts5(source_id UNINDEXED, product_id UNINDEXED, category UNINDEXED, text, tokenize='porter unicode61');
'''
TABLES = {'products', 'sources', 'offers'}


def normalize_wifi(text):
    return re.sub(r'\bwi[\s-]*fi\b', 'wifi', text, flags=re.IGNORECASE)


class Database:
    def __init__(self):
        self.lock = RLock()
        self.connection = sqlite3.connect(':memory:', check_same_thread=False)
        self.connection.execute('PRAGMA foreign_keys = ON')
        self.connection.executescript(SCHEMA)

    def replace(self, data):
        """Commit a complete validated release atomically."""
        with self.lock, self.connection:
            for table in ('evidence_search', 'offers', 'sources', 'products', 'metadata'):
                self.connection.execute(f'DELETE FROM {table}')
            self.connection.execute('INSERT INTO metadata VALUES (?)', (data['ontology_version'],))
            for table in ('products', 'sources', 'offers'):
                column = 'category' if table == 'products' else 'product_id'
                records = [(row['id'], row[column], json.dumps(row)) for row in data[table]]
                self.connection.executemany(f'INSERT INTO {table} VALUES (?, ?, ?)', records)

            products = {product['id']: product for product in data['products']}
            indexed = []
            for source in data['sources']:
                if source['active'] and source['reviewed']:
                    product = products[source['product_id']]
                    text = normalize_wifi(product['title'] + ' ' + source['text'])
                    indexed.append((source['id'], product['id'], product['category'], text))
            self.connection.executemany('INSERT INTO evidence_search VALUES (?, ?, ?, ?)', indexed)

    def search(self, query, category=None, limit=20):
        # Quote individual tokens so user input cannot become FTS operators.
        terms = re.findall(r'[^\W_]+', normalize_wifi(query).lower())
        if not terms:
            return []
        match = ' OR '.join('"' + term + '"' for term in dict.fromkeys(terms))
        with self.lock:
            rows = self.connection.execute(
                'SELECT source_id, product_id, -bm25(evidence_search) AS score FROM evidence_search '
                'WHERE evidence_search MATCH ? AND (? IS NULL OR category = ?) '
                'ORDER BY score DESC, source_id LIMIT ?', (match, category, category, limit),
            ).fetchall()
        return [dict(source_id=row[0], product_id=row[1], score=row[2]) for row in rows]

    def records(self, table, category=None):
        if table not in TABLES:
            raise ValueError('Unknown catalog table')
        query = f'SELECT document FROM {table}'
        parameters = ()
        if category is not None:
            if table != 'products':
                raise ValueError('Category applies only to products')
            query += ' WHERE category = ?'
            parameters = (category,)
        with self.lock:
            rows = self.connection.execute(query + ' ORDER BY id', parameters).fetchall()
        return [json.loads(row[0]) for row in rows]

    def get(self, table, record_id):
        if table not in TABLES:
            raise ValueError('Unknown catalog table')
        key = 'product_id' if table == 'offers' else 'id'
        with self.lock:
            row = self.connection.execute(f'SELECT document FROM {table} WHERE {key} = ?', (record_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def export(self):
        with self.lock:
            version = self.connection.execute('SELECT ontology_version FROM metadata').fetchone()[0]
            return {'ontology_version': version, **{table: self.records(table) for table in TABLES}}

    def save(self, path):
        with self.lock, closing(sqlite3.connect(path)) as destination:
            self.connection.backup(destination)

    def close(self):
        with self.lock:
            self.connection.close()


def read_database(path):
    uri = Path(path).resolve().as_uri() + '?mode=ro'
    with closing(sqlite3.connect(uri, uri=True)) as connection:
        version = connection.execute('SELECT ontology_version FROM metadata').fetchone()[0]
        return {'ontology_version': version, **{
            table: [json.loads(row[0]) for row in connection.execute(f'SELECT document FROM {table} ORDER BY id')]
            for table in TABLES
        }}
