"""Process-local runtime state initialized by the application lifespan."""
from forecasting import DemandForecaster

forecaster: DemandForecaster | None = None
