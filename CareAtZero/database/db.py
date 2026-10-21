import sqlite3
import os
import json
from typing import List, Dict, Any, Optional

DB_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(DB_DIR, "care_at_zero.db")


def get_connection(db_path: str = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: str = DB_PATH) -> None:
    """Initialize database tables with complete schema according to specification."""
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    with get_connection(db_path) as conn:
        cursor = conn.cursor()

        # 1. Sources table - Provenance and freshness tracking
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sources (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                source_url TEXT NOT NULL,
                source_type TEXT NOT NULL, -- e.g. HRSA, NAFC, Mobile_Care_Network, Local_Health_Dept
                last_checked TEXT NOT NULL,
                status TEXT NOT NULL -- active, stale, unavailable
            );
        """)

        # 2. Care Sites table - Permanent free and safety-net clinics
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS care_sites (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                type TEXT NOT NULL, -- permanent, fqhc, free_clinic, hospital_charity
                address TEXT NOT NULL,
                city TEXT NOT NULL,
                state TEXT NOT NULL,
                zip_code TEXT NOT NULL,
                latitude REAL,
                longitude REAL,
                phone TEXT NOT NULL,
                website TEXT NOT NULL,
                services TEXT NOT NULL, -- JSON list of services, e.g. ["Medical", "Dental"]
                cost_class TEXT NOT NULL, -- Free, Very Low Cost, Sliding Scale
                uninsured_acceptance TEXT NOT NULL, -- Yes, Priority, All Welcome
                eligibility TEXT NOT NULL,
                documents_required TEXT NOT NULL, -- JSON list of required docs
                hours_summary TEXT NOT NULL,
                appointment_rule TEXT NOT NULL, -- Walk-in welcome, Appointment required, Call ahead
                source_id TEXT NOT NULL,
                notes TEXT,
                FOREIGN KEY (source_id) REFERENCES sources (id)
            );
        """)

        # 3. Care Events table - Time-sensitive mobile and pop-up clinics
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS care_events (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                provider_id TEXT,
                organizer_name TEXT NOT NULL,
                date_start TEXT NOT NULL, -- ISO YYYY-MM-DD
                date_end TEXT NOT NULL, -- ISO YYYY-MM-DD
                time_details TEXT NOT NULL,
                recurring_rule TEXT, -- e.g., "1st and 3rd Saturday monthly" or null
                location_name TEXT NOT NULL,
                address TEXT NOT NULL,
                city TEXT NOT NULL,
                state TEXT NOT NULL,
                zip_code TEXT NOT NULL,
                latitude REAL,
                longitude REAL,
                services TEXT NOT NULL, -- JSON list
                cost_class TEXT NOT NULL, -- Free, Very Low Cost
                eligibility TEXT NOT NULL,
                appointment_rule TEXT NOT NULL, -- First come first served, Pre-registration required
                documents_required TEXT NOT NULL, -- JSON list
                phone TEXT,
                source_id TEXT NOT NULL,
                is_active INTEGER DEFAULT 1,
                FOREIGN KEY (source_id) REFERENCES sources (id)
            );
        """)

        conn.commit()


# Helper query functions

def insert_source(source_dict: Dict[str, Any], db_path: str = DB_PATH) -> None:
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO sources (id, name, source_url, source_type, last_checked, status)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            source_dict["id"],
            source_dict["name"],
            source_dict["source_url"],
            source_dict["source_type"],
            source_dict["last_checked"],
            source_dict.get("status", "active")
        ))
        conn.commit()


def insert_care_site(site_dict: Dict[str, Any], db_path: str = DB_PATH) -> None:
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        services_json = json.dumps(site_dict.get("services", []))
        docs_json = json.dumps(site_dict.get("documents_required", []))
        cursor.execute("""
            INSERT OR REPLACE INTO care_sites (
                id, name, type, address, city, state, zip_code, latitude, longitude,
                phone, website, services, cost_class, uninsured_acceptance,
                eligibility, documents_required, hours_summary, appointment_rule,
                source_id, notes
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            site_dict["id"],
            site_dict["name"],
            site_dict["type"],
            site_dict["address"],
            site_dict["city"],
            site_dict["state"],
            site_dict["zip_code"],
            site_dict.get("latitude"),
            site_dict.get("longitude"),
            site_dict["phone"],
            site_dict["website"],
            services_json,
            site_dict["cost_class"],
            site_dict.get("uninsured_acceptance", "Yes"),
            site_dict["eligibility"],
            docs_json,
            site_dict["hours_summary"],
            site_dict["appointment_rule"],
            site_dict["source_id"],
            site_dict.get("notes", "")
        ))
        conn.commit()


def insert_care_event(event_dict: Dict[str, Any], db_path: str = DB_PATH) -> None:
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        services_json = json.dumps(event_dict.get("services", []))
        docs_json = json.dumps(event_dict.get("documents_required", []))
        cursor.execute("""
            INSERT OR REPLACE INTO care_events (
                id, title, provider_id, organizer_name, date_start, date_end,
                time_details, recurring_rule, location_name, address, city,
                state, zip_code, latitude, longitude, services, cost_class,
                eligibility, appointment_rule, documents_required, phone,
                source_id, is_active
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            event_dict["id"],
            event_dict["title"],
            event_dict.get("provider_id"),
            event_dict["organizer_name"],
            event_dict["date_start"],
            event_dict["date_end"],
            event_dict["time_details"],
            event_dict.get("recurring_rule"),
            event_dict["location_name"],
            event_dict["address"],
            event_dict["city"],
            event_dict["state"],
            event_dict["zip_code"],
            event_dict.get("latitude"),
            event_dict.get("longitude"),
            services_json,
            event_dict["cost_class"],
            event_dict["eligibility"],
            event_dict["appointment_rule"],
            docs_json,
            event_dict.get("phone", ""),
            event_dict["source_id"],
            event_dict.get("is_active", 1)
        ))
        conn.commit()


def get_all_sites(db_path: str = DB_PATH) -> List[Dict[str, Any]]:
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT s.*, src.name as source_name, src.source_url, src.last_checked, src.status as source_status
            FROM care_sites s
            LEFT JOIN sources src ON s.source_id = src.id
        """)
        rows = cursor.fetchall()
        results = []
        for row in rows:
            d = dict(row)
            d["services"] = json.loads(d["services"]) if isinstance(d["services"], str) else d["services"]
            d["documents_required"] = json.loads(d["documents_required"]) if isinstance(d["documents_required"], str) else d["documents_required"]
            d["record_type"] = "site"
            results.append(d)
        return results


def get_all_events(include_expired: bool = False, current_date_str: Optional[str] = None, db_path: str = DB_PATH) -> List[Dict[str, Any]]:
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        query = """
            SELECT e.*, src.name as source_name, src.source_url, src.last_checked, src.status as source_status
            FROM care_events e
            LEFT JOIN sources src ON e.source_id = src.id
            WHERE e.is_active = 1
        """
        params = []
        if not include_expired and current_date_str:
            query += " AND e.date_end >= ?"
            params.append(current_date_str)

        cursor.execute(query, params)
        rows = cursor.fetchall()
        results = []
        for row in rows:
            d = dict(row)
            d["services"] = json.loads(d["services"]) if isinstance(d["services"], str) else d["services"]
            d["documents_required"] = json.loads(d["documents_required"]) if isinstance(d["documents_required"], str) else d["documents_required"]
            d["record_type"] = "event"
            results.append(d)
        return results


def get_site_by_id(site_id: str, db_path: str = DB_PATH) -> Optional[Dict[str, Any]]:
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT s.*, src.name as source_name, src.source_url, src.last_checked, src.status as source_status
            FROM care_sites s
            LEFT JOIN sources src ON s.source_id = src.id
            WHERE s.id = ?
        """, (site_id,))
        row = cursor.fetchone()
        if row:
            d = dict(row)
            d["services"] = json.loads(d["services"]) if isinstance(d["services"], str) else d["services"]
            d["documents_required"] = json.loads(d["documents_required"]) if isinstance(d["documents_required"], str) else d["documents_required"]
            d["record_type"] = "site"
            return d
        return None


def get_event_by_id(event_id: str, db_path: str = DB_PATH) -> Optional[Dict[str, Any]]:
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT e.*, src.name as source_name, src.source_url, src.last_checked, src.status as source_status
            FROM care_events e
            LEFT JOIN sources src ON e.source_id = src.id
            WHERE e.id = ?
        """, (event_id,))
        row = cursor.fetchone()
        if row:
            d = dict(row)
            d["services"] = json.loads(d["services"]) if isinstance(d["services"], str) else d["services"]
            d["documents_required"] = json.loads(d["documents_required"]) if isinstance(d["documents_required"], str) else d["documents_required"]
            d["record_type"] = "event"
            return d
        return None
