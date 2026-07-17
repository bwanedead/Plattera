import { readFileSync, readdirSync, statSync } from "node:fs";
import path from "node:path";
import {
  backendPipelinePrefix,
  backendServicePrefix,
  frontendComponentPrefix,
  frontendSharedLayerPrefixes,
  isApiModuleImport,
  isComponentImport,
  isPageImport,
  isServiceImport,
} from "./static-governance-config.mjs";

const repoRoot = path.resolve(import.meta.dirname, "..");
const ignoredSegments = new Set([
  ".git",
  ".next",
  ".venv",
  "node_modules",
  "__pycache__",
  ".pytest_cache",
  "dist",
  "build",
]);

const repoRootTestAllowlist = new Set([
  "test_alignment_api.py",
  "test_api.py",
  "test_consensus_draft_generator.py",
  "test_fixed_unified_path.py",
  "test_format_integration.py",
  "test_section_normalizer.py",
  "test_section_normalizer_alignment_pipeline.py",
  "test_section_normalizer_new_structure.py",
  "test_uneven_sections.py",
]);

const backendRootTestAllowlist = new Set([
  "test_final.py",
  "test_pyproj_behavior.py",
]);

const oversizedFileBudgets = new Map([
  ["backend/agent_kernel/tooling.py", { maxLines: 4815 }],
  ["backend/agents/controller/controller.py", { maxLines: 3915 }],
  ["backend/agents/transcript_edit/iteration_pipeline.py", { maxLines: 2455 }],
  ["backend/services/plss/overlay_engine.py", { maxLines: 1035 }],
  ["backend/agents/transcript_edit/controller.py", { maxLines: 1065 }],
  ["backend/pipelines/mapping/plss/data_manager.py", { maxLines: 1020 }],
  ["frontend/src/components/TextToSchemaWorkspace.tsx", { maxLines: 1505 }],
  ["frontend/src/components/image-processing/ResultsViewer.tsx", { maxLines: 1155 }],
  ["frontend/src/components/mapping/overlays/ContainerLabelManager.tsx", { maxLines: 1095 }],
  ["frontend/src/components/image-processing/ImageProcessingWorkspace.tsx", { maxLines: 935 }],
  ["frontend/src/components/assets/AssetsTray.tsx", { maxLines: 815 }],
  ["frontend/src/components/text-to-schema/TextToSchemaControlPanel.tsx", { maxLines: 770 }],
  ["frontend/src/components/dossier/DossierManager.tsx", { maxLines: 705 }],
]);

const componentServiceImportBaselines = new Map([
  ["frontend/src/components/agent-viewer/types.ts", 1],
  ["frontend/src/components/assets/AssetInstallOverlay.tsx", 1],
  ["frontend/src/components/assets/AssetsTray.tsx", 3],
  ["frontend/src/components/dossier/DossierList.tsx", 1],
  ["frontend/src/components/dossier/DossierManager.tsx", 3],
  ["frontend/src/components/dossier/DossierPicker.tsx", 1],
  ["frontend/src/components/dossier/items/DraftItem.tsx", 2],
  ["frontend/src/components/image-processing/ControlPanel.tsx", 1],
  ["frontend/src/components/image-processing/DossierReader.tsx", 3],
  ["frontend/src/components/image-processing/FinalDraftSelector.tsx", 2],
  ["frontend/src/components/image-processing/ImageProcessingWorkspace.tsx", 2],
  ["frontend/src/components/image-processing/ResultsViewer.tsx", 7],
  ["frontend/src/components/logs/LogsPanel.tsx", 1],
  ["frontend/src/components/mapping/GeoreferenceController.tsx", 1],
  ["frontend/src/components/mapping/MapStatusDisplay.tsx", 1],
  ["frontend/src/components/mapping/MapViewer.tsx", 1],
  ["frontend/src/components/mapping/overlays/ContainerLabelManager.tsx", 1],
  ["frontend/src/components/mapping/overlays/ContainerOverlayManager.tsx", 1],
  ["frontend/src/components/mapping/overlays/PLSSManager.tsx", 1],
  ["frontend/src/components/mapping/overlays/PLSSOverlayManager.tsx", 1],
  ["frontend/src/components/plss/PLSSDownloadBanner.tsx", 1],
  ["frontend/src/components/plss/PLSSDownloadOverlay.tsx", 1],
  ["frontend/src/components/polygon/PolygonDrawingControls.tsx", 1],
  ["frontend/src/components/polygon/PolygonViewer.tsx", 1],
  ["frontend/src/components/rag-index/IndexDetailsPanel.tsx", 1],
  ["frontend/src/components/schema/SchemaManager.tsx", 1],
  ["frontend/src/components/text-to-schema/JsonSchemaTab.tsx", 1],
  ["frontend/src/components/text-to-schema/TextToSchemaControlPanel.tsx", 3],
  ["frontend/src/components/TextToSchemaWorkspace.tsx", 8],
  ["frontend/src/components/visualization/backgrounds/GridBackground.tsx", 1],
  ["frontend/src/components/visualization/backgrounds/MapBackground.tsx", 1],
  ["frontend/src/components/visualization/layers/PolygonLayer.tsx", 1],
  ["frontend/src/components/visualization/VisualizationWorkspace.tsx", 2],
]);

const importPattern = /\b(?:import\s+(?:type\s+)?[^;]*?\sfrom\s*|import\s*\()\s*["']([^"']+)["']/g;

function toRepoRelative(filePath) {
  return path.relative(repoRoot, filePath).replace(/\\/g, "/");
}

function walkFiles(directory, files = []) {
  for (const entry of readdirSync(directory, { withFileTypes: true })) {
    if (ignoredSegments.has(entry.name)) {
      continue;
    }

    const fullPath = path.join(directory, entry.name);
    if (entry.isDirectory()) {
      walkFiles(fullPath, files);
      continue;
    }

    files.push(fullPath);
  }

  return files;
}

function getLineCount(filePath) {
  const content = readFileSync(filePath, "utf8");
  return content.split(/\r?\n/).length;
}

function getImports(filePath) {
  const content = readFileSync(filePath, "utf8");
  return [...content.matchAll(importPattern)].map((match) => match[1]);
}

function fail(message, failures) {
  failures.push(message);
}

const failures = [];
const repoFiles = walkFiles(repoRoot);

for (const testFile of readdirSync(repoRoot, { withFileTypes: true })) {
  if (!testFile.isFile() || !/^test_.*\.py$/.test(testFile.name)) {
    continue;
  }

  if (!repoRootTestAllowlist.has(testFile.name)) {
    fail(
      `Repo-root test file '${testFile.name}' is not allowlisted. Co-locate new tests with the module they validate.`,
      failures,
    );
  }
}

const backendRoot = path.join(repoRoot, "backend");
for (const testFile of readdirSync(backendRoot, { withFileTypes: true })) {
  if (!testFile.isFile() || !/^test_.*\.py$/.test(testFile.name)) {
    continue;
  }

  if (!backendRootTestAllowlist.has(testFile.name)) {
    fail(
      `Backend-root test file 'backend/${testFile.name}' is not allowlisted. Co-locate new tests under the owning package.`,
      failures,
    );
  }
}

for (const [relativePath, budget] of oversizedFileBudgets.entries()) {
  const fullPath = path.join(repoRoot, relativePath);
  if (!statSync(fullPath).isFile()) {
    fail(`Oversize budget target '${relativePath}' is missing. Update static-governance baselines.`, failures);
    continue;
  }

  const lineCount = getLineCount(fullPath);
  if (lineCount > budget.maxLines) {
    fail(
      `'${relativePath}' has ${lineCount} lines, exceeding its growth budget of ${budget.maxLines}. Split or reduce the module before growing it further.`,
      failures,
    );
  }
}

for (const filePath of repoFiles) {
  const relativePath = toRepoRelative(filePath);
  const isTsFile = /\.(ts|tsx)$/.test(relativePath);
  const isPyFile = /\.py$/.test(relativePath);
  if (!isTsFile && !isPyFile) {
    continue;
  }

  const imports = getImports(filePath);

  if (isTsFile && relativePath.startsWith(frontendComponentPrefix) && !relativePath.includes("/hooks/")) {
    const pageImport = imports.find(isPageImport);
    if (pageImport) {
      fail(
        `'${relativePath}' imports '${pageImport}'. Components must not depend on page modules.`,
        failures,
      );
    }

    const serviceImportCount = imports.filter(isServiceImport).length;
    const allowedImports = componentServiceImportBaselines.get(relativePath);
    if (serviceImportCount > 0 && allowedImports === undefined) {
      fail(
        `'${relativePath}' directly imports service modules. Route transport and persistence concerns through hooks or add an explicit baseline entry if this is a deliberate exception.`,
        failures,
      );
    }

    if (allowedImports !== undefined && serviceImportCount > allowedImports) {
      fail(
        `'${relativePath}' imports ${serviceImportCount} service modules, exceeding its current baseline of ${allowedImports}. Avoid increasing component-level service coupling.`,
        failures,
      );
    }
  }

  if (isTsFile && frontendSharedLayerPrefixes.some((prefix) => relativePath.startsWith(prefix))) {
    const pageImport = imports.find(isPageImport);
    if (pageImport) {
      fail(
        `'${relativePath}' imports '${pageImport}'. Shared modules must not depend on page modules.`,
        failures,
      );
    }
  }

  if (isTsFile && (relativePath.startsWith("frontend/src/services/") || relativePath.startsWith("frontend/src/utils/"))) {
    const componentImport = imports.find(isComponentImport);
    if (componentImport) {
      fail(
        `'${relativePath}' imports '${componentImport}'. Services and utilities must stay UI-agnostic.`,
        failures,
      );
    }
  }

  const isBackendTestFile = /(^|\/)test_.*\.py$/.test(relativePath);
  if (!isBackendTestFile && (relativePath.startsWith(backendServicePrefix) || relativePath.startsWith(backendPipelinePrefix))) {
    const apiImport = imports.find(isApiModuleImport);
    if (apiImport) {
      fail(
        `'${relativePath}' imports '${apiImport}'. Backend services and pipelines must not depend on the API transport layer.`,
        failures,
      );
    }
  }
}

if (failures.length > 0) {
  console.error("Static governance checks failed:");
  for (const failure of failures) {
    console.error(`- ${failure}`);
  }
  process.exit(1);
}

console.log("Static governance checks passed.");
