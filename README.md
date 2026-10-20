# AI Invoice Ingestion Platform

An AI pipeline that reads clinical trial site invoices, matches them to sponsors, studies, sites and
catalog items from the reference API, and asks the user to confirm each stage. The original take-home
brief is in [`TAKEHOME_INSTRUCTIONS.md`](TAKEHOME_INSTRUCTIONS.md).

## How to run the reference API

Requires Docker.

```bash
docker compose up --build
```

- The API runs at http://localhost:8000, with interactive docs at http://localhost:8000/docs.
- Postgres listens on `localhost:5433` (user `ctref`, password `ctref`, database `ctref`).
- Check it is up: `curl http://localhost:8000/health` returns `{"status": "ok"}`.

## How to run the app

_To be written once the app is built._

## Environment variables

_To be written once the app is built._

| Variable | Required | Meaning |
|---|---|---|

## How to exercise the full flow

_To be written once the app is built._

## Write-up

### How I designed the extraction and matching prompts

_To be written._

### How I handled partial metadata-matching failures

_To be written._ (For example: the sponsor is not found, but the study is matched.)

### One thing I would improve or add next

_To be written._
