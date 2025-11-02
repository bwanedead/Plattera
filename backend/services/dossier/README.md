# Dossier Management System - Enhanced Implementation

## 🎯 Addressed Improvements

Based on architectural review, the following enhancements have been implemented to address blind spots and prepare for future scalability:

### ✅ 1. Provenance Schema Implementation

**File**: `provenance_schema.py`

**Features**:
- **Standardized Metadata**: Consistent schema for all transcription provenance
- **File Integrity**: SHA256 hashing of source files
- **Lineage Tracking**: Parent/child relationships for reruns
- **Quality Metrics**: Confidence scores, text length, section counts
- **Engine Tracking**: OCR engine, model, processing date
- **Validation**: Schema validation and error handling

**Example Usage**:
```python
# Create provenance for new transcription
provenance = ProvenanceSchema.create_initial_provenance(
    file_path="/uploads/deed.jpg",
    processing_engine="openai",
    model="gpt-4o",
    extraction_mode="legal_document_json"
)

# Update with quality metrics
provenance = ProvenanceSchema.update_provenance_quality(
    provenance, confidence_score=0.92, text_length=2847, section_count=4
)
```

### ✅ 2. Segment Abstraction Layer

**File**: `models.py` - Added `Segment` class

**Purpose**: Placeholder for future `segment` vs `run` distinction

**Current State**: Maps 1:1 with transcriptions (as discussed)
**Future State**: Will allow multiple runs of the same logical document segment

```python
class Segment:
    """Logical document segment (page, section, etc.)"""
    segment_id: str
    description: str  # e.g., "Page 1 Left Side"
    metadata: Dict    # Custom properties
```

### ✅ 3. Active Text Source Hook

**File**: `models.py` - Enhanced `Dossier` class

**Purpose**: Prepare for consensus integration

**Implementation**:
```python
class Dossier:
    # ... existing fields ...
    active_text_source: Optional[Dict] = None
    # Format: {"type": "alignment"|"llm"|"individual", "id": "..."}
```

**Usage**:
```python
# Set active consensus source
dossier.set_active_text_source("alignment", "consensus_123")

# Future: Stitched views will respect this setting
active_source = dossier.get_active_text_source()
```

### ✅ 4. Neutral Ordering

**Updated**: `TranscriptionEntry.position` documentation

**Clarification**: Position field is now explicitly documented as a "sequence index" rather than implying visual layout (left/right positioning).

### ✅ 5. Draft Selection Policy Documentation

**Added**: Clear documentation for how stitched views select which transcription draft to use:

```python
def get_stitched_draft_selection_policy():
    """
    Policy for selecting which draft to use in stitched views:
    1. Latest edited draft (if available)
    2. Normalized draft (if available)
    3. Raw transcription (fallback)
    """
```

---

## 🔧 Integration Improvements

### Enhanced Processing Endpoint

**File**: `backend/api/endpoints/processing.py`

**New Features**:
- **Automatic Provenance Creation**: Every dossier-associated transcription gets standardized provenance
- **Rich Metadata**: Processing parameters, quality metrics, lineage tracking
- **Error Resilience**: Provenance creation failures don't break transcription processing

**Example Association**:
```json
{
  "transcription_id": "draft_1",
  "position": 1,
  "metadata": {
    "auto_added": true,
    "source": "processing_api",
    "processing_params": {
      "model": "gpt-4o",
      "extraction_mode": "legal_document_json",
      "redundancy_count": 3
    },
    "provenance": {
      "version": "1.0",
      "source": {"file_hash": "a665...", "file_size_bytes": 2457600},
      "processing": {"engine": "openai", "model": "gpt-4o"},
      "quality": {"confidence_score": 0.92, "estimated_accuracy": "high"}
    }
  }
}
```

---

## 🚀 Future-Proofing Benefits

### 1. **Consensus Integration Ready**
- `active_text_source` field allows seamless addition of consensus methods
- Provenance schema supports comparing different consensus approaches
- Stitched views can dynamically select text sources

### 2. **Rerun Support Prepared**
- Segment abstraction allows multiple runs of same logical segment
- Lineage tracking in provenance supports rerun relationships
- Quality metrics enable comparison of different processing attempts

### 3. **Scalability Prepared**
- JSON storage matches existing patterns (easy migration path)
- Independent services can scale horizontally
- Repository abstraction ready for future database integration

### 4. **Search Enhancement Ready**
- Provenance metadata provides rich search/filtering capabilities
- Quality metrics enable accuracy-based filtering
- Lineage tracking supports rerun discovery

---

## 📊 Quality Improvements

### Provenance Standards
- **Consistency**: All transcriptions have standardized metadata schema
- **Auditability**: Complete processing history and file integrity checks
- **Comparability**: Quality metrics enable side-by-side draft comparison

### Error Handling
- **Graceful Degradation**: Provenance failures don't break core functionality
- **Detailed Logging**: Comprehensive error tracking and debugging
- **Recovery**: Automatic fallbacks for missing or corrupted metadata

### Documentation
- **Clear Policies**: Explicit draft selection and stitching rules
- **Schema Examples**: Real-world usage examples and edge cases
- **Migration Path**: Clear upgrade path for future enhancements

---

## 🎯 Impact Assessment

### ✅ **Strengths Preserved**
- Zero breaking changes to existing functionality
- Clean modular architecture maintained
- JSON-based storage compatibility retained

### ✅ **Blind Spots Addressed**
- Provenance schema prevents future metadata inconsistencies
- Segment abstraction enables rerun workflows
- Active text source prepares for consensus integration
- Neutral ordering prevents UI layout assumptions
- Draft selection policy provides clear stitching rules

### ✅ **Scalability Enhanced**
- Independent services enable horizontal scaling
- Repository abstraction eases future database migration
- Provenance standards support advanced search capabilities

---

## 🔄 Next Steps

1. **UI Development**: Build frontend components using these enhanced APIs
2. **Testing**: Comprehensive API testing with provenance validation
3. **Performance**: Optimize for production workloads
4. **Documentation**: API documentation and user guides
5. **Migration**: Plan database migration when scale requires it

**The foundation is now rock-solid for iterative development and future consensus integration!** 🚀

---

## **🖼️ Image Storage & Enhancement Tracking**

### **New Capabilities**
- ✅ **Original Image Storage**: Automatic saving of source images for future reference
- ✅ **Enhancement Tracking**: Complete record of enhancement settings applied
- ✅ **Image Retrieval**: API endpoints to retrieve stored images
- ✅ **Provenance Enhancement**: Image paths and settings in provenance schema

### **Storage Structure**
```
backend/dossiers/images/
├── original/                    # Original source images
│   ├── draft_1_original.jpg
│   └── draft_2_original.png
└── processed/                   # Processed/enhanced images
    ├── draft_1_processed.jpg
    └── draft_2_processed.png
```

### **New API Endpoints**
```
GET    /api/dossier-views/transcription/{tid}/images       # Image info
GET    /api/dossier-views/transcription/{tid}/image/{type} # Retrieve image
GET    /api/dossier-views/transcription/{tid}/enhancement  # Enhancement settings
GET    /api/dossier-views/images/stats                     # Storage statistics
```

### **Enhanced Provenance Schema**
```json
{
  "enhancement": {
    "settings_applied": {"contrast": 2.0, "brightness": 1.5},
    "original_image_path": "/dossiers/images/original/draft_1_original.jpg",
    "processed_image_path": "/temp/processed_image.jpg",
    "enhancement_hash": "abc123...",
    "settings_summary": "contrast=2.0, brightness=1.5"
  }
}
```

### **Automatic Processing Integration**
- ✅ **Image Saving**: Original images automatically saved when `dossier_id` provided
- ✅ **Settings Recording**: Enhancement parameters captured in provenance
- ✅ **Path Tracking**: Both original and processed image paths stored
- ✅ **Change Detection**: Enhancement hash enables detecting setting changes

### **Benefits for Users**
- **Reproducibility**: Exact enhancement settings preserved for future reference
- **Reprocessing**: Users can retrieve original images and apply different settings
- **Audit Trail**: Complete record of image processing history
- **Debugging**: Inspect exact images that produced specific transcriptions
- **Optimization**: Compare results with different enhancement combinations
