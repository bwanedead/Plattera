# API Services Architecture

## Overview

The API services have been refactored following clean architecture principles to separate concerns and improve maintainability. Each service has a single responsibility and can be imported independently.

## Structure

```
services/
├── index.ts                 # Central exports for all services
├── imageProcessingApi.ts    # Image processing API calls
├── modelApi.ts             # Model management API calls
├── alignmentApi.ts         # Alignment engine API calls
└── README.md               # This documentation
```

## Services

### 🖼️ Image Processing API (`imageProcessingApi.ts`)
**Responsibility:** Handle file upload and image-to-text processing

**Exports:**
- `processFilesAPI(files, model, mode, enhancementSettings, redundancySettings)`

**Usage:**
```typescript
import { processFilesAPI } from '../services/imageProcessingApi';
// OR
import { processFilesAPI } from '../services';

const results = await processFilesAPI(files, model, mode, enhancementSettings, redundancySettings);
```

### 🤖 Model API (`modelApi.ts`)
**Responsibility:** Fetch and manage available AI models

**Exports:**
- `fetchModelsAPI()`

**Usage:**
```typescript
import { fetchModelsAPI } from '../services/modelApi';
// OR
import { fetchModelsAPI } from '../services';

const models = await fetchModelsAPI();
```

### 🧬 Alignment API (`alignmentApi.ts`)
**Responsibility:** Handle draft alignment and consensus analysis

**Exports:**
- `alignDraftsAPI(drafts, consensusStrategy)`

**Usage:**
```typescript
import { alignDraftsAPI } from '../services/alignmentApi';
// OR
import { alignDraftsAPI } from '../services';

const alignmentResult = await alignDraftsAPI(drafts, consensusStrategy);
```

## Central Import (`index.ts`)

For convenience, all services can be imported from a single location:

```typescript
import { 
  processFilesAPI, 
  fetchModelsAPI, 
  alignDraftsAPI 
} from '../services';
```

## Migration Guide

### Before (Old Structure)
```typescript
import { processFilesAPI, fetchModelsAPI, alignDraftsAPI } from '../services/imageProcessingApi';
```

### After (New Structure)
```typescript
// Option 1: Import from specific services
import { processFilesAPI } from '../services/imageProcessingApi';
import { fetchModelsAPI } from '../services/modelApi';
import { alignDraftsAPI } from '../services/alignmentApi';

// Option 2: Import from central index
import { processFilesAPI, fetchModelsAPI, alignDraftsAPI } from '../services';
```

## Benefits

- ✅ **Single Responsibility:** Each service has one clear purpose
- ✅ **Maintainability:** Changes to one API don't affect others
- ✅ **Testability:** Each service can be tested independently
- ✅ **Scalability:** New API endpoints can be added without cluttering existing files
- ✅ **Type Safety:** Proper TypeScript types for each service
- ✅ **Clean Imports:** Choose between specific or centralized imports

## Error Handling

Each service maintains its own error handling patterns appropriate to its domain:

- **Image Processing:** File-level error tracking with detailed error messages
- **Model API:** Graceful fallback to default models when API is unavailable
- **Alignment API:** Structured error responses with confidence metrics

## Future Additions

When adding new API functionality:

1. Create a new service file (e.g., `boundingBoxApi.ts`)
2. Follow the same pattern with single responsibility
3. Add exports to `index.ts`
4. Update this documentation 