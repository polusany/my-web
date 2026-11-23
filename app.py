from __future__ import annotations

import csv
import datetime
import hmac
import json
import math
import os
import re
import secrets
import sqlite3
import time
from collections import Counter, defaultdict
from contextlib import contextmanager
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
DATA_PATH = ROOT / "data" / "nigeria_houses_data.csv"
WEB_ROOT = ROOT / "static"
DATA_DIR = Path(os.environ.get("MOSHELTER_DATA_DIR", str(ROOT))).expanduser()
DATA_DIR.mkdir(parents=True, exist_ok=True)
INVENTORY_DB_PATH = DATA_DIR / "shelter_inventory.sqlite3"
MIN_STATE_LISTINGS = 50
NUMERIC_FIELDS = ("bedrooms", "bathrooms", "toilets", "parking_space")
NIGERIAN_STATES = {
    "Abia", "Adamawa", "Akwa Ibom", "Anambra", "Bauchi", "Bayelsa", "Benue", "Borno",
    "Cross River", "Delta", "Ebonyi", "Edo", "Ekiti", "Enugu", "Abuja", "Federal Capital Territory",
    "Gombe", "Imo", "Jigawa", "Kaduna", "Kano", "Katsina", "Kebbi", "Kogi", "Kwara",
    "Lagos", "Nasarawa", "Niger", "Ogun", "Ondo", "Osun", "Oyo", "Plateau", "Rivers",
    "Sokoto", "Taraba", "Yobe", "Zamfara",
}
STATE_LOOKUP = {state.casefold(): state for state in NIGERIAN_STATES}
STATE_ALIASES = {"anambara": "Anambra"}
ADMIN_SESSIONS = {}
ADMIN_SESSION_TTL = 8 * 60 * 60


@contextmanager
def inventory_connection():
    connection = sqlite3.connect(INVENTORY_DB_PATH, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def initialize_inventory():
    with inventory_connection() as connection:
        connection.executescript("""
            CREATE TABLE IF NOT EXISTS homes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                state TEXT NOT NULL,
                town TEXT NOT NULL,
                property_type TEXT NOT NULL,
                transaction_type TEXT NOT NULL DEFAULT 'sale',
                rent_frequency TEXT NOT NULL DEFAULT 'monthly',
                price INTEGER NOT NULL CHECK (price > 0),
                bedrooms INTEGER NOT NULL CHECK (bedrooms >= 0),
                bathrooms INTEGER NOT NULL CHECK (bathrooms >= 0),
                toilets INTEGER NOT NULL CHECK (toilets >= 0),
                parking_space INTEGER NOT NULL CHECK (parking_space >= 0),
                description TEXT NOT NULL,
                image_url TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'available' CHECK (status IN ('available','unavailable')),
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS tour_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                home_id INTEGER NOT NULL REFERENCES homes(id),
                name TEXT NOT NULL,
                email TEXT NOT NULL,
                phone TEXT NOT NULL,
                preferred_at TEXT NOT NULL,
                tour_type TEXT NOT NULL CHECK (tour_type IN ('in_person','virtual')),
                note TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'requested' CHECK (status IN ('requested','confirmed','completed','cancelled')),
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS homes_status_created ON homes(status, created_at DESC);
            CREATE INDEX IF NOT EXISTS tours_created ON tour_requests(created_at DESC);
        """)
        home_columns = {row["name"] for row in connection.execute("PRAGMA table_info(homes)")}
        if "transaction_type" not in home_columns:
            connection.execute("ALTER TABLE homes ADD COLUMN transaction_type TEXT NOT NULL DEFAULT 'sale'")
        if "rent_frequency" not in home_columns:
            connection.execute("ALTER TABLE homes ADD COLUMN rent_frequency TEXT NOT NULL DEFAULT 'monthly'")


def bounded_text(value, label, limit, required=True):
    if not isinstance(value, str):
        raise ValueError(f"Enter a valid {label}.")
    value = " ".join(value.split())
    if (required and not value) or len(value) > limit:
        raise ValueError(f"{label.capitalize()} is required and must be under {limit} characters.")
    return value


def validated_home(payload):
    if not isinstance(payload, dict):
        raise ValueError("Enter the property details.")
    result = {
        "title": bounded_text(payload.get("title"), "listing title", 100),
        "state": bounded_text(payload.get("state"), "state", 40),
        "town": bounded_text(payload.get("town"), "town or area", 80),
        "property_type": bounded_text(payload.get("property_type"), "property type", 80),
        "transaction_type": payload.get("transaction_type", "sale"),
        "rent_frequency": payload.get("rent_frequency", "monthly"),
        "description": bounded_text(payload.get("description"), "description", 1600),
        "image_url": bounded_text(payload.get("image_url", ""), "photo URL", 500, required=False),
        "status": payload.get("status", "available"),
    }
    if result["state"] not in DATASET_STATES:
        raise ValueError("Choose a state or Abuja location represented in the current dataset.")
    if not isinstance(result["status"], str) or result["status"] not in {"available", "unavailable"}:
        raise ValueError("Choose whether the listing is available or unavailable.")
    if not isinstance(result["transaction_type"], str) or result["transaction_type"] not in {"sale", "rent"}:
        raise ValueError("Choose whether this property is for sale or rent.")
    if not isinstance(result["rent_frequency"], str) or result["rent_frequency"] not in {"monthly", "yearly"}:
        raise ValueError("Choose monthly or yearly rent.")
    if result["image_url"]:
        image = urlparse(result["image_url"])
        if image.scheme != "https" or not image.netloc:
            raise ValueError("Photo URL must start with https://")
    price = payload.get("price")
    if isinstance(price, bool) or not isinstance(price, (int, float)) or not float(price).is_integer() or price <= 0 or price > 100_000_000_000:
        raise ValueError("Enter a price between ₦1 and ₦100 billion.")
    result["price"] = int(price)
    for field in NUMERIC_FIELDS:
        value = payload.get(field)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not float(value).is_integer() or value < 0 or value > 30:
            raise ValueError("Room and parking counts must be whole numbers from 0 to 30.")
        result[field] = int(value)
    return result


def validate_tour(payload):
    if not isinstance(payload, dict):
        raise ValueError("Enter your tour request details.")
    name = bounded_text(payload.get("name"), "name", 80)
    email = bounded_text(payload.get("email"), "email", 254)
    phone = bounded_text(payload.get("phone"), "phone number", 30)
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
        raise ValueError("Enter a valid email address.")
    if len(re.sub(r"\D", "", phone)) < 7:
        raise ValueError("Enter a phone number with at least 7 digits.")
    preferred_at = bounded_text(payload.get("preferred_at"), "preferred tour date and time", 30)
    try:
        requested_time = datetime.datetime.fromisoformat(preferred_at)
    except ValueError as error:
        raise ValueError("Choose a valid tour date and time.") from error
    if requested_time.tzinfo is not None:
        raise ValueError("Choose the tour time in your local time zone.")
    if requested_time <= datetime.datetime.now():
        raise ValueError("Choose a future date and time for the tour.")
    tour_type = payload.get("tour_type")
    if not isinstance(tour_type, str) or tour_type not in {"in_person", "virtual"}:
        raise ValueError("Choose an in-person or virtual tour.")
    note = bounded_text(payload.get("note", ""), "note", 600, required=False)
    home_id = payload.get("home_id")
    if isinstance(home_id, bool) or not isinstance(home_id, int) or home_id < 1:
        raise ValueError("Choose an available property listing.")
    return {"home_id": home_id, "name": name, "email": email, "phone": phone,
            "preferred_at": requested_time.isoformat(timespec="minutes"), "tour_type": tour_type, "note": note}


initialize_inventory()


def number(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def load_listings():
    rows, seen = [], set()
    with DATA_PATH.open("r", encoding="utf-8-sig", newline="") as handle:
        for raw in csv.DictReader(handle):
            raw_state = (raw.get("state") or "").strip()
            state = STATE_ALIASES.get(raw_state.casefold(), STATE_LOOKUP.get(raw_state.casefold(), raw_state))
            if state not in NIGERIAN_STATES:
                continue
            record = {"state": state, "town": (raw.get("town") or "").strip(),
                      "title": (raw.get("title") or "").strip()}
            for field in NUMERIC_FIELDS:
                record[field] = number(raw.get(field))
            record["price"] = number(raw.get("price"))
            if not record["town"] or not record["title"] or record["price"] is None or record["price"] <= 0:
                continue
            if any(record[field] is None or record[field] < 0 for field in NUMERIC_FIELDS):
                continue
            key = tuple(record[field] for field in ("state", "town", "title", *NUMERIC_FIELDS, "price"))
            if key in seen:
                continue
            seen.add(key)
            rows.append(record)
    return rows


ALL_VALID_LISTINGS = load_listings()
STATE_LISTING_COUNTS = Counter(row["state"] for row in ALL_VALID_LISTINGS)
DATASET_STATES = set(STATE_LISTING_COUNTS)
ALLOWED_STATES = {state for state, count in STATE_LISTING_COUNTS.items() if count >= MIN_STATE_LISTINGS}
LISTINGS = [row for row in ALL_VALID_LISTINGS if row["state"] in ALLOWED_STATES]
TOWNS = defaultdict(set)
TYPES = set()
for row in LISTINGS:
    TOWNS[row["state"]].add(row["town"])
    TYPES.add(row["title"])


def weighted_median(items):
    items.sort(key=lambda item: item[0])
    total = sum(weight for _, weight in items)
    halfway, accumulated = total / 2, 0.0
    for price, weight in items:
        accumulated += weight
        if accumulated >= halfway:
            return price
    return items[-1][0]


def weighted_quantile(items, quantile):
    """Return a price percentile from the weighted comparable listings."""
    ordered = sorted(items, key=lambda item: item[0])
    total = sum(weight for _, weight in ordered)
    threshold = total * quantile
    accumulated = 0.0
    for price, weight in ordered:
        accumulated += weight
        if accumulated >= threshold:
            return price
    return ordered[-1][0]


def predict(query, source=LISTINGS):
    state, town, title = query["state"], query["town"], query["title"]
    if state not in ALLOWED_STATES or town not in TOWNS.get(state, set()) or title not in TYPES:
        raise ValueError("Choose a supported location and property type.")
    for field in NUMERIC_FIELDS:
        value = query.get(field)
        if not isinstance(value, (int, float)) or isinstance(value, bool) or not float(value).is_integer() or value < 0 or value > 20:
            raise ValueError("Enter room and parking counts from 0 to 20.")

    candidates = [row for row in source if row["state"] == state]
    scored = []
    scales = {"bedrooms": 4.0, "bathrooms": 4.0, "toilets": 4.0, "parking_space": 4.0}
    for row in candidates:
        # Different towns and home types are less comparable. Room-count gaps
        # are scaled so one extra room does not overwhelm the location signal.
        distance = (0.0 if row["town"] == town else 1.65)
        distance += 0.0 if row["title"] == title else 1.1
        for field in NUMERIC_FIELDS:
            distance += abs(row[field] - query[field]) / scales[field]
        scored.append((distance, row))
    scored.sort(key=lambda pair: pair[0])
    chosen = scored[:100]
    if len(chosen) < 8:
        raise ValueError("There are not enough comparable listings for this combination yet.")
    values = []
    for distance, row in chosen:
        weight = math.exp(-1.5 * distance)
        values.append((row["price"], weight))
    lower_comparable_price = weighted_quantile(values, 0.2)
    upper_comparable_price = weighted_quantile(values, 0.8)
    estimate = weighted_median(values)
    same_town = sum(row["town"] == town for _, row in chosen)
    same_type = sum(row["title"] == title for _, row in chosen)
    same_town_and_type = sum(
        row["town"] == town and row["title"] == title for _, row in chosen
    )
    if same_town >= 25 and same_type >= 25:
        match = "many similar listings in this town and property type"
    elif same_town >= 10:
        match = "similar listings in this town, with some broader comparisons"
    else:
        match = "broader listings across the selected state"
    return {"estimate": round(estimate / 1_000_000) * 1_000_000,
            "rangeLow": round(lower_comparable_price / 1_000_000) * 1_000_000,
            "rangeHigh": round(upper_comparable_price / 1_000_000) * 1_000_000,
            "comparables": len(chosen), "match": match,
            "sameTownComparables": same_town,
            "sameTypeComparables": same_type,
            "sameTownAndTypeComparables": same_town_and_type}


class Handler(BaseHTTPRequestHandler):
    def send_json(self, payload, status=200, headers=()):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for name, value in headers:
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)

    def read_json(self, maximum=20000):
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0 or length > maximum:
            raise ValueError("Please submit the form again with valid details.")
        payload = json.loads(self.rfile.read(length))
        if not isinstance(payload, dict):
            raise ValueError("Please submit valid details.")
        return payload

    def same_origin(self):
        origin = self.headers.get("Origin")
        if not origin:
            return True
        return urlparse(origin).netloc.casefold() == self.headers.get("Host", "").casefold()

    def admin_authenticated(self):
        cookie = SimpleCookie()
        try:
            cookie.load(self.headers.get("Cookie", ""))
            session = cookie.get("shelter_admin")
        except Exception:
            session = None
        if not session:
            return False
        expires = ADMIN_SESSIONS.get(session.value, 0)
        if expires <= time.time():
            ADMIN_SESSIONS.pop(session.value, None)
            return False
        return True

    def require_admin(self):
        if not self.admin_authenticated():
            self.send_json({"error": "Sign in as a Moshelter administrator to continue."}, 401)
            return False
        return True

    def serve_file(self, file_path):
        try:
            body = file_path.read_bytes()
        except (OSError, ValueError):
            self.send_error(404)
            return
        content_type = {
            ".css": "text/css; charset=utf-8",
            ".js": "application/javascript; charset=utf-8",
            ".html": "text/html; charset=utf-8",
        }.get(file_path.suffix, "application/octet-stream")
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        if file_path.name == "admin.html":
            self.send_header("Cache-Control", "no-store, private")
        self.end_headers()
        self.wfile.write(body)

    def get_public_homes(self, home_id=None):
        with inventory_connection() as connection:
            if home_id is None:
                rows = connection.execute(
                    "SELECT * FROM homes WHERE status='available' ORDER BY created_at DESC, id DESC LIMIT 200"
                ).fetchall()
            else:
                rows = connection.execute(
                    "SELECT * FROM homes WHERE id=? AND status='available'", (home_id,)
                ).fetchone()
        if home_id is None:
            return [dict(row) for row in rows if row["state"] in DATASET_STATES]
        return dict(rows) if rows and rows["state"] in DATASET_STATES else None

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/api/homes":
            return self.send_json({"homes": self.get_public_homes()})
        home_match = re.fullmatch(r"/api/homes/(\d+)", path)
        if home_match:
            home = self.get_public_homes(int(home_match.group(1)))
            if not home:
                return self.send_json({"error": "This home is not currently available."}, 404)
            return self.send_json(home)
        if path == "/api/admin/status":
            return self.send_json({"configured": bool(os.environ.get("MOSHELTER_ADMIN_PASSWORD") or os.environ.get("SHELTER_ADMIN_PASSWORD")),
                                   "authenticated": self.admin_authenticated()})
        if path == "/api/admin/homes":
            if not self.require_admin():
                return
            with inventory_connection() as connection:
                rows = connection.execute("SELECT * FROM homes ORDER BY created_at DESC, id DESC").fetchall()
            return self.send_json({"homes": [dict(row) for row in rows if row["state"] in DATASET_STATES]})
        if path == "/api/admin/tours":
            if not self.require_admin():
                return
            with inventory_connection() as connection:
                rows = connection.execute("""
                    SELECT tour_requests.*, homes.title AS home_title, homes.state AS home_state,
                           homes.town AS home_town, homes.price AS home_price,
                           homes.transaction_type AS home_transaction_type,
                           homes.rent_frequency AS home_rent_frequency
                    FROM tour_requests JOIN homes ON homes.id=tour_requests.home_id
                    ORDER BY tour_requests.created_at DESC, tour_requests.id DESC
                """).fetchall()
            return self.send_json({"tours": [dict(row) for row in rows]})
        if path == "/api/meta":
            return self.send_json({"states": sorted(DATASET_STATES),
                                   "supportedStates": sorted(ALLOWED_STATES),
                                   "stateCounts": dict(STATE_LISTING_COUNTS),
                                   "minimumStateListings": MIN_STATE_LISTINGS,
                                   "towns": {state: sorted(TOWNS[state], key=str.casefold) for state in ALLOWED_STATES},
                                   "types": sorted(TYPES), "listingCount": len(LISTINGS)})
        if path == "/api/health":
            return self.send_json({"status": "ready", "listings": len(LISTINGS)})
        if path in ("/", "/shelter.html"):
            file_path = ROOT / "shelter.html"
        elif path in ("/admin", "/admin.html"):
            file_path = ROOT / "admin.html"
        elif path in ("/styles.css", "/app.js", "/admin.css", "/admin.js"):
            file_path = WEB_ROOT / path.lstrip("/")
        else:
            self.send_error(404)
            return
        return self.serve_file(file_path)

    def do_POST(self):
        path = urlparse(self.path).path
        if not self.same_origin():
            return self.send_json({"error": "This request origin is not allowed."}, 403)
        if path == "/api/admin/login":
            configured_password = os.environ.get("MOSHELTER_ADMIN_PASSWORD") or os.environ.get("SHELTER_ADMIN_PASSWORD", "")
            if len(configured_password) < 12:
                return self.send_json({"error": "Admin access is not configured. Set MOSHELTER_ADMIN_PASSWORD to a private password of at least 12 characters and restart Moshelter."}, 503)
            try:
                payload = self.read_json()
            except (ValueError, json.JSONDecodeError) as error:
                return self.send_json({"error": str(error)}, 400)
            password = payload.get("password")
            if not isinstance(password, str) or not hmac.compare_digest(password.encode("utf-8"), configured_password.encode("utf-8")):
                return self.send_json({"error": "The password is not correct."}, 401)
            session = secrets.token_urlsafe(32)
            ADMIN_SESSIONS[session] = time.time() + ADMIN_SESSION_TTL
            secure = "; Secure" if (os.environ.get("MOSHELTER_COOKIE_SECURE") or os.environ.get("SHELTER_COOKIE_SECURE")) == "1" else ""
            cookie = f"shelter_admin={session}; Path=/; HttpOnly; SameSite=Strict; Max-Age={ADMIN_SESSION_TTL}{secure}"
            return self.send_json({"ok": True}, headers=(("Set-Cookie", cookie),))
        if path == "/api/admin/logout":
            cookie = SimpleCookie()
            cookie.load(self.headers.get("Cookie", ""))
            session = cookie.get("shelter_admin")
            if session:
                ADMIN_SESSIONS.pop(session.value, None)
            expired = "shelter_admin=; Path=/; HttpOnly; SameSite=Strict; Max-Age=0"
            return self.send_json({"ok": True}, headers=(("Set-Cookie", expired),))
        if path == "/api/tours":
            try:
                payload = validate_tour(self.read_json())
                with inventory_connection() as connection:
                    home = connection.execute("SELECT status,state FROM homes WHERE id=?", (payload["home_id"],)).fetchone()
                    if not home or home["status"] != "available" or home["state"] not in DATASET_STATES:
                        return self.send_json({"error": "This home is not currently available for tours."}, 404)
                    cursor = connection.execute("""
                        INSERT INTO tour_requests (home_id,name,email,phone,preferred_at,tour_type,note,created_at)
                        VALUES (?,?,?,?,?,?,?,?)
                    """, (payload["home_id"], payload["name"], payload["email"], payload["phone"],
                          payload["preferred_at"], payload["tour_type"], payload["note"],
                          datetime.datetime.now().isoformat(timespec="seconds")))
                return self.send_json({"ok": True, "request_id": cursor.lastrowid,
                                       "message": "Your tour request has been sent. Moshelter will contact you to confirm the time."}, 201)
            except (ValueError, json.JSONDecodeError) as error:
                return self.send_json({"error": str(error)}, 400)
            except sqlite3.Error:
                return self.send_json({"error": "We could not save your tour request. Please try again."}, 500)
        if path == "/api/admin/homes":
            if not self.require_admin():
                return
            try:
                home = validated_home(self.read_json())
                columns = tuple(home)
                with inventory_connection() as connection:
                    cursor = connection.execute(
                        f"INSERT INTO homes ({','.join(columns)},created_at) VALUES ({','.join('?' for _ in columns)},?)",
                        (*[home[column] for column in columns], datetime.datetime.now().isoformat(timespec="seconds")))
                return self.send_json({"ok": True, "id": cursor.lastrowid}, 201)
            except (ValueError, json.JSONDecodeError) as error:
                return self.send_json({"error": str(error)}, 400)
            except sqlite3.Error:
                return self.send_json({"error": "The listing could not be saved."}, 500)
        tour_status_match = re.fullmatch(r"/api/admin/tours/(\d+)/status", path)
        if tour_status_match:
            if not self.require_admin():
                return
            try:
                status = self.read_json().get("status")
                if not isinstance(status, str) or status not in {"requested", "confirmed", "completed", "cancelled"}:
                    raise ValueError("Choose a valid tour-request status.")
                with inventory_connection() as connection:
                    cursor = connection.execute("UPDATE tour_requests SET status=? WHERE id=?", (status, int(tour_status_match.group(1))))
                if cursor.rowcount == 0:
                    return self.send_json({"error": "Tour request not found."}, 404)
                return self.send_json({"ok": True})
            except (ValueError, json.JSONDecodeError) as error:
                return self.send_json({"error": str(error)}, 400)
            except sqlite3.Error:
                return self.send_json({"error": "The tour request could not be updated."}, 500)
        if path != "/api/predict":
            self.send_error(404)
            return
        try:
            query = self.read_json(10000)
            result = predict(query)
            return self.send_json(result)
        except (ValueError, json.JSONDecodeError) as error:
            return self.send_json({"error": str(error)}, 400)
        except Exception:
            return self.send_json({"error": "The estimate could not be prepared. Please try again."}, 500)

    def do_PUT(self):
        path = urlparse(self.path).path
        if not self.same_origin():
            return self.send_json({"error": "This request origin is not allowed."}, 403)
        home_match = re.fullmatch(r"/api/admin/homes/(\d+)", path)
        if home_match:
            if not self.require_admin():
                return
            try:
                home = validated_home(self.read_json())
                columns = tuple(home)
                with inventory_connection() as connection:
                    cursor = connection.execute(
                        "UPDATE homes SET " + ",".join(f"{column}=?" for column in columns) + " WHERE id=?",
                        (*[home[column] for column in columns], int(home_match.group(1))))
                if cursor.rowcount == 0:
                    return self.send_json({"error": "Listing not found."}, 404)
                return self.send_json({"ok": True})
            except (ValueError, json.JSONDecodeError) as error:
                return self.send_json({"error": str(error)}, 400)
            except sqlite3.Error:
                return self.send_json({"error": "The listing could not be updated."}, 500)
        self.send_error(404)

    def log_message(self, fmt, *args):
        print("[%s] %s" % (self.log_date_time_string(), fmt % args))


def main():
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "8000"))
    server = ThreadingHTTPServer((host, port), Handler)
    print("Moshelter is running at http://%s:%s" % (host, port))
    print("Loaded %s cleaned Lagos and Abuja listings." % f"{len(LISTINGS):,}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()



