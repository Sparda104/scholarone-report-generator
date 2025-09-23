from __future__ import annotations
from typing import Dict, Literal, TypedDict

Method = Literal["GET", "POST"]

class EndpointDef(TypedDict, total=False):
    path: str
    method: Method
    required_params: list[str]
    optional_params: list[str]
    notes: str

ENDPOINTS: Dict[str, EndpointDef] = {
    "person_full_by_email": {
        "path": "/api/s1m/v7/person/full/email/search",
        "method": "GET",
        "required_params": ["primary_email", "_type"],
        "optional_params": [],
        "notes": "Full person record by primary email",
    },
    "submissions_basic_by_ids": {
        "path": "/api/s1m/v3/submissions/basic/metadata/submissionids",
        "method": "GET",
        "required_params": ["ids", "_type"],
        "optional_params": [],
        "notes": "ids must be quoted, comma-separated",
    },
    "submission_full_by_documentids": {
        "path": "/api/s1m/v9/submissions/full/metadata/documentids",
        "method": "GET",
        "required_params": ["ids", "_type"],
        "optional_params": [],
        "notes": "Full submission info by document IDs",
    },
    "submission_full_by_submissionids": {
        "path": "/api/s1m/v9/submissions/full/metadata/submissionids",
        "method": "GET",
        "required_params": ["ids", "_type"],
        "optional_params": [],
        "notes": "Full submission info by submission IDs",
    },
    "metadatainfo_by_documentids": {
        "path": "/api/s1m/v3/submissions/full/metadatainfo/documentids",
        "method": "GET",
        "required_params": ["ids", "_type"],
        "optional_params": [],
        "notes": "Metadata info by document IDs",
    },
    "metadatainfo_by_submissionids": {
        "path": "/api/s1m/v3/submissions/full/metadatainfo/submissionids",
        "method": "GET",
        "required_params": ["ids", "_type"],
        "optional_params": [],
        "notes": "Metadata info by submission IDs",
    },
    "ids_by_date": {
        "path": "/api/s1m/v4/submissions/full/idsByDate",
        "method": "GET",
        "required_params": ["from_time", "to_time", "_type"],
        "optional_params": ["role_type", "custom_question", "Locale ID", "External ID"],
        "notes": "Returns document IDs in a UTC time range; app converts common date formats to UTC Z",
    },
    "author_full_by_documentids": {
        "path": "/api/s1m/v3/submissions/full/contributors/authors/documentids",
        "method": "GET",
        "required_params": ["ids", "_type"],
        "optional_params": [],
        "notes": "Author info by document IDs",
    },
    "author_full_by_submissionids": {
        "path": "/api/s1m/v3/submissions/full/contributors/authors/submissionids",
        "method": "GET",
        "required_params": ["ids", "_type"],
        "optional_params": [],
        "notes": "Author info by submission IDs",
    },
    "reviewer_full_by_documentids": {
        "path": "/api/s1m/v2/submissions/full/reviewer/documentids",
        "method": "GET",
        "required_params": ["ids", "_type"],
        "optional_params": [],
        "notes": "Reviewer info by document IDs",
    },
    "reviewer_full_by_submissionids": {
        "path": "/api/s1m/v2/submissions/full/reviewer/submissionids",
        "method": "GET",
        "required_params": ["ids", "_type"],
        "optional_params": [],
        "notes": "Reviewer info by submission IDs",
    },
}
