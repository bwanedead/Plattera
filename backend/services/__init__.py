# Services package

__all__ = ["AlignmentService"]


def __getattr__(name: str):
    if name == "AlignmentService":
        from services.alignment_service import AlignmentService

        return AlignmentService
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")