# Retrieval internals

## Text and vocabulary

Lowercase English tokens; normalize Wi-Fi, wifi and wi fi; retain hyphenated revisions such as l42-r2 and negation (no, not, without). A small stop list removes common function words. Chunk source text into 36 original whitespace words, with 8-word overlap. Start is inclusive and end exclusive. Offsets refer to source words before tokenization.

Vocabulary takes the most frequent actual source tokens (default maximum 500, configurable 1–1,000) with alphabetical tie-breaking. No padding. Terms outside it contribute no vector weight. BM25 has its own full postings vocabulary, retaining rare lexical identifiers.

## Sparse vector arithmetic

A dictionary maps dimension to weight; omitted dimensions are zero.

`dot(a,b) = sum(a[t] * b.get(t,0) for t in a)`

`norm(a) = sqrt(dot(a,a))`

`cosine(a,b) = dot(a,b)/(norm(a)*norm(b))`, or zero if either vector is zero.

For a=(3,4), b=(1,0), dot=3, norms=5 and 1, cosine=0.6. Normalization divides nonzero entries by the norm. Exact scanning evaluates every document vector; no ANN approximation is involved.

## TF-IDF

For N indexed chunks and term document frequency df:

`idf(t) = 1 + ln((N+1)/(df(t)+1))`

`weight(t,d) = (1+ln(tf(t,d))) * idf(t)` for present terms; absent terms have zero weight. Normalize the vector. Query and document encoders share the fitted IDF.

In documents “red red blue” and “blue”, idf(red)=1+ln(3/2), idf(blue)=1. Raw red weight in the first document is (1+ln(2))*(1+ln(3/2)). This is lexical weighting, not a neural embedding.

Repeated titles are indexed with every chunk. Overlapping chunks increase N, token frequencies and document frequencies. These deliberate educational choices change scores; the source-preserving chunks expose their origin.

## PPMI

Train on original reviewed active sources, without chunk overlap or repeated title augmentation. Count ordered word/context pairs within a two-token window on tokenized text. Out-of-vocabulary words retain their positions so omitted words cannot create spurious neighbors.

`PPMI(w,c) = max(0, ln(count(w,c)*total_pairs/(row_total(w)*column_total(c))))`

Normalize each word vector, then pool its context dimensions weighted by text TF-IDF and normalize the pooled vector. For sources “red blue” and “red green”, window 1, red has two equal positive context weights; normalized values are 1/sqrt(2). Blue has a single unit red dimension.

No separate hand-authored synonym training sentences are injected; all training text is visible in catalog.json, including the dock wording “monitor screen display”. Similar contexts can group antonyms too. Tiny PPMI cannot reliably interpret negation, prerequisites or unseen meaning.

## BM25

Use inverted postings rather than scanning all text. N is the number of chunks; document length includes its repeated title.

`idf(t) = ln(1+(N-df(t)+0.5)/(df(t)+0.5))`

`contribution(t,d) = idf(t)*tf(t,d)*(k1+1)/(tf(t,d)+k1*(1-b+b*len(d)/avg_len))`

Sum contributions for unique query terms; k1=1.5, b=0.75. Higher frequency saturates and longer documents are adjusted. Each returned match includes per-term contributions. Empty corpora and missing terms yield no hits.

## Fusion and second-stage scoring

Combine positive BM25 and PPMI rankings: `RRF(d)=sum(1/(60+rank(d)))`. Ranks begin at one; zero hits and duplicate IDs are removed before assigning positions. TF-IDF is an independently evaluated baseline, not an additional lexical vote.

The first 20 fused chunks are reranked by:

- 0.45 times IDF-weighted query term coverage in source text.
- 0.25 times query term coverage in the title.
- 0.20 times TF-IDF cosine with source text.
- 0.10 times adjacent query-token-pair coverage.

These are hand-set weights, not probabilities or a cross-encoder. Ties use stable IDs. Product discovery ranks after hard checks; a high score cannot override missing evidence, prerequisites or budget.

## Evaluation

Run `python -m ai_commerce evaluate` to compare BM25, TF-IDF, PPMI, RRF and reranked retrieval. Deduplicate product IDs after chunk retrieval. Report Recall@3, full-ranking MRR and nDCG@3 (gain 2^grade-1; discount log2(rank+1)). Three visible hand-authored judgments are deliberately tiny and illustrative. They measure relevance, not commerce eligibility. Service tests separately enforce the expected eligibility outcomes. Use a larger held-out set before selecting model adapters or claiming improvement.
