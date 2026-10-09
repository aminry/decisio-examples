Queries: 400 (200 answerable, 200 unanswerable), 10 candidates each from BM25. A passage is kept at 2.9229953289031982 or more (chosen to keep as many per query as the Decisio run).

- BM25's top 10 held the relevant paragraph for 188 of 200 answerable queries.
- The filter kept that paragraph for 144 of those 188 (76.6%, 95% interval 70.0% to 82.1%).
- It kept 1.1 passages per answerable query out of 10; 65.5% of the kept passages were the relevant paragraph.
- Ordering the candidates by its probability put the relevant paragraph first in 92.0% of queries (BM25's own order: 86.7%).
- Relevant against irrelevant, as an AUC: 0.966 (BM25's score: 0.911).
- Unanswerable queries: it kept nothing for 86 of 200 (43.0%, 95% interval 36.3% to 49.9%); 0.69 kept per query on average.
