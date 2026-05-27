"""N2: Legacy route deprecation stubs.

Returns 410 Gone with Sunset + Link headers for the deleted
/cts/identity/global_tracks*, /cts/identity/decisions*, and
/cts/identity/corrections/unmerge_tracklet routes.

Keep this stub for one release (one calendar month), then delete.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/cts", tags=["cts-legacy-gone"])

_SUNSET = "Sat, 28 Jun 2026 00:00:00 GMT"
_SUCCESSOR = '</api/v1/cts/ph>; rel="successor-version"'

_LEGACY_PATHS = [
    "/identity/global_tracks",
    "/identity/global_tracks/{path:path}",
    "/identity/decisions",
    "/identity/decisions/{path:path}",
    "/identity/corrections/unmerge_tracklet",
]


def _gone_response(request: Request) -> JSONResponse:
    return JSONResponse(
        status_code=410,
        content={
            "code": "cts.legacy_gone",
            "message": (
                "This endpoint has been removed. The world tracker now uses "
                "Person Hypotheses (PHs). Use /api/v1/cts/ph instead."
            ),
        },
        headers={"Sunset": _SUNSET, "Link": _SUCCESSOR},
    )


for _path in _LEGACY_PATHS:
    router.add_api_route(
        _path,
        _gone_response,
        methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        include_in_schema=False,
    )
