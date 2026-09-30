"""Application paths and environment-backed configuration."""
from pathlib import Path
import os

ROOT = Path(__file__).resolve().parent.parent
TOKEN_SECRET = os.getenv("FIXMATE_TOKEN_SECRET", "local-demo-secret-change-before-hosting").encode()
MODEL_PATH = ROOT / "model.joblib"
