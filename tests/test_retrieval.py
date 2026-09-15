import math
import unittest
from ai_commerce.text import tokenize, chunk_source, vocabulary
from ai_commerce.vectors import TFIDF, PPMI, cosine, dot, normalize
from ai_commerce.search import BM25, exact_scan, rrf, rerank_features
from ai_commerce.evaluation import metrics


class RetrievalTests(unittest.TestCase):
    def test_tokenizer(self):
        self.assertEqual(tokenize('No Wi-Fi without L42-r2'), ['no','wifi','without','l42-r2'])
        self.assertEqual(tokenize('wi fi WIFI wi-fi'), ['wifi']*3)

    def test_offsets(self):
        text='one the three four five six seven'
        chunks=chunk_source('s','p','title','dock',text,4,1)
        self.assertEqual([(c.start,c.end) for c in chunks],[(0,4),(3,7)])
        for c in chunks: self.assertEqual(c.text,' '.join(text.split()[c.start:c.end]))

    def test_bad_overlap(self):
        with self.assertRaises(ValueError): chunk_source('s','p','','','x',4,4)

    def test_vocabulary(self):
        self.assertEqual(vocabulary(['beta alpha beta']),('beta','alpha'))
        with self.assertRaises(ValueError): vocabulary(['x'],1001)

    def test_vector_math(self):
        self.assertEqual(dot({'x':3},{'x':4}),12)
        self.assertAlmostEqual(cosine({'x':3,'y':4},{'x':1}),0.6)
        self.assertEqual(cosine({},{}),0)
        self.assertEqual(normalize({}),{})

    def test_tfidf_formula(self):
        model=TFIDF(['red red blue','blue'],['red','blue'])
        self.assertAlmostEqual(model.idf['red'],1+math.log(3/2))
        self.assertEqual(model.idf['blue'],1)
        self.assertAlmostEqual(model.weights('red red')['red'],(1+math.log(2))*(1+math.log(3/2)))
        self.assertEqual(model.encode('missing'),{})

    def test_ppmi_formula(self):
        model=PPMI(['red blue','red green'],['red','blue','green'],1)
        self.assertAlmostEqual(model.words['red']['blue'],1/math.sqrt(2))
        self.assertAlmostEqual(model.words['blue']['red'],1)
        self.assertEqual(PPMI([],[]).words,{})

    def test_ppmi_does_not_close_oov_gaps(self):
        self.assertEqual(PPMI(['red absent blue'],['red','blue'],1).words,{})

    def test_bm25_formula(self):
        model=BM25({'a':'red red','b':'blue'})
        expected=math.log(2)*2*2.5/(2+1.5*(0.25+0.75*2/1.5))
        self.assertAlmostEqual(model.search('red')[0][1],expected)
        self.assertEqual(model.search('red'),model.search('red red'))
        self.assertEqual(BM25({}).search('red'),[])

    def test_rrf(self):
        scores=dict(rrf([('zero',0),('a',4),('a',3)],[('b',2),('a',1)]))
        self.assertAlmostEqual(scores['a'],1/61+1/62)
        self.assertNotIn('zero',scores)

    def test_scan(self):
        self.assertEqual(exact_scan({'x':1},{'a':{'x':1},'b':{'y':1}}),[('a',1.0)])

    def test_reranker(self):
        model=TFIDF(['wifi washer'],['wifi','washer'])
        self.assertAlmostEqual(rerank_features('wifi washer','wifi washer','wifi washer',model)['score'],1)

    def test_metrics(self):
        result=metrics(['irrelevant','a','a'],{'a':3,'b':1},2)
        self.assertEqual(result['recall_at_k'],0.5)
        self.assertEqual(result['mrr'],0.5)
        self.assertAlmostEqual(result['ndcg_at_k'],(7/math.log2(3))/(7+1/math.log2(3)))
