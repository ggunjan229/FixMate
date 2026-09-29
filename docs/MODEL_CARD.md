# FixMate model notes

## Worker allocation

- **Purpose:** rank eligible workers for one requested service; the API filters by verification, availability, skill and travel radius before ranking.
- **Features:** booking quantity/time/day plus worker experience, certifications, distance, worker price, price type and tenure, including within-booking relative features.
- **Live ranking:** score the candidate group together, then combine the classifier score (70%) with a transparent score (30%) that includes skill, distance, availability, rating, experience, certifications, and workload balance. The final score is a ranking signal, not a calibrated probability.
- **Runtime data:** current worker profiles, ratings, account tenure, availability, active booking load, and requested location/schedule are read from SQLite for each customer request. The app records how many eligible candidates were considered and stores the selected candidate's features and scores with the booking.
- **Target:** `successful_completion` in the repository CSV.
- **Validation:** `train.py` groups splits by `booking_id` and uses GroupKFold within training bookings. The held-out ranking measures are in `evaluation_report.json`.
- **Current report:** ROC-AUC 0.670, NDCG@3 0.675, NDCG@5 0.765, Hit@1 0.680. These are the current artifact's numbers, not a re-run or a real-world service guarantee.
- **Risks:** the data provenance is not currently recorded; simulated or biased labels can produce misleading scores. Do not use the ranking alone to deny access to work. Show distance and experience and let cooperative policy set eligibility/fairness constraints.
- **Fallback:** if the artifact is missing or fails to load, the app uses `transparent_fair_match_v1`; responses expose the matching method and factors.

## Workforce demand

- **Purpose:** demonstrate short-horizon category-by-locality demand forecasts for capacity planning.
- **Model:** scikit-learn `HistGradientBoostingRegressor` in `forecasting.py`.
- **Data:** deterministic seeded synthetic panel generated in code (2023–2025); it is not observed booking history.
- **Validation:** last 90 calendar days are held out chronologically; the API returns MAE and RMSE.
- **Uncertainty:** the chart displays a 90th-percentile absolute residual band from synthetic holdout errors. This is not a calibrated statistical prediction interval.
- **Real-history use:** after at least 10 non-cancelled past bookings spanning 28 days exist for a service/locality, the app calibrates the synthetic model level using a 56-day daily booking history. It does not retrain the model on sparse live records.
- **Capacity heuristic:** required peak staffing = `ceil(peak predicted jobs per day / 1.5)`. The admin scan compares this with verified, available workers covering the locality and persists a recruitment alert when there is a gap. Productivity and locality-centre assumptions need validation with cooperative data.

## Responsible use

Use both features as decision support, provide understandable reasons, monitor group-level outcomes and workload distribution, and retain a human cooperative decision maker. Do not claim production accuracy from generated data.
