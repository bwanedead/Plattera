from __future__ import annotations

from fastapi import APIRouter, Query
from typing import Optional

from services.assets.service import AssetsService


router = APIRouter()
assets_service = AssetsService()


@router.get("/assets")
def list_assets(plss_state: Optional[str] = Query(default=None)) -> dict:
    assets = assets_service.list_assets(plss_state=plss_state)
    return {"assets": assets}


@router.post("/assets/{asset_id}/install")
def install_asset(asset_id: str) -> dict:
    return assets_service.start_install(asset_id)


@router.get("/assets/{asset_id}/progress")
def asset_progress(asset_id: str) -> dict:
    return assets_service.get_progress(asset_id)


@router.post("/assets/{asset_id}/cancel")
def cancel_asset(asset_id: str) -> dict:
    return assets_service.cancel_install(asset_id)


@router.post("/assets/{asset_id}/stop")
def stop_asset(asset_id: str) -> dict:
    return assets_service.stop_install(asset_id)


@router.post("/assets/{asset_id}/purge")
def purge_asset(asset_id: str) -> dict:
    return assets_service.purge_asset(asset_id)
