"""SQLite persistence and demo seed data for the FixMate prototype."""
from __future__ import annotations

import hashlib
import os
import secrets
import sqlite3
from pathlib import Path

DB_PATH = Path(os.getenv("FIXMATE_DB_PATH", Path(__file__).with_name("fixmate.db")))


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB_PATH, timeout=15)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    db.execute("PRAGMA journal_mode = WAL")
    return db


def hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    key = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 240_000)
    return f"{salt.hex()}:{key.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        salt_hex, key_hex = stored.split(":", 1)
        actual = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), 240_000)
        return secrets.compare_digest(actual.hex(), key_hex)
    except (ValueError, TypeError):
        return False


def init_db() -> None:
    with connect() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS users (
          id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, email TEXT NOT NULL UNIQUE,
          phone TEXT NOT NULL DEFAULT '', password_hash TEXT NOT NULL,
          role TEXT NOT NULL CHECK(role IN ('customer','worker','admin')),
          language TEXT NOT NULL DEFAULT 'en', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS services(name TEXT PRIMARY KEY, description TEXT, base_rate REAL, icon TEXT);
        CREATE TABLE IF NOT EXISTS workers (
          user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
          skills TEXT NOT NULL DEFAULT '[]', experience_years REAL NOT NULL DEFAULT 0,
          certifications TEXT NOT NULL DEFAULT '[]', verified INTEGER NOT NULL DEFAULT 0,
          available INTEGER NOT NULL DEFAULT 1, hourly_rate REAL NOT NULL DEFAULT 350,
          price_type TEXT NOT NULL DEFAULT 'per_visit', society TEXT NOT NULL DEFAULT 'FixMate Cooperative',
          latitude REAL NOT NULL DEFAULT 28.4595, longitude REAL NOT NULL DEFAULT 77.0266,
          radius_km REAL NOT NULL DEFAULT 15, bio TEXT NOT NULL DEFAULT '',
          welfare_status TEXT NOT NULL DEFAULT 'enrolled'
        );
        CREATE TABLE IF NOT EXISTS bookings (
          id INTEGER PRIMARY KEY AUTOINCREMENT, customer_id INTEGER NOT NULL REFERENCES users(id),
          worker_id INTEGER REFERENCES users(id), service TEXT NOT NULL, description TEXT NOT NULL DEFAULT '',
          scheduled_at TEXT NOT NULL, address TEXT NOT NULL, latitude REAL NOT NULL, longitude REAL NOT NULL,
          emergency INTEGER NOT NULL DEFAULT 0, quantity INTEGER NOT NULL DEFAULT 1,
          status TEXT NOT NULL DEFAULT 'requested', payment_method TEXT NOT NULL DEFAULT 'cash',
          payment_status TEXT NOT NULL DEFAULT 'unpaid', quoted_amount REAL NOT NULL,
          model_score REAL, match_method TEXT, match_factors TEXT NOT NULL DEFAULT '{}',
          eligible_workers_count INTEGER NOT NULL DEFAULT 0,
          match_features TEXT NOT NULL DEFAULT '{}',
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS reviews (
          id INTEGER PRIMARY KEY AUTOINCREMENT, booking_id INTEGER NOT NULL UNIQUE REFERENCES bookings(id),
          customer_id INTEGER NOT NULL REFERENCES users(id), worker_id INTEGER NOT NULL REFERENCES users(id),
          rating INTEGER NOT NULL CHECK(rating BETWEEN 1 AND 5), comment TEXT NOT NULL DEFAULT '',
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS payments (
          id INTEGER PRIMARY KEY AUTOINCREMENT, booking_id INTEGER NOT NULL UNIQUE REFERENCES bookings(id),
          amount REAL NOT NULL, method TEXT NOT NULL, status TEXT NOT NULL, reference TEXT NOT NULL,
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS admin_alerts (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          service TEXT NOT NULL, locality TEXT NOT NULL,
          forecast_start TEXT NOT NULL, forecast_end TEXT NOT NULL,
          predicted_jobs REAL NOT NULL, workers_required INTEGER NOT NULL,
          available_workers INTEGER NOT NULL, worker_gap INTEGER NOT NULL,
          data_source TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'open',
          recruitment_status TEXT NOT NULL DEFAULT 'not_started',
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          UNIQUE(service, locality, forecast_start, forecast_end)
        );
        CREATE INDEX IF NOT EXISTS idx_booking_customer ON bookings(customer_id, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_booking_worker ON bookings(worker_id, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_booking_status ON bookings(status);
        """)
        booking_columns = {row["name"] for row in db.execute("PRAGMA table_info(bookings)")}
        if "match_method" not in booking_columns:
            db.execute("ALTER TABLE bookings ADD COLUMN match_method TEXT")
        if "match_factors" not in booking_columns:
            db.execute("ALTER TABLE bookings ADD COLUMN match_factors TEXT NOT NULL DEFAULT '{}'")
        if "eligible_workers_count" not in booking_columns:
            db.execute("ALTER TABLE bookings ADD COLUMN eligible_workers_count INTEGER NOT NULL DEFAULT 0")
        if "match_features" not in booking_columns:
            db.execute("ALTER TABLE bookings ADD COLUMN match_features TEXT NOT NULL DEFAULT '{}'")
        services = [
          ("Plumbing", "Leaks, taps, fittings", 350, "🔧"), ("Electrical", "Wiring, fans, repairs", 400, "⚡"),
          ("Carpentry", "Furniture and woodwork", 450, "🪚"), ("Painting", "Walls and touch-ups", 500, "🖌️"),
          ("Cleaning", "Home and deep cleaning", 300, "🧹"), ("Caregiving", "Companionship and care", 450, "💛"),
          ("Driving", "Local and scheduled trips", 400, "🚗"), ("Gardening", "Plants and outdoor care", 300, "🌿"),
          ("Technician", "Appliance and equipment repair", 450, "🧰")]
        db.executemany("INSERT OR IGNORE INTO services VALUES(?,?,?,?)", services)
        if db.execute("SELECT COUNT(*) FROM users").fetchone()[0]:
            return

        admin_email = os.getenv("FIXMATE_ADMIN_EMAIL", "admin@fixmate.local").lower()
        db.execute("INSERT INTO users(name,email,phone,password_hash,role) VALUES(?,?,?,?,?)",
                   ("Cooperative Admin", admin_email, "9876543210", hash_password(admin_password), "admin"))
        demo_workers = [
          ("Ravi Kumar", "ravi@fixmate.local", "9876500001", ["Plumbing", "Technician"], 9.0, ["ITI Plumbing"], 1, 420, 28.4590, 77.0260, 4.2),
          ("Meena Devi", "meena@fixmate.local", "9876500002", ["Cleaning", "Caregiving"], 7.0, ["First Aid"], 1, 350, 28.4660, 77.0350, 4.9),
          ("Amit Singh", "amit@fixmate.local", "9876500003", ["Electrical", "Technician"], 12.0, ["ITI Electrical", "Safety"], 1, 480, 28.4480, 77.0180, 4.7),
          ("Sana Khan", "sana@fixmate.local", "9876500004", ["Painting", "Carpentry"], 5.0, ["Skill India Carpentry"], 1, 460, 28.4720, 77.0200, 4.8),
          ("Dev Raj", "dev@fixmate.local", "9876500005", ["Gardening", "Cleaning"], 4.0, [], 1, 320, 28.4510, 77.0400, 4.4),
          ("Pooja Sharma", "pooja@fixmate.local", "9876500006", ["Caregiving", "Cleaning"], 6.0, ["Elder Care"], 0, 390, 28.4620, 77.0110, 4.6),
          ("Imran Ali", "imran@fixmate.local", "9876500007", ["Driving", "Technician"], 8.0, ["Commercial Driving"], 1, 430, 28.4430, 77.0300, 4.5)]
        for name, email, phone, skills, exp, certs, verified, rate, lat, lon, _rating in demo_workers:
            cur = db.execute("INSERT INTO users(name,email,phone,password_hash,role) VALUES(?,?,?,?,?)",
                             (name, email, phone, hash_password("worker123"), "worker"))
            db.execute("INSERT INTO workers(user_id,skills,experience_years,certifications,verified,hourly_rate,latitude,longitude) VALUES(?,?,?,?,?,?,?,?)",
                       (cur.lastrowid, __import__("json").dumps(skills), exp, __import__("json").dumps(certs), verified, rate, lat, lon))
        customer = db.execute("INSERT INTO users(name,email,phone,password_hash,role) VALUES(?,?,?,?,?)",
                              ("Demo Customer", "customer@fixmate.local", "9876500000", hash_password("customer123"), "customer"))
        # Worker sample accounts are accessible for role workflows. Demo worker passwords: worker123.
        db.commit()
