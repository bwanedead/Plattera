"""
Service Registry - Auto-discovers all available services
Drop providers in llm/ or ocr/ folders and they'll be automatically loaded

LLM model ownership is credential-independent: declared models remain
discoverable when a provider key is absent. Callable services are a
separate fact from ownership.
"""
from __future__ import annotations

import os
import importlib
import glob
import sys
from typing import Any, Dict, List, Mapping, MutableMapping, Set, Union
import logging
from services.llm.base import LLMService
from services.ocr.base import OCRService


class ModelProviderError(Exception):
    """Mechanical model→provider resolution failure (no credentials in message)."""

    def __init__(self, reason_code: str, message: str) -> None:
        super().__init__(message)
        self.reason_code = str(reason_code or "model_provider_not_found")


class ServiceRegistry:
    """Central registry that auto-discovers and manages all services"""

    def __init__(self, *, discover: bool = True) -> None:
        # Callable (configured) services only.
        self.llm_services: Dict[str, LLMService] = {}
        self.ocr_services: Dict[str, OCRService] = {}
        # Declared LLM providers regardless of credential availability.
        self._declared_llm_services: Dict[str, LLMService] = {}
        # model_id → provider name (unique owners only).
        self._model_owners: Dict[str, str] = {}
        # model_id → metadata copied from provider.models
        self._model_metadata: Dict[str, Dict[str, Any]] = {}
        # model_id → set of conflicting provider names
        self._ambiguous_models: Dict[str, Set[str]] = {}
        if discover:
            self._discover_services()

    def _discover_services(self) -> None:
        """Auto-discover all available LLM and OCR services"""
        logger = logging.getLogger(__name__)
        logger.debug("🔍 Discovering services...")

        self._discover_llm_services()
        self._discover_ocr_services()

        logger.debug(
            f"✅ Loaded {len(self.llm_services)} LLM services, {len(self.ocr_services)} OCR services"
        )

    def _register_service_from_module(self, module_name: str, service_type: str) -> None:
        """Helper to inspect a module and register its service."""
        logger = logging.getLogger(__name__)
        try:
            package = f"services.{service_type}"
            full_module_name = f"{package}.{module_name}"
            module = importlib.import_module(full_module_name)

            base_class = LLMService if service_type == "llm" else OCRService
            target_dict: MutableMapping[str, Any] = (
                self.llm_services if service_type == "llm" else self.ocr_services
            )

            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if (
                    isinstance(attr, type)
                    and issubclass(attr, base_class)
                    and attr is not base_class
                ):
                    try:
                        service = attr()
                        if service_type == "llm":
                            self.accept_llm_service(service)
                        elif service.is_available():
                            target_dict[service.name] = service
                            logger.info(f"✅ {service_type.upper()}: {service.name}")
                        else:
                            logger.warning(
                                f"⚠️  {service_type.upper()}: {service.name} (not configured)"
                            )
                    except Exception as e:
                        logger.error(
                            f"❌ {service_type.upper()}: {module_name} failed to load: {e}"
                        )
        except Exception as e:
            logger.error(f"❌ Failed to import {service_type.upper()} module {module_name}: {e}")

    def accept_llm_service(self, service: LLMService) -> None:
        """Register a declared LLM provider and index its models.

        Ownership is recorded from ``service.models`` even when the provider is
        not configured. Only available providers are added to ``llm_services``.
        """
        logger = logging.getLogger(__name__)
        name = str(getattr(service, "name", "") or "").strip()
        if not name:
            logger.error("❌ LLM service missing name; skipping")
            return
        self._declared_llm_services[name] = service
        self._index_llm_models(service)
        if service.is_available():
            self.llm_services[name] = service
            logger.info(f"✅ LLM: {name}")
        else:
            logger.warning(f"⚠️  LLM: {name} (not configured)")

    def _index_llm_models(self, service: LLMService) -> None:
        owner = str(getattr(service, "name", "") or "").strip()
        if not owner:
            return
        raw_models = getattr(service, "models", {}) or {}
        if not isinstance(raw_models, Mapping):
            return
        for model_id, meta in raw_models.items():
            mid = str(model_id or "").strip()
            if not mid:
                continue
            if mid in self._ambiguous_models:
                self._ambiguous_models[mid].add(owner)
                continue
            prior = self._model_owners.get(mid)
            if prior is not None and prior != owner:
                self._ambiguous_models[mid] = {prior, owner}
                self._model_owners.pop(mid, None)
                self._model_metadata.pop(mid, None)
                continue
            self._model_owners[mid] = owner
            self._model_metadata[mid] = dict(meta) if isinstance(meta, Mapping) else {}

    def _discover_llm_services(self) -> None:
        """Discover all LLM providers in services/llm/"""
        if getattr(sys, "frozen", False):
            logging.getLogger(__name__).info(
                "❄️ Running in frozen mode - manually registering LLM services"
            )
            known_services = ["openai", "meta"]  # keep in sync with PyInstaller hidden-imports
            for module in known_services:
                self._register_service_from_module(module, "llm")
            return

        llm_dir = os.path.join(os.path.dirname(__file__), "llm")
        provider_files = glob.glob(os.path.join(llm_dir, "*.py"))

        for file_path in provider_files:
            filename = os.path.basename(file_path)

            if filename in ["base.py", "__init__.py"]:
                continue

            module_name = filename[:-3]
            self._register_service_from_module(module_name, "llm")

    def _discover_ocr_services(self) -> None:
        """Discover all OCR providers in services/ocr/"""
        if getattr(sys, "frozen", False):
            logging.getLogger(__name__).info(
                "❄️ Running in frozen mode - manually registering OCR services"
            )
            known_services: List[str] = []
            for module in known_services:
                self._register_service_from_module(module, "ocr")
            return

        ocr_dir = os.path.join(os.path.dirname(__file__), "ocr")
        provider_files = glob.glob(os.path.join(ocr_dir, "*.py"))

        for file_path in provider_files:
            filename = os.path.basename(file_path)

            if filename in ["base.py", "__init__.py"]:
                continue

            module_name = filename[:-3]
            self._register_service_from_module(module_name, "ocr")

    def get_model_metadata(self, model_id: str) -> Dict[str, Any]:
        """Return declared metadata for ``model_id`` (credentials not required)."""
        mid = str(model_id or "").strip()
        if not mid:
            raise ModelProviderError("model_provider_not_found", "Model id is blank.")
        if mid in self._ambiguous_models:
            raise ModelProviderError(
                "model_provider_ambiguous",
                f"Model '{mid}' is claimed by multiple providers.",
            )
        meta = self._model_metadata.get(mid)
        if meta is None:
            raise ModelProviderError(
                "model_provider_not_found",
                f"Model '{mid}' is not declared by any provider.",
            )
        return dict(meta)

    def get_provider_name_for_model(self, model_id: str) -> str:
        """Return the owning provider name for a uniquely declared model."""
        mid = str(model_id or "").strip()
        if not mid:
            raise ModelProviderError("model_provider_not_found", "Model id is blank.")
        if mid in self._ambiguous_models:
            raise ModelProviderError(
                "model_provider_ambiguous",
                f"Model '{mid}' is claimed by multiple providers.",
            )
        owner = self._model_owners.get(mid)
        if not owner:
            raise ModelProviderError(
                "model_provider_not_found",
                f"Model '{mid}' is not declared by any provider.",
            )
        return owner

    def get_available_llm_service_for_model(self, model_id: str) -> LLMService:
        """Return a configured LLM service for ``model_id``.

        Distinguishes unknown, ambiguous, and known-but-unavailable providers.
        """
        mid = str(model_id or "").strip()
        provider = self.get_provider_name_for_model(mid)
        service = self.llm_services.get(provider)
        if service is None:
            raise ModelProviderError(
                "model_provider_unavailable",
                f"Provider for model '{mid}' is not configured.",
            )
        return service

    def get_all_models(self) -> Dict[str, Dict[str, Any]]:
        """Get models from configured, callable services only.

        Declared-but-unavailable and ambiguous models are intentionally omitted.
        Credential-independent ownership remains available via
        ``get_model_metadata`` / ``get_provider_name_for_model``.
        """
        all_models: Dict[str, Dict[str, Any]] = {}

        for service in self.llm_services.values():
            try:
                models = service.get_models()
                for model_id, model_info in models.items():
                    mid = str(model_id or "").strip()
                    if not mid or mid in self._ambiguous_models:
                        continue
                    owner = self._model_owners.get(mid)
                    if owner is not None and owner != service.name:
                        continue
                    row = dict(model_info) if isinstance(model_info, Mapping) else {}
                    row["service_type"] = "llm"
                    row["service_name"] = service.name
                    all_models[mid] = row
            except Exception as e:
                logging.getLogger(__name__).error(
                    f"Error getting models from LLM service {service.name}: {e}"
                )

        for service in self.ocr_services.values():
            try:
                models = service.get_models()
                for model_id, model_info in models.items():
                    row = dict(model_info) if isinstance(model_info, Mapping) else {}
                    row["service_type"] = "ocr"
                    row["service_name"] = service.name
                    all_models[str(model_id)] = row
            except Exception as e:
                logging.getLogger(__name__).error(
                    f"Error getting models from OCR service {service.name}: {e}"
                )

        return all_models

    def get_service_for_model(self, model: str) -> Union[LLMService, OCRService, None]:
        """Find which configured service can handle a specific model."""
        mid = str(model or "").strip()
        if not mid:
            return None
        try:
            return self.get_available_llm_service_for_model(mid)
        except ModelProviderError:
            pass

        for service in self.ocr_services.values():
            if mid in service.get_models():
                return service

        return None

    def get_llm_services(self) -> Dict[str, LLMService]:
        """Get all available LLM services with detailed info"""
        return self.llm_services.copy()

    def get_ocr_services(self) -> Dict[str, OCRService]:
        """Get all available OCR services with detailed info"""
        return self.ocr_services.copy()

    def get_service_info(self) -> Dict[str, Any]:
        """Get detailed information about configured (available) services."""
        info: Dict[str, Any] = {
            "llm_services": {},
            "ocr_services": {},
            "total_models": 0,
        }

        for name, service in self.llm_services.items():
            models = service.get_models()
            info["llm_services"][name] = {
                "available": service.is_available(),
                "model_count": len(models),
                "models": list(models.keys()),
            }
            info["total_models"] += len(models)

        for name, service in self.ocr_services.items():
            models = service.get_models()
            info["ocr_services"][name] = {
                "available": service.is_available(),
                "model_count": len(models),
                "models": list(models.keys()),
            }
            info["total_models"] += len(models)

        return info

    def process_text(self, prompt: str, model: str, **kwargs) -> Dict[str, Any]:
        """Process text-only request (routes to appropriate LLM service)"""
        try:
            service = self.get_available_llm_service_for_model(model)
        except ModelProviderError as exc:
            return {
                "success": False,
                "error": str(exc),
                "reason_code": exc.reason_code,
                "text": None,
            }

        return service.call_text(prompt, model, **kwargs)

    def process_vision(self, prompt: str, image_data: str, model: str, **kwargs) -> Dict[str, Any]:
        """Process vision request (routes to appropriate LLM service)"""
        try:
            service = self.get_available_llm_service_for_model(model)
        except ModelProviderError as exc:
            return {
                "success": False,
                "error": str(exc),
                "reason_code": exc.reason_code,
                "text": None,
            }

        return service.call_vision(prompt, image_data, model, **kwargs)

    def process_ocr(self, image_path: str, model: str, **kwargs) -> Dict[str, Any]:
        """Process OCR request (routes to appropriate OCR service)"""
        service = self.get_service_for_model(model)

        if not service:
            return {
                "success": False,
                "error": f"Model '{model}' not found in any service",
                "text": None,
            }

        if not isinstance(service, OCRService):
            return {
                "success": False,
                "error": f"Model '{model}' is not an OCR model",
                "text": None,
            }

        return service.extract_text(image_path, model, **kwargs)


# Global registry instance
_registry: ServiceRegistry | None = None


def get_registry() -> ServiceRegistry:
    """Get the global service registry instance"""
    global _registry
    if _registry is None:
        _registry = ServiceRegistry()
    return _registry


def reset_registry_for_tests() -> None:
    """Clear the process-global registry (tests only)."""
    global _registry
    _registry = None


def get_model_metadata(model_id: str) -> Dict[str, Any]:
    """Canonical model metadata lookup (credentials not required)."""
    return get_registry().get_model_metadata(model_id)


def get_provider_name_for_model(model_id: str) -> str:
    """Canonical model→provider ownership lookup."""
    return get_registry().get_provider_name_for_model(model_id)


def get_available_llm_service_for_model(model_id: str) -> LLMService:
    """Canonical configured LLM service lookup for a model id."""
    return get_registry().get_available_llm_service_for_model(model_id)
