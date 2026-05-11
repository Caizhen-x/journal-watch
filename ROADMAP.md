# Roadmap

Pending upgrades, prioritized by execution feasibility.

## Trends page — additional statistical plots

Brainstorm of charts to add to `views/trends.py`. All use only data already in `papers.db` unless noted.

### Tier 1 — Trivial (~10-15 min each, no new deps)

1. **Relevance distribution per year (boxplot)** — spread/median/outliers per year. Are recent years more or less relevant on average?
2. **Top 20 most prolific authors in window** — bar chart from `papers.authors_json`.
3. **Topic co-occurrence matrix** — heatmap of "when a paper has topic X, how often does it also have Y?" Reveals natural pairings.
4. **Method × topic affinity heatmap** — which methods get used for which topics.
5. **All-time top-N papers by relevance** — leaderboard table, no time axis. Sortable.
6. **Abstract coverage by journal/year** — % of papers with usable abstracts. Data-quality dashboard.
7. **Year-over-year growth rate per topic** — line chart of % change. Which topics rose/fell fastest.
8. **Papers per month (not year) — finer-grain volume** — useful around peer-review cycles, special issues.

### Tier 2 — Easy (~30-45 min each, no new deps)

9. **Method-group dominance over time** — stacked area: causal inference vs experimental vs structural vs descriptive. Tells the "credibility revolution" story.
10. **Causal-inference share** — single line: % of papers using any `ci_*` method, by year.
11. **"Hot right now" — fastest-growing topics in last 24 months** — ratio of recent vs older window; tile/bar layout.
12. **Methodological complexity** — average number of method tags per paper per year. Proxy for mixed-methods rise.
13. **Journal personality** — for each journal, its top 5 topics + top 5 methods. Side-by-side cards. "What is JEEM about, really?"

### Tier 3 — Medium (~1-2 hr each, may need small dep)

14. **Title word cloud per topic** — visual vocabulary snapshot. Needs `wordcloud` library (~5 MB).
15. **Sankey diagram: journal → topic → method** — flow chart of how research moves. Altair supports it; needs careful data shaping.
16. **Top author × topic specialization heatmap** — who's known for what. Multi-step aggregation.
17. **Annual research-volume forecast** — simple linear extrapolation. Statsmodels has that.

### Tier 4 — Harder (2-4 hr, real new tooling)

18. **Co-authorship network graph** — render author collaboration network. Needs `networkx` + `pyvis`. Heavy for the insight at this scale.
19. **Abstract bigram/trigram trends** — "which phrases are rising?" Needs NLP preprocessing (stopwords, lemmatization).
20. **Topic embedding clustering** — sentence embeddings → UMAP → cluster. Reveals structure beyond LLM tags. Expensive (extra API calls).

### Recommended bundle if doing just one pass

Highest narrative value: **#9 (method-group dominance), #3 (topic co-occurrence), #11 (hot right now), #2 (top authors)** — ~2 hours total, transforms the trends page.

For pure visual flair: add **#14 (word clouds)** — biggest "colorful" punch.

## Other deferred items

- **Subscribe button** — was added then removed when the Google Form wasn't ready. Add back via `st.secrets["subscribe_form_url"]` once the Form exists. See SETUP.md for the Form construction.
- **Domain expansion** — currently 20 journals across Ag Econ + Env & Resource Econ. The original folder has 6 more domains (Dev Econ, Econometrics, Economics, Info & Mgmt, Statistics, other). Adding them is just appending to `data/journals.yaml`.
- **Group photos / custom branding** — beyond the HU Berlin seal currently rendered via `st.logo()`. Could add a banner image, team grid, lab building shot in the dashboard header.
- **Classifier prompt tuning** — after a few weeks of real use, review whether the relevance scores feel calibrated. Bump `CLASSIFIER_VERSION` to force a reclassify pass with a refined prompt.
