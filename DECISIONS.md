# Decisions

A log of the significant choices made while building this project, with the reasoning behind each.
Newest entries go at the bottom.

---

## 1. Keep SQLAlchemy on the 2.0 series in the reference API

**Date:** 2026-10-20

**Context.** The provided reference API failed to start under `docker compose up --build`. The API
container crashed while seeding the database with `ModuleNotFoundError: No module named 'psycopg'`.

`services/api/requirements.txt` set only a lower bound (`sqlalchemy>=2.0.36`), so a fresh build
installed SQLAlchemy 2.1.5. In 2.1, a plain `postgresql://` URL loads the psycopg 3 driver
(`psycopg`) by default, where 2.0 loaded psycopg2. The image installs only `psycopg2-binary`, so
SQLAlchemy could not find a driver. The starter code was correct when it was written; a later
SQLAlchemy release broke it.

**Decision.** Change the requirement to `sqlalchemy>=2.0.36,<2.1`. That is the only change to the
provided code.

**Alternatives considered.**
- *Change the URL to `postgresql+psycopg2://`* in `docker-compose.yml` and in the defaults in
  `app/database.py` and `docker-entrypoint.sh`. This also works, but it touches three files instead
  of one.
- *Switch the driver to `psycopg[binary]`.* This moves the reference API to a newer driver it was
  never tested with, which is more change than the fix needs.

**Consequences.** The reference API builds and starts, and its seed data matches the README
(4 sponsors, 6 studies, 8 sites, 17 study-site links, 134 catalog items, 100 of them for
Northwind Pharma / LUMIN-2024). The API stays on SQLAlchemy 2.0 until someone moves it to 2.1 on
purpose.
