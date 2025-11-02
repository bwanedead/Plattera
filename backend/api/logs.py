from fastapi import APIRouter, Query, Response
from services.logging_service import get_ring_handler, LOG_FILE
import os
import io
import zipfile
import json


router = APIRouter(prefix="/logs", tags=["logs"])


@router.get("/recent")
def get_recent_logs(limit: int = Query(500, ge=1, le=5000)):
    ring = get_ring_handler()
    return {"logs": ring.get_recent(limit)}


@router.get("/download")
def download_logs():
    buf = io.BytesIO()
    base = os.path.basename(LOG_FILE)
    directory = os.path.dirname(LOG_FILE)
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        # Include rotating files app.log, app.log.1, ...
        try:
            for name in os.listdir(directory):
                if name.startswith(os.path.splitext(base)[0]):
                    path = os.path.join(directory, name)
                    if os.path.isfile(path):
                        zf.write(path, arcname=name)
        except Exception:
            # If log dir not present yet, continue gracefully
            pass

        # Also include recent ring buffer as JSON
        try:
            ring_json = json.dumps({"logs": get_ring_handler().get_recent(2000)}, indent=2).encode("utf-8")
            zf.writestr("recent_ring_buffer.json", ring_json)
        except Exception:
            pass

    headers = {"Content-Disposition": 'attachment; filename="plattera-logs.zip"'}
    return Response(content=buf.getvalue(), media_type="application/zip", headers=headers)


