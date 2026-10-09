Queries: 400 (200 answerable, 200 unanswerable), 10 candidates each from BM25. A passage is kept at 0.5 or more (fixed before the run).

- BM25's top 10 held the relevant paragraph for 188 of 200 answerable queries.
- The filter kept that paragraph for 182 of those 188 (96.8%, 95% interval 93.2% to 98.5%).
- It kept 1.32 passages per answerable query out of 10; 68.9% of the kept passages were the relevant paragraph.
- Ordering the candidates by its probability put the relevant paragraph first in 93.1% of queries (BM25's own order: 86.7%).
- Relevant against irrelevant, as an AUC: 0.99 (BM25's score: 0.911).
- Unanswerable queries: it kept nothing for 125 of 200 (62.5%, 95% interval 55.6% to 68.9%); 0.47 kept per query on average.
