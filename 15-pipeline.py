"""Idempotent incident ingestion and escalation queue (SQLite demo)."""
import hashlib
import json
import sqlite3
from datetime import datetime, timezone


class IncidentQueue:
    def __init__(self, database):
        self.db = sqlite3.connect(database)
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS incidents(id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL,
                service TEXT, severity TEXT NOT NULL, status TEXT NOT NULL, payload TEXT NOT NULL,
                first_seen TEXT NOT NULL, last_seen TEXT NOT NULL, sightings INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS outbox(id INTEGER PRIMARY KEY AUTOINCREMENT, incident_id TEXT NOT NULL,
                kind TEXT NOT NULL, payload TEXT NOT NULL, created_at TEXT NOT NULL, delivered INTEGER DEFAULT 0);
        """)

    def ingest(self, incident):
        if incident.get("severity", "").upper() not in ("SEV1", "SEV2", "SEV3", "SEV4"):
            raise ValueError("Severity must be SEV1-SEV4")
        if not incident.get("id") or not incident.get("description"):
            raise ValueError("ID and description are required")
        now = datetime.now(timezone.utc).isoformat()
        fingerprint = hashlib.sha256(json.dumps({k: incident.get(k) for k in ("service", "description")}, sort_keys=True).encode()).hexdigest()
        with self.db:
            found = self.db.execute("SELECT id,sightings FROM incidents WHERE fingerprint=? AND status='OPEN'",
                                    (fingerprint,)).fetchone()
            if found:
                self.db.execute("UPDATE incidents SET sightings=sightings+1,last_seen=? WHERE id=?", (now, found[0]))
                return {"incident_id": found[0], "duplicate": True, "sightings": found[1]+1}
            if self.db.execute("SELECT id FROM incidents WHERE id=?", (incident["id"],)).fetchone():
                raise ValueError("Incident ID collision for a different event")
            self.db.execute("INSERT INTO incidents VALUES(?,?,?,?,?,?,?,?,?)",
                            (incident["id"], fingerprint, incident.get("service"), incident["severity"].upper(),
                             "OPEN", json.dumps(incident, sort_keys=True), now, now, 1))
            if incident["severity"].upper() in ("SEV1", "SEV2"):
                # Outbox only: never sends a page. An authorized external worker must deliver it.
                self.db.execute("INSERT INTO outbox(incident_id,kind,payload,created_at) VALUES(?,?,?,?)",
                                (incident["id"], "HUMAN_ESCALATION", json.dumps({"service":incident.get("service"),
                                  "severity":incident["severity"].upper()}), now))
            return {"incident_id": incident["id"], "duplicate": False, "sightings": 1}

    def close(self):
        self.db.close()
