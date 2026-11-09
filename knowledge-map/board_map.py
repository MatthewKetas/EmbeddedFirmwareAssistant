import hashlib
import re
import sqlite3
from contextlib import closing
from itertools import islice
from pathlib import Path
from xml.etree import ElementTree


MAP_DIR = Path(__file__).resolve().parent
DB_PATH = MAP_DIR / "knowledge.sql"
STARTER_BOARDS = (
    ("arduino-uno", "Arduino Uno", "R3", "atmega328p.svd"),
    ("esp-32", "ESP32", "generic", "esp32.svd"),
)
SCHEMA = """
CREATE TABLE IF NOT EXISTS svd_devices (
    id TEXT PRIMARY KEY NOT NULL,
    device_name TEXT NOT NULL,
    svd_xml TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS boards (
    id TEXT PRIMARY KEY NOT NULL,
    name TEXT NOT NULL,
    revision TEXT NOT NULL,
    svd_device_id TEXT NOT NULL REFERENCES svd_devices(id),
    UNIQUE (name, revision)
);
CREATE TABLE IF NOT EXISTS board_facts (
    board_id TEXT NOT NULL REFERENCES boards(id),
    key TEXT NOT NULL,
    value TEXT NOT NULL,
    source TEXT,
    PRIMARY KEY (board_id, key)
);
"""


def connect():
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    return closing(db)


def initialize(db):
    db.executescript(SCHEMA)
    with db:
        for board_id, name, revision, svd_id in STARTER_BOARDS:
            if not db.execute("SELECT 1 FROM svd_devices WHERE id = ?", (svd_id,)).fetchone():
                xml = (MAP_DIR / "svd" / svd_id).read_text(encoding="utf-8")
                device = ElementTree.fromstring(xml)
                db.execute(
                    "INSERT INTO svd_devices VALUES (?, ?, ?) ON CONFLICT(id) DO NOTHING",
                    (svd_id, device.findtext("name"), xml),
                )
            db.execute(
                "INSERT INTO boards VALUES (?, ?, ?, ?) ON CONFLICT(id) DO NOTHING",
                (board_id, name, revision, svd_id),
            )


def list_boards():
    with connect() as db:
        initialize(db)
        boards = db.execute("SELECT id, name, revision FROM boards ORDER BY id").fetchall()
    return [dict(board) for board in boards]


def import_board(data):
    from defusedxml import ElementTree as SafeElementTree

    device = SafeElementTree.fromstring(data, forbid_dtd=True)
    for element in device.iter():
        element.tag = element.tag.rsplit("}", 1)[-1]
    name = device.findtext("name", "").strip()
    revision = device.findtext("version", "").strip() or "Unspecified"
    peripherals = device.findall("./peripherals/peripheral")
    registers = device.findall("./peripherals/peripheral/registers/register")
    if device.tag != "device" or not name or not peripherals or any(
        not element.findtext("name", "").strip() for element in (*peripherals, *registers)
    ):
        raise ValueError("Choose a CMSIS-SVD device XML file with named peripherals and registers.")
    xml = ElementTree.tostring(device, encoding="unicode")
    board_id = "svd-" + hashlib.sha256(xml.encode()).hexdigest()[:24]
    with connect() as db:
        initialize(db)
        with db:
            db.execute("INSERT INTO svd_devices VALUES (?, ?, ?) ON CONFLICT(id) DO NOTHING", (board_id, name, xml))
            db.execute(
                "INSERT INTO boards VALUES (?, ?, ?, ?) ON CONFLICT(name, revision) DO NOTHING",
                (board_id, name, revision, board_id),
            )
            if not db.execute("SELECT 1 FROM boards WHERE id = ?", (board_id,)).fetchone():
                raise ValueError(f"A different XML file already defines {name} ({revision}).")
    return {"id": board_id, "name": name, "revision": revision}


def select_board(arg, current):
    if arg == "none":
        print("Board selection cleared.\n")
        return None
    for board in list_boards():
        label = f"{board['name']} ({board['revision']})"
        if arg == board["id"]:
            print(f"Selected board: {label}\n")
            return arg
        if not arg:
            active = " [selected]" if board["id"] == current else ""
            print(f"  {board['id']}  {label}{active}")
    print(f"Unknown board {arg!r}. Use /board to list choices.\n" if arg else "")
    return current


def remember(board_id, arg):
    if board_id is None:
        print("Select a board with /board <id> before using /remember.\n")
        return
    key, _, value = arg.partition("=")
    key, value = key.strip().lower(), value.strip()
    if not re.fullmatch(r"[a-z0-9_-]{1,64}", key) or not 0 < len(value) <= 512:
        print("Usage: /remember key=value (key up to 64 letters, digits, _ or - and value up to 512 characters)\n")
        return
    with connect() as db, db:
        db.execute(
            """INSERT INTO board_facts (board_id, key, value, source) VALUES (?, ?, ?, 'user')
               ON CONFLICT(board_id, key) DO UPDATE SET value = excluded.value, source = excluded.source""",
            (board_id, key, value),
        )
    print(f"Remembered {key} for {board_id}.\n")


def svd_matches(xml, question):
    symbols = set(re.findall(r"[A-Z0-9_]+", question.upper()))
    for peripheral in ElementTree.fromstring(xml).findall("./peripherals/peripheral"):
        name = peripheral.findtext("name", "").strip()
        base = peripheral.findtext("baseAddress")
        if name.upper() in symbols:
            yield f"{name} base address {base}"
        for register in peripheral.findall("./registers/register"):
            reg = register.findtext("name", "").strip()
            qualified = f"{name}_{reg}".upper()
            if symbols.intersection((reg.upper(), qualified, qualified + "_REG")):
                description = " ".join(register.findtext("description", "").split())[:180]
                offset = register.findtext("addressOffset")
                yield f"{name}.{reg}, offset {offset} from {base}. {description}".rstrip()


def context(board_id, question):
    with connect() as db:
        board = db.execute(
            """SELECT boards.name, revision, svd_devices.*
               FROM boards JOIN svd_devices ON svd_device_id = svd_devices.id WHERE boards.id = ?""",
            (board_id,),
        ).fetchone()
        facts = db.execute(
            "SELECT key, value FROM board_facts WHERE board_id = ? ORDER BY key", (board_id,),
        ).fetchall()
    words = set(re.findall(r"[a-z0-9]+", question.lower()))
    facts.sort(key=lambda fact: -len(words.intersection(re.findall(r"[a-z0-9]+", fact["key"]))))
    lines = [f"Selected board: {board['name']} ({board['revision']}), device {board['device_name']}."]
    lines.extend(f"[remember:{fact['key']}] User-confirmed {fact['key']} = {fact['value']}" for fact in facts[:6])
    lines.extend(f"[{board['id']}] {match}" for match in islice(svd_matches(board["svd_xml"], question), 6))
    return "\n".join(lines)
