# FixMate - Cooperative Service Marketplace

FixMate connects households with verified local service workers managed by labour cooperatives. This repository includes an installable mobile-first app, a FastAPI backend, a local SQLite database, an explainable worker matcher, and a time-validated demand-forecasting demonstration.

## Run locally

Python 3.11 or newer is recommended.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn api:app --reload
```

Open <http://127.0.0.1:8000>. FastAPI interactive API docs are at <http://127.0.0.1:8000/docs>. The first start creates `fixmate.db` and trains the demand model from a fixed, generated demonstration dataset. Startup can take several seconds.

The app is a Progressive Web App (PWA): use the browser's **Install app** / **Add to Home Screen** action to run it in a standalone mobile window. Geolocation and speech recognition depend on browser support and secure-context rules; both have manual/text fallbacks.

## Demo accounts

| Role | Email | Password |
|---|---|---|
| Customer | `customer@fixmate.local` | `customer123` |
| Verified worker — plumbing | `ravi@fixmate.local` | `worker123` |
| Verified worker — cleaning / caregiving | `meena@fixmate.local` | `worker123` |
| Verified worker — electrical | `amit@fixmate.local` | `worker123` |
| Cooperative admin | `admin@fixmate.local` | `FixMate!2026` |

Other seeded worker accounts use `worker123`. These are local demo credentials only. Set `FIXMATE_ADMIN_EMAIL`, `FIXMATE_ADMIN_PASSWORD`, `FIXMATE_TOKEN_SECRET` and `FIXMATE_DB_PATH` in the environment before using a shared environment. Do not reuse the development defaults for a public deployment.

## Included flows

- Customer registration and sign-in; browse nine service categories and worker profiles; request an urgent or scheduled booking with a location; see matching factors, status updates, invoice, demo payment record, and review form.
- Worker registration, skill/certificate/rate/location profile, cooperative verification state, availability, assigned jobs, job state changes, earnings ledger, and welfare record.
- Cooperative admin dashboard, worker verification/suspension, booking oversight, workforce demand forecast, and model evaluation summary.
- English/Hindi assistant replies and browser speech input where supported. The assistant uses local intent handling; it does not call a paid LLM.
- FastAPI API docs, health endpoint, installable app shell, and offline caching of static screens. Offline API mutations are not queued.

## Data and machine learning

### Worker matching

The existing `train.py`, `my_ml_core.py`, `model.joblib` and `evaluation_report.json` remain in the project. `/rank-candidates` preserves the previous ranking contract. Live booking matching filters to verified and available workers with a matching skill and service radius, then uses the saved classifier if it loads successfully. Otherwise it uses a documented fair-match score based on skill, distance, availability, rating, experience and certifications. The app returns the score method and factor values so the match is inspectable.

The committed allocation report is a baseline (ROC-AUC about 0.67, NDCG@5 about 0.765 on its holdout). Keep those as prototype results; do not present them as live-service performance. The source/provenance of the candidate CSV should be documented before drawing conclusions about generalization or representing it as real worker data.

### Demand forecasting

`forecasting.py` builds a reproducible three-year synthetic daily panel across nine service categories and six Gurugram localities. It fits `HistGradientBoostingRegressor` and validates on the latest 90 days chronologically. The API reports MAE and RMSE from that holdout. The bar chart and 90th-percentile absolute-residual range are planning aids for this synthetic demonstration, not calibrated intervals. Suggested capacity is a heuristic (1.5 jobs per worker-shift), not a trained staffing recommendation.

Replace simulated demand with dated cooperative bookings and weather/holiday features before making operational forecasts. Avoid random row splits for time-series claims. Report the dataset coverage, baseline comparisons, temporal holdout, MAE/RMSE, and limitations in your resume/demo.

## Important prototype boundaries

- `demo_digital` creates a visible ledger entry only. It does **not** charge a card, transfer money, or integrate a payment provider. Cash confirmation is also a demonstration record.
- Worker verification is an admin workflow, not government identity verification. Welfare status is a cooperative record, not an insurance policy or government-benefit enrollment.
- Demo coordinates and workers are seed records around Gurugram. The platform is not yet connected to a production cooperative roster, map/geocoding provider, messaging/SMS service, or external identity provider.
- This is a local prototype with development defaults and a browser token. Harden secrets, CORS, rate limits, consent, data retention, deployment TLS, and payment/identity integrations before real users.

## Project layout

```text
api.py              FastAPI routes and role-based workflows
platform_db.py      SQLite schema, password hashing, demo data
forecasting.py      Synthetic panel, temporal evaluation, forecast API model
train.py            Existing worker-allocation model training pipeline
my_ml_core.py       Feature contract and ranking evaluation
app/                Responsive installable PWA (HTML/CSS/JS)
tests/              API workflow and model checks
```

## Verify

```powershell
python -m pytest -q
```