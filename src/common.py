from pathlib import Path
import sqlite3
ROOT=Path(__file__).resolve().parents[1]
RAW=ROOT/"data"/"raw"
CLEAN=ROOT/"data"/"clean"
OUT=ROOT/"outputs"
DB=ROOT/"data"/"instamart.db"
for p in (RAW,CLEAN,OUT,DB.parent): p.mkdir(parents=True,exist_ok=True)
def connect():
    return sqlite3.connect(DB)
