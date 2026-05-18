# Journal Watch

Automated journal watch for the **Agrifood Chain Management** group at the Thaer-Institut, Humboldt-Universität zu Berlin.

### 🌐 [**Open the live website →**](https://thaer-agrifood-journal-watch.streamlit.app/)

[![Live app](https://img.shields.io/badge/Live_app-thaer--agrifood--journal--watch.streamlit.app-FF4B4B?logo=streamlit&logoColor=white)](https://thaer-agrifood-journal-watch.streamlit.app/) [![Hosted on Streamlit Cloud](https://img.shields.io/badge/hosted_on-Streamlit_Cloud-FF4B4B)](https://share.streamlit.io)

The site polls top journals weekly and classifies new papers by **topic × method** using an LLM. An email-digest workflow exists but is **paused** — to re-enable, set the `ENABLE_DIGEST` repository variable and add the Gmail/Form secrets per `SETUP.md`. Group members access the dashboard with a shared password.

## How it works

```
[GitHub Actions, every Monday 06:00 UTC]
    ↓
Fetch new papers from OpenAlex (by ISSN)
    ↓
Claude Haiku classifier tags each paper: topics[] + methods[] + relevance (0–10)
    ↓
SQLite committed back to the repo → Streamlit Cloud auto-redeploys

[Weekly digest workflow — currently disabled]
   gated by ENABLE_DIGEST repo variable; sends emails when re-enabled.
```

## Repo layout

```
journal-watch/
├── app.py                 # Streamlit entrypoint (st.navigation)
├── auth.py                # Shared-password gate
├── views/                 # Dashboard + Trends pages
├── assets/hu-logo.png     # HU Berlin seal
├── src/                   # fetcher, classifier, digest builder, DB
├── data/
│   ├── journals.yaml      # 20 journals with ISSNs
│   ├── taxonomies.yaml    # 12 topics × 15 methods
│   └── papers.db          # ~20K classified papers, updated weekly
├── .github/workflows/     # weekly-poll + weekly-digest cron
├── SETUP.md               # one-time setup (API keys, Gmail, Google Form)
├── DEPLOY.md              # how the public site is hosted
└── ROADMAP.md             # deferred upgrades
```

## Run locally

```bash
pip install -r requirements.txt
JOURNAL_WATCH_DEV_MODE=true streamlit run app.py
```

Opens at http://localhost:8501. Same code as the live site. The password gate **fails closed by default** — set `JOURNAL_WATCH_DEV_MODE=true` to bypass it locally, or put a real `app_password` in `.streamlit/secrets.toml`. (Production must use `app_password`; do not deploy with dev mode.)

## Coverage

20 journals across **Agricultural Economics** and **Environmental & Resource Economics**, ~20,000 classified papers spanning 2016–present. Updated weekly via the GitHub Actions workflow.

See [`ROADMAP.md`](ROADMAP.md) for planned upgrades.
