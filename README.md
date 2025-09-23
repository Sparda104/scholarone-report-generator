# Scholarone Report Generator (FastAPI)

Starter service that wraps ScholarOne Manuscripts APIs with a generic proxy and a registry of allowed endpoints.
This build includes **Option A**: common query parameters are visible in Swagger for the generic routes.

## Quickstart
```bash
python -m venv .venv
# Windows
. .venv/Scripts/activate
pip install -r requirements.txt
uvicorn src.app.main:app --reload
```

## Generic S1 proxy usage (named endpoints)
List endpoints:
```
GET /v1/endpoints
```

Examples:
```
GET /v1/s1/person_full_by_email?site_name=orgsci&primary_email=someone@example.com
GET /v1/s1/submission_full_by_submissionids?site_name=orgsci&ids=ORSC-MS-2025-20274
GET /v1/s1/ids_by_date?site_name=ms&from_time=09/23/2025&to_time=09/30/2025
```
