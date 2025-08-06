# Services Architecture

## Domain-Driven Organization

Services are organized by domain for maximum modularity and scalability:

```
services/
├── plss/                    # PLSS (Public Land Survey System) domain
│   ├── dataService.ts       # Core data operations
│   └── index.ts            # Domain exports
├── imageProcessingApi.ts    # Image processing operations
├── textToSchemaApi.ts      # Text-to-schema conversion
├── polygonApi.ts           # Polygon operations
├── mappingApi.ts           # General mapping operations
└── consensusApi.ts         # Consensus algorithms
```

## Design Principles

### 1. **Domain Boundaries**
Each domain (PLSS, imaging, etc.) is self-contained with:
- Clear data models
- Focused responsibilities  
- Minimal cross-domain dependencies

### 2. **Single Responsibility**
Each service handles one specific concern:
- `dataService.ts` - Pure data operations
- `validationService.ts` - Business rules validation
- `cacheService.ts` - Caching strategies

### 3. **Scalable Growth**
New features have obvious homes:
- PLSS features → `plss/` domain
- New domains → New subdirectories
- Shared utilities → Domain-agnostic files

## Usage Examples

```typescript
// Clean domain imports
import { plssDataService, PLSSDataState } from '../services/plss';
import { imageProcessingApi } from '../services/imageProcessingApi';

// Domain-specific operations
const plssData = await plssDataService.checkDataStatus('Wyoming');
const imageResult = await imageProcessingApi.processImage(file);
```

## Benefits

✅ **Clear Ownership** - Easy to find responsible code  
✅ **No Conflicts** - Domain isolation prevents interference  
✅ **Easy Testing** - Focused scope for unit tests  
✅ **Team Scalability** - Multiple developers can work independently  
✅ **Future-Proof** - Architecture scales with feature growth