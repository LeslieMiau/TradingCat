import json

from tradingcat.repositories.postgres_store import PostgresStore


class _FakeCursor:
    def __init__(self, connection):
        self.connection = connection
        self._result = None
        self._rows = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, query, params=None):
        normalized = " ".join(query.split()).upper()
        self.connection.queries.append((query, params))
        if normalized.startswith("SELECT PAYLOAD FROM STATE_BUCKETS"):
            bucket = params[0]
            self._result = (json.loads(self.connection.storage[bucket]),) if bucket in self.connection.storage else None
        elif normalized.startswith("INSERT INTO STATE_BUCKETS"):
            bucket, payload = params
            self.connection.storage[bucket] = payload
        elif normalized.startswith("INSERT INTO AUDIT_LOG"):
            self.connection.audit.append(params)
        elif normalized.startswith("SELECT BUCKET, ACTION, PAYLOAD FROM AUDIT_LOG WHERE BUCKET = %S"):
            bucket, limit = params
            rows = [row for row in self.connection.audit if row[0] == bucket]
            self._rows = [(row[0], row[1], json.loads(row[2])) for row in rows[-int(limit):]][::-1]
        elif normalized.startswith("SELECT BUCKET, ACTION, PAYLOAD FROM AUDIT_LOG"):
            limit = params[0]
            rows = list(self.connection.audit)
            self._rows = [(row[0], row[1], json.loads(row[2])) for row in rows[-int(limit):]][::-1]

    def fetchone(self):
        return self._result

    def fetchall(self):
        return self._rows


class _FakeConnection:
    def __init__(self):
        self.storage = {}
        self.audit = []
        self.queries = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def cursor(self):
        return _FakeCursor(self)


def test_postgres_store_load_and_save_round_trip():
    connection = _FakeConnection()
    store = PostgresStore("postgresql:///test", connector=lambda dsn: connection)

    assert store.load("orders", []) == []

    store.save("orders", [{"id": "1"}])

    assert store.load("orders", []) == [{"id": "1"}]
    assert len(connection.audit) == 1


def test_postgres_store_append_and_list_audit():
    connection = _FakeConnection()
    store = PostgresStore("postgresql:///test", connector=lambda dsn: connection)

    store.append_audit("audit_events", "manual", {"id": "1"})

    events = store.list_audit("audit_events", limit=10)

    assert len(events) == 1
    assert events[0]["action"] == "manual"
