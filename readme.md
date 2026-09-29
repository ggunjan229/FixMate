# FixMate — Cooperative Service Marketplace

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
- English/Hindi customer interface, assistant replies and browser speech input where supported. The assistant uses local intent handling; it does not call a paid LLM. The picker exposes only fully bundled locales; see [localization notes](docs/LOCALIZATION.md) before adding another language.
- FastAPI API docs, health endpoint, installable app shell, and offline caching of static screens. Offline API mutations are not queued.

## Data and machine learning

### Worker matching

The existing `train.py`, `my_ml_core.py`, `model.joblib` and `evaluation_report.json` remain in the project. `/rank-candidates` preserves the previous ranking contract. Live booking matching first filters verified and available workers by skill, service radius, and schedule conflicts. It then scores the entire candidate group with the saved classifier when compatible and blends that result with a transparent fair-match score based on distance, availability, rating, experience, certifications, and workload. A rule-based score remains available when the model artifact is unavailable. The app returns the score method and factor values so the match is inspectable.

The committed allocation report is a baseline (ROC-AUC about 0.67, NDCG@5 about 0.765 on its holdout). Keep those as prototype results; do not present them as live-service performance. The source/provenance of the candidate CSV should be documented before drawing conclusions about generalization or representing it as real worker data.

At booking time, the app uses current SQLite worker profiles, verification and availability, service skills, coordinates and coverage radius, current bookings, ratings, experience, certifications, rates, and account tenure. It filters candidates first, calculates relative model features across the entire eligible candidate set, and combines the saved model probability with a transparent fairness score. The response and persisted booking include the candidate count, assigned worker, score method, and score factors. Customer-created requests do not automatically retrain the classifier; they become platform records and live context for subsequent decisions.

### Demand forecasting

`forecasting.py` builds a reproducible three-year synthetic daily panel across nine service categories and six Gurugram localities. It fits `HistGradientBoostingRegressor` and validates on the latest 90 days chronologically. The API reports MAE and RMSE from that holdout. Once a category and locality have at least 10 non-cancelled past service requests spanning 28 days, the synthetic model forecast is calibrated to the platform's own recent booking history. Before that threshold, the app labels the result as synthetic. The model does not retrain on this small history.

Workforce planning takes the peak predicted jobs per day, estimates staff at 1.5 jobs per worker-shift, and compares that peak need with verified, available workers who have the skill and cover the locality. The admin dashboard scans all 54 service/locality combinations and persists in-app recruitment alerts when a gap exists. Admins can mark recruitment as started; incoming workers still register and complete the existing verification flow. These are dashboard alerts, not external push, SMS, or email notifications. Locality centroids and the staffing ratio are explicit planning assumptions and must be validated with cooperative data.

Replace simulated demand with dated cooperative bookings and weather/holiday features before making operational forecasts. Avoid random row splits for time-series claims. Report the dataset coverage, baseline comparisons, temporal holdout, MAE/RMSE, and limitations in your resume/demo.

## Important prototype boundaries

- `demo_digital` creates a visible ledger entry only. It does **not** charge a card, transfer money, or integrate a payment provider. Cash confirmation is also a demonstration record.
- Worker verification is an admin workflow, not government identity verification. Welfare status is a cooperative record, not an insurance policy or government-benefit enrollment.
- Demo coordinates and workers are seed records around Gurugram. The platform is not yet connected to a production cooperative roster, map/geocoding provider, messaging/SMS service, or external identity provider.
- This is a local prototype with development defaults and a browser token. Harden secrets, CORS, rate limits, consent, data retention, deployment TLS, and payment/identity integrations before real users.

## Project layout

```text
api.py                         Backward-compatible ASGI entry point (uvicorn api:app)
fixmate/
  main.py                      FastAPI app factory, lifecycle, and router registration
  config.py                    Shared paths and environment-backed configuration
  runtime.py                   Models initialized during application startup
  schemas.py                   Validated API request models
  security.py                  Session tokens and role-access dependencies
  routers/
    core.py                    Health, service catalog, and PWA shell routes
    auth.py                    Registration, sign-in, and current-user routes
    workers.py                 Worker profile, discovery, and availability routes
    bookings.py                Booking lifecycle, reviews, payment records, invoices
    assistant.py               Local assistant endpoint
    insights.py                Forecast, cooperative analytics, admin, worker summary
    matching.py                Backward-compatible candidate scoring API route
  services/
    matching.py                Candidate filtering, distance, model scoring, fair ranking
    workforce_planning.py      Forecast-to-roster comparison and persisted shortage alerts
    booking_serialization.py   Database-row to booking-response conversion
platform_db.py                 SQLite schema, password hashing, demo data
analysis.py                    Dataset profiling and workload fairness statistics
forecasting.py                 Synthetic demand panel, temporal validation, forecaster
train.py                       Worker-allocation model training pipeline
my_ml_core.py                  Allocation feature contract and ranking evaluation
model.joblib                   Saved worker-allocation model artifact
evaluation_report.json         Committed model-evaluation results
app/                           Responsive installable PWA (HTML/CSS/JS)
  i18n.js                      English/Hindi UI dictionaries and locale formatting
docs/                          Model documentation and project notes
tests/                         API workflow and model checks
```

The HTTP layer is grouped by product area; shared validation, authentication, and matching logic live in dedicated modules. `api.py` intentionally remains as a tiny compatibility entry point so the existing `uvicorn api:app` command and imports used by tests continue to work. The browser app keeps the same API paths and payloads across this refactor.

## Verify

```powershell
python -m pytest -q
```
