"""Application paths and environment-backed configuration."""
from pathlib import Path
import os

ROOT = Path(__file__).resolve().parent.parent
MODEL_PATH = ROOT / "model.joblib"
