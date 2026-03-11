export const pageImportPatterns = [
  "@/pages/*",
  "../pages/*",
  "../../pages/*",
  "../../../pages/*",
  "../../../../pages/*",
];

export const componentImportPatterns = [
  "@/components/*",
  "../components/*",
  "../../components/*",
  "../../../components/*",
  "../../../../components/*",
];

export const frontendSharedLayerPrefixes = [
  "frontend/src/hooks/",
  "frontend/src/services/",
  "frontend/src/utils/",
];

export const frontendComponentPrefix = "frontend/src/components/";
export const backendServicePrefix = "backend/services/";
export const backendPipelinePrefix = "backend/pipelines/";

export function isPageImport(specifier) {
  return specifier.includes("/pages/") || specifier.startsWith("@/pages/");
}

export function isServiceImport(specifier) {
  return specifier.includes("/services/") || specifier.startsWith("@/services/");
}

export function isComponentImport(specifier) {
  return specifier.includes("/components/") || specifier.startsWith("@/components/");
}

export function isApiModuleImport(specifier) {
  return specifier.startsWith("api.");
}
