# Setup guide

One-time setup to make the system run end-to-end. About 30 minutes total.

## 1. Anthropic API key

1. Go to https://console.anthropic.com/settings/keys → **Create Key**.
2. In your terminal:
   ```bash
   gh secret set ANTHROPIC_API_KEY --repo Caizhen-x/journal-watch
   ```
   Paste the key when prompted.

## 2. Gmail App Password (for sending digests)

The digest is sent from a Gmail account via SMTP. You'll use **App Passwords**, not your regular password.

1. Make sure 2-Step Verification is enabled on the Gmail account: https://myaccount.google.com/security
2. Generate an App Password: https://myaccount.google.com/apppasswords (label it "journal-watch")
3. Add both as GHA secrets:
   ```bash
   gh secret set GMAIL_SENDER_ADDRESS --repo Caizhen-x/journal-watch
   # paste the Gmail address (e.g., fqqqywzwan@gmail.com)
   gh secret set GMAIL_APP_PASSWORD --repo Caizhen-x/journal-watch
   # paste the 16-char App Password (no spaces)
   ```

## 3. Subscriber Google Form

### 3a. Create the Form

1. Go to https://forms.google.com → **+ Blank**.
2. Title: "Journal Watch — Subscription".
3. Description: "Weekly research-paper digest from top Ag/Env Econ journals, filtered to your interests. Unsubscribe anytime by replying to any digest email."
4. Add these fields **with these exact titles** (the code reads column names from the sheet):

   | Field title | Type | Options |
   |---|---|---|
   | `Email` (required, set under Settings → Responses → "Collect email addresses") | — | — |
   | `Name` (short answer, optional) | Short answer | — |
   | `Topics` | Checkboxes (multi-select) | The 12 topic labels — see below |
   | `Methods` | Checkboxes (multi-select) | The 15 method labels — see below |
   | `Minimum relevance` | Linear scale 0–10 (optional) | default suggest 5 |

   **Topic options** (paste these as the checkbox values, exact text):
   - Agri-food value chain & supply chain
   - Sustainability & governance of agri-food systems
   - Food security & nutrition
   - Smallholder farmers & gender dynamics
   - Agroforestry & ecosystem services
   - Digital agriculture & ag-tech adoption
   - Consumer behavior & food choice
   - Climate change & agriculture
   - Agricultural trade & policy
   - Land use & land economics
   - Energy & agriculture
   - AI / ML in agriculture

   **Method options**:
   - RCT / field experiment
   - Difference-in-differences
   - Instrumental variables
   - Regression discontinuity
   - Matching / synthetic control
   - Structural estimation
   - Theoretical / analytical model
   - Lab / online experiment
   - Discrete choice / contingent valuation / WTP
   - Survey / descriptive analysis
   - Mixed methods (quant + qual)
   - Qualitative (case study, interviews, ethnography)
   - Machine learning / prediction
   - Systematic review / meta-analysis / bibliometric
   - Simulation (CGE, agent-based, etc.)

5. Add a final required checkbox: "I consent to receive a weekly research digest. I can unsubscribe by emailing the maintainer."

### 3b. Link the Form to a Sheet and publish it

1. In the Form, switch to the **Responses** tab → click the green Sheets icon → "Create new spreadsheet".
2. Open the linked Sheet.
3. **Important:** make sure the column headers exactly match the field titles (`Email`, `Name`, `Topics`, `Methods`, `Minimum relevance`). Google will use the form question text as the column name; rename if needed.
4. **File → Share → Publish to web** → choose "Form responses 1" sheet, format CSV, click **Publish**. Copy the published URL — it looks like:
   ```
   https://docs.google.com/spreadsheets/d/e/SOMETHING/pub?gid=0&single=true&output=csv
   ```
5. Add as GHA secret:
   ```bash
   gh secret set SUBSCRIBERS_CSV_URL --repo Caizhen-x/journal-watch
   # paste the published CSV URL
   ```

### 3c. Add an `Unsubscribe` column (optional but recommended)

In the Sheet, manually add a column header `Unsubscribe`. When someone emails you to unsubscribe, type any non-empty value (e.g., "yes") in their row. The next digest run will skip them.

## 4. Verify everything is wired up

```bash
gh secret list --repo Caizhen-x/journal-watch
```

You should see all four:
- `ANTHROPIC_API_KEY`
- `GMAIL_SENDER_ADDRESS`
- `GMAIL_APP_PASSWORD`
- `SUBSCRIBERS_CSV_URL`

## 5. Test runs

Trigger the workflows manually before the first cron fires:

```bash
gh workflow run "Daily poll"     --repo Caizhen-x/journal-watch
gh workflow run "Weekly digest"  --repo Caizhen-x/journal-watch
```

Watch the runs:
```bash
gh run list --repo Caizhen-x/journal-watch
gh run watch --repo Caizhen-x/journal-watch
```

Add yourself to the Form first so the test digest has a subscriber.

## Schedules

- **Daily poll** runs at 06:00 UTC (07:00/08:00 Berlin depending on DST).
- **Weekly digest** runs Monday 07:00 UTC.

Adjust in `.github/workflows/*.yml` if needed.
