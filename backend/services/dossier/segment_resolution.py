"""
Segment Resolution Helper
=========================

Utilities to resolve a segment_id given a dossier_id and a transcription_id.
"""

from typing import Optional

from services.dossier.management_service import DossierManagementService


def resolve_segment_id(dossier_id: str, transcription_id: str) -> Optional[str]:
    """Return the segment_id that contains a run with the provided transcription_id.

    If no matching segment is found, returns None.
    """
    try:
        mgmt = DossierManagementService()
        dossier = mgmt.get_dossier(dossier_id)
        if not dossier:
            return None
        for segment in getattr(dossier, 'segments', []) or []:
            for run in getattr(segment, 'runs', []) or []:
                tid = getattr(run, 'transcription_id', None) or getattr(run, 'transcriptionId', None)
                if tid and str(tid) == str(transcription_id):
                    return str(segment.id)
    except Exception:
        return None
    return None


