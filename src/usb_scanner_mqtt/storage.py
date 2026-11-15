"""Durable MQTT outbox, bounded scan history and optional product cache."""
import json
import os
import sqlite3
import threading
import time
from pathlib import Path


class Outbox:
    """Commit scans before transmission. IDs survive disconnects and restarts."""
    def __init__(self, path, history_limit=1000):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.lock = threading.Lock()
        self.history_limit = history_limit
        self.connection = sqlite3.connect(path, check_same_thread=False)
        os.chmod(path, 0o600)
        try:
            self.connection.execute("CREATE TABLE IF NOT EXISTS outbox (sequence INTEGER PRIMARY KEY AUTOINCREMENT, topic TEXT NOT NULL, payload TEXT NOT NULL)")
            self.connection.execute("CREATE TABLE IF NOT EXISTS history (sequence INTEGER PRIMARY KEY AUTOINCREMENT, scan_id TEXT UNIQUE NOT NULL, payload TEXT NOT NULL, mode TEXT NOT NULL, status TEXT NOT NULL, off_status TEXT NOT NULL, off_data TEXT, cached INTEGER NOT NULL DEFAULT 0)")
            self.connection.execute("CREATE TABLE IF NOT EXISTS lookup_jobs (scan_id TEXT PRIMARY KEY, code TEXT NOT NULL, options TEXT NOT NULL, enrich_mqtt INTEGER NOT NULL)")
            self.connection.execute("CREATE TABLE IF NOT EXISTS product_cache (code TEXT NOT NULL, language TEXT NOT NULL, expires REAL NOT NULL, status TEXT NOT NULL, data TEXT, PRIMARY KEY(code, language))")
            self._prune()
            self.connection.commit()
        except BaseException:
            self.connection.close()
            raise

    def put(self, topic, payload, options=None, record=False):
        with self.lock, self.connection:
            count = self.connection.execute("SELECT count(*) FROM outbox").fetchone()[0]
            if count >= 1000:
                raise RuntimeError("Outbox full (1000 scans). Restore MQTT before scanning more.")
            self.connection.execute("INSERT INTO outbox(topic,payload) VALUES (?,?)",
                                    (topic, json.dumps(payload, ensure_ascii=False)))
            if record:
                self._record(payload, 'mqtt', 'queued', options)

    def first(self):
        with self.lock:
            row = self.connection.execute("SELECT sequence,topic,payload FROM outbox ORDER BY sequence LIMIT 1").fetchone()
            if row and self.connection.execute("SELECT 1 FROM lookup_jobs WHERE scan_id=? AND enrich_mqtt=1", (json.loads(row[2])['scan_id'],)).fetchone():
                return None
            return row

    def remove(self, sequence):
        with self.lock, self.connection:
            row = self.connection.execute("SELECT payload FROM outbox WHERE sequence=?", (sequence,)).fetchone()
            if row:
                self.connection.execute("UPDATE history SET status='sent' WHERE scan_id=?", (json.loads(row[0])['scan_id'],))
            self.connection.execute("DELETE FROM outbox WHERE sequence=?", (sequence,))

    def count(self):
        with self.lock:
            return self.connection.execute("SELECT count(*) FROM outbox").fetchone()[0]

    def close(self):
        with self.lock:
            self.connection.close()


    def _prune(self):
        self.connection.execute("DELETE FROM history WHERE sequence NOT IN (SELECT sequence FROM history ORDER BY sequence DESC LIMIT ?)", (self.history_limit,))
        self.connection.execute("DELETE FROM lookup_jobs WHERE enrich_mqtt=0 AND scan_id NOT IN (SELECT scan_id FROM history)")

    def _record(self, payload, mode, status, options):
        enabled = bool(options and options['enabled'])
        self.connection.execute("INSERT INTO history(scan_id,payload,mode,status,off_status) VALUES (?,?,?,?,?)",
            (payload['scan_id'], json.dumps(payload, ensure_ascii=False), mode, status, 'pending' if enabled else 'disabled'))
        if enabled:
            self.connection.execute("INSERT INTO lookup_jobs VALUES (?,?,?,?)", (payload['scan_id'], payload['ean'], json.dumps(options), int(mode == 'mqtt' and options['include_mqtt'])))
        self._prune()

    def record(self, payload, mode, options=None):
        with self.lock, self.connection:
            self._record(payload, mode, 'local' if mode == 'local' else 'disabled', options)

    def history(self, limit=100, offset=0):
        with self.lock:
            rows = self.connection.execute("SELECT payload,mode,status,off_status,off_data,cached FROM history ORDER BY sequence DESC LIMIT ? OFFSET ?", (limit, offset)).fetchall()
        from .open_facts import display_product
        result = []
        for raw, mode, status, off_status, data, cached in reversed(rows):
            payload = json.loads(raw)
            result.append(dict(id=payload['scan_id'], text=payload['ean'], timestamp=payload['timestamp'],
                length=len(payload['ean']) if payload['ean'] is not None else 0, mode=mode, status=status,
                off_status=off_status, off_data=display_product(json.loads(data)) if data else None, off_cached=bool(cached)))
        return result

    def history_count(self):
        with self.lock:
            return self.connection.execute("SELECT count(*) FROM history").fetchone()[0]

    def clear_history(self, scan_id=None):
        with self.lock, self.connection:
            if scan_id is None:
                self.connection.execute("DELETE FROM history")
            else:
                self.connection.execute("DELETE FROM history WHERE scan_id=?", (scan_id,))
            # Pending MQTT jobs survive deleting their display entries.
            self.connection.execute("DELETE FROM lookup_jobs WHERE enrich_mqtt=0 AND scan_id NOT IN (SELECT scan_id FROM history)")

    def next_job(self):
        with self.lock:
            row = self.connection.execute("SELECT scan_id,code,options FROM lookup_jobs ORDER BY rowid LIMIT 1").fetchone()
            return (row[0], row[1], json.loads(row[2])) if row else None

    def finish_job(self, scan_id, status, data, cached=False):
        with self.lock, self.connection:
            job = self.connection.execute("SELECT enrich_mqtt FROM lookup_jobs WHERE scan_id=?", (scan_id,)).fetchone()
            if not job:
                return
            self.connection.execute("UPDATE history SET off_status=?,off_data=?,cached=? WHERE scan_id=?", (status, json.dumps(data, ensure_ascii=False), int(cached), scan_id))
            if job[0]:
                rows = self.connection.execute("SELECT sequence,payload FROM outbox").fetchall()
                for sequence, raw in rows:
                    payload = json.loads(raw)
                    if payload['scan_id'] == scan_id:
                        payload.update(off_status=status, off_data=data)
                        self.connection.execute("UPDATE outbox SET payload=? WHERE sequence=?", (json.dumps(payload, ensure_ascii=False), sequence))
                        break
            self.connection.execute("DELETE FROM lookup_jobs WHERE scan_id=?", (scan_id,))

    def cached(self, code, language):
        with self.lock:
            row = self.connection.execute("SELECT status,data FROM product_cache WHERE code=? AND language=? AND expires>?", (code, language, time.time())).fetchone()
        return (row[0], json.loads(row[1])) if row else None

    def cache(self, code, language, status, data, ttl):
        with self.lock, self.connection:
            self.connection.execute("INSERT OR REPLACE INTO product_cache VALUES (?,?,?,?,?)", (code, language, time.time()+ttl, status, json.dumps(data, ensure_ascii=False)))
            self.connection.execute("DELETE FROM product_cache WHERE expires<?", (time.time(),))
            self.connection.execute("DELETE FROM product_cache WHERE rowid NOT IN (SELECT rowid FROM product_cache ORDER BY expires DESC LIMIT 5000)")

    def clear_cache(self):
        with self.lock, self.connection:
            self.connection.execute("DELETE FROM product_cache")
