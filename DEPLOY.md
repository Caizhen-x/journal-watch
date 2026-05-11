# Deployment guide — Streamlit Cloud + shared password

The browse UI and trend dashboard are deployed to Streamlit Community Cloud (free), gated by a single shared password. Group members get one URL + one password from you.

## How it stays in sync

The daily-poll GitHub Actions workflow commits the updated `data/papers.db` to the repo. Streamlit Cloud auto-redeploys on every push, so the hosted app shows fresh data without any manual step.

## One-time setup

### 1. Connect Streamlit Cloud to the repo

1. Go to https://share.streamlit.io and sign in with GitHub (use the `Caizhen-x` account).
2. Click **Create app** → **Deploy a public app from GitHub**.
3. Pick:
   - **Repository:** `Caizhen-x/journal-watch`
   - **Branch:** `main`
   - **Main file path:** `app.py`
   - **App URL** (custom): something like `agecon-journal-watch.streamlit.app`
4. Open **Advanced settings** before clicking Deploy:
   - **Python version:** 3.12
   - **Secrets:** paste this (replace the password):
     ```toml
     app_password = "pick-a-memorable-password"
     ```
5. Click **Deploy**. First deploy takes ~2 minutes (installing Python deps).

### 2. Verify

Visit your app URL. You should see a password prompt. Enter the password — the browse page loads. Click **Trends** in the sidebar — that page also requires the password (session-based).

### 3. Share with the group

Send group members one message containing:
- The URL
- The password
- A line about what's there: "Browse classified ag/env econ papers, see methodology trends over time. Filters in the left sidebar."

Tell them to **bookmark the URL**, not save the password in an email thread.

## Optional: enable the "Subscribe to weekly digest" button

When you have the Google Form (see `SETUP.md`), grab its public "responder" link and add it to the app's secrets. The homepage and Trends page will then show a button that opens the form in a new tab.

1. Streamlit Cloud dashboard → your app → **Settings** → **Secrets**.
2. Add a new line:
   ```toml
   subscribe_form_url = "https://docs.google.com/forms/d/e/SOMETHING/viewform"
   ```
3. Click **Save**. The app reloads in ~10 seconds. The button appears.

If you leave this out, the button doesn't show. No errors.

## Rotating the password

If you need to change it (someone left the group, etc.):

1. Streamlit Cloud dashboard → your app → **Settings** → **Secrets** → edit `app_password`.
2. Click **Save**. The app reloads in ~10 seconds.
3. Send the new password to current members.

## Local development with the same secret

For running `streamlit run app.py` on your Mac:

```bash
mkdir -p .streamlit
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
# Edit the file, set app_password to anything (or leave the default).
```

The file is in `.gitignore`, never gets committed.

## How auth actually works

Implemented in `auth.py`. On each page:
- If you've already entered the password in this browser session → page loads
- If not → password prompt; on success, set session flag and rerun

It's a single shared password, not per-user accounts. Trade-off: simpler operationally, but you can't see who accessed when. Acceptable for a research group of ~10-30 people. If you need audit logs later, switch to GitHub OAuth via Streamlit Cloud's built-in viewer access controls.

## Cost

Streamlit Community Cloud is free for public *and* private repos under the "Community" tier as of 2026. There are limits (1 GB memory per app, sleeping after 7 days of no visits). For this app's load (small SQLite, ~10-30 visitors/week) it's well within limits.

If the app sleeps and a member visits, it wakes up in ~30 seconds. Not ideal but free.
