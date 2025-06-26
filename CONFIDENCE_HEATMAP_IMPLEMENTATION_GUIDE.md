# 🔴 CONFIDENCE HEATMAP IMPLEMENTATION GUIDE 🔴
## Critical Architecture Documentation

---

## 🎯 **OVERVIEW**
This document outlines the implementation of the Confidence Heatmap feature that visualizes word-level confidence scores from redundancy analysis and allows interactive editing of contested words.

---

## 🔒 **CRITICAL PRESERVATION RULES**

### **❌ DO NOT MODIFY THESE EXISTING COMPONENTS:**
1. **ImageProcessingWorkspace.tsx** - Core state management and API integration
2. **DraftSelector.tsx** - Existing draft selection functionality  
3. **Backend pipeline.py** - Consensus calculation and redundancy analysis
4. **API response format** - Must maintain existing structure
5. **CSS positioning** - Draft selector positioning must remain functional

### **✅ SAFE TO ADD:**
1. New `ConfidenceHeatmapViewer.tsx` component
2. New `HeatmapToggle.tsx` component  
3. New CSS classes for heatmap styling
4. New state variables for heatmap mode
5. Optional props to existing components

---

## 📊 **DATA FLOW ARCHITECTURE**

### **Backend Data Structure (ALREADY EXISTS - DO NOT MODIFY):**
```typescript
redundancy_analysis: {
  word_confidence_map: {
    "word_0": 1.0,    // 100% confidence
    "word_1": 0.67,   // 67% confidence  
    "word_2": 0.33,   // 33% confidence
    // ... for each word in consensus text
  },
  individual_results: [
    {
      success: true,
      text: "Draft 1 full text...",
      tokens: 1234,
      error?: string
    },
    // ... more drafts
  ],
  consensus_text: "Formatted consensus text...",
  best_formatted_text: "Best formatted text...",
  best_result_index: 0
}
```

### **Frontend Data Flow:**
```
1. User toggles heatmap mode
2. ConfidenceHeatmapViewer receives:
   - Current text (consensus/best/draft)
   - word_confidence_map from redundancy_analysis
   - individual_results for alternatives
3. Component parses text into words with confidence scores
4. Renders words with color-coded backgrounds
5. Shows popup with alternatives on hover
6. Allows editing when unlocked
```

---

## 🏗️ **IMPLEMENTATION PLAN**

### **Step 1: Create HeatmapToggle Component**
**File:** `frontend/src/components/HeatmapToggle.tsx`

**Purpose:** Toggle button positioned near DraftSelector

**Critical Requirements:**
- Position: `top: 60px, right: 80px` (staggered from DraftSelector)
- Must use AnimatedBorder for consistency
- Must not interfere with DraftSelector functionality
- Only visible when redundancy data exists

**Interface:**
```typescript
interface HeatmapToggleProps {
  isEnabled: boolean;
  onToggle: (enabled: boolean) => void;
  hasRedundancyData: boolean;
}
```

### **Step 2: Create ConfidenceHeatmapViewer Component**
**File:** `frontend/src/components/ConfidenceHeatmapViewer.tsx`

**Purpose:** Display text with confidence-based coloring and interactive editing

**Critical Requirements:**
- Must preserve original text formatting (whitespace, line breaks)
- Must handle missing confidence data gracefully
- Must not break when redundancy_analysis is undefined
- Must maintain text selection/copy functionality

**Interface:**
```typescript
interface ConfidenceHeatmapViewerProps {
  text: string;
  wordConfidenceMap: Record<string, number>;
  redundancyAnalysis?: RedundancyAnalysis;
  onTextUpdate?: (updatedText: string) => void;
  isReadOnly?: boolean;
}
```

### **Step 3: Add Heatmap State to ImageProcessingWorkspace**
**File:** `frontend/src/components/ImageProcessingWorkspace.tsx`

**Critical Integration Points:**
```typescript
// ADD these state variables (SAFE)
const [isHeatmapEnabled, setIsHeatmapEnabled] = useState(false);

// MODIFY the text display section (lines ~566-568)
// Replace <pre>{getCurrentText()}</pre> with conditional rendering

// ADD HeatmapToggle component near DraftSelector (lines ~555)
```

**Integration Rules:**
- Add heatmap state AFTER existing state declarations
- Add HeatmapToggle AFTER DraftSelector in the JSX
- Replace text display with conditional component
- DO NOT modify existing state variable names
- DO NOT modify existing function signatures

### **Step 4: Add CSS Styling**
**File:** `frontend/styles/components/results.css`

**Critical Styling Requirements:**
- Heatmap toggle positioning must not conflict with DraftSelector
- Word highlighting must be subtle and readable
- Popup must have high z-index (1000+) to appear above all content
- Must work in both light and dark themes

---

## 🎨 **UI/UX SPECIFICATIONS**

### **Heatmap Toggle Button:**
- **Icon:** 🌡️ (thermometer) or 🎨 (palette)
- **Position:** `top: 60px, right: 80px` (40px offset from DraftSelector)
- **Size:** 28x28px (same as DraftSelector bubble)
- **Animation:** Uses AnimatedBorder when hovered
- **Tooltip:** None (following DraftSelector pattern)

### **Confidence Color Scheme:**
```css
/* High Confidence (80-100%) */
background: rgba(34, 197, 94, 0.1-0.3);  /* Green */

/* Medium Confidence (50-79%) */  
background: rgba(234, 179, 8, 0.2-0.5);  /* Yellow */

/* Low Confidence (0-49%) */
background: rgba(239, 68, 68, 0.3-0.7);  /* Red */
```

### **Word Interaction States:**
- **Default:** Subtle background highlighting
- **Hover:** Slightly darker background + popup
- **Editing:** Input field replaces word
- **Contested:** Pointer cursor for words with alternatives

### **Popup Design:**
```
┌─────────────────────┐
│ Confidence: 67%  🔓 │ <- Header with unlock button
├─────────────────────┤
│ Alternatives:       │
│ • jumps (2 drafts)  │ <- Clickable alternatives
│ • leaps (1 draft)   │
└─────────────────────┘
```

---

## 🔧 **CRITICAL INTEGRATION POINTS**

### **1. Text Display Logic (ImageProcessingWorkspace.tsx)**
**Current Code (lines ~566-568):**
```typescript
{activeTab === 'text' && (
  <pre>{getCurrentText()}</pre>
)}
```

**New Code:**
```typescript
{activeTab === 'text' && (
  isHeatmapEnabled && selectedResult?.result?.metadata?.redundancy_analysis ? (
    <ConfidenceHeatmapViewer
      text={getCurrentText()}
      wordConfidenceMap={selectedResult.result.metadata.redundancy_analysis.word_confidence_map || {}}
      redundancyAnalysis={selectedResult.result.metadata.redundancy_analysis}
      onTextUpdate={handleTextUpdate}
    />
  ) : (
    <pre>{getCurrentText()}</pre>
  )
)}
```

### **2. HeatmapToggle Positioning (ImageProcessingWorkspace.tsx)**
**Add after DraftSelector (line ~555):**
```typescript
{/* Heatmap Toggle - positioned with offset from DraftSelector */}
<HeatmapToggle
  isEnabled={isHeatmapEnabled}
  onToggle={setIsHeatmapEnabled}
  hasRedundancyData={!!selectedResult?.result?.metadata?.redundancy_analysis}
/>
```

### **3. Text Update Handler (ImageProcessingWorkspace.tsx)**
**Add new function:**
```typescript
const handleTextUpdate = useCallback((updatedText: string) => {
  // Update the selected result with new text
  if (selectedResult && selectedResult.result) {
    const updatedResult = {
      ...selectedResult,
      result: {
        ...selectedResult.result,
        extracted_text: updatedText
      }
    };
    
    // Update in session results
    setSessionResults(prev => 
      prev.map(result => 
        result === selectedResult ? updatedResult : result
      )
    );
    
    setSelectedResult(updatedResult);
  }
}, [selectedResult, setSessionResults]);
```

---

## 🧪 **TESTING CHECKPOINTS**

### **Before Implementation:**
1. ✅ Current redundancy system works
2. ✅ DraftSelector functions correctly
3. ✅ Text display shows properly
4. ✅ Enhancement controls work

### **After Each Step:**
1. **After HeatmapToggle:** 
   - DraftSelector still works
   - Toggle appears in correct position
   - No visual conflicts

2. **After ConfidenceHeatmapViewer:**
   - Component renders without errors
   - Handles missing data gracefully
   - Text formatting preserved

3. **After Integration:**
   - Normal text view still works
   - Heatmap view displays correctly
   - Toggle switches between modes
   - Editing functionality works

4. **After CSS:**
   - Colors are readable
   - Popup appears correctly
   - No layout issues

---

## 🚨 **FAILURE PREVENTION**

### **Common Pitfalls to Avoid:**
1. **Breaking DraftSelector positioning** - Use different CSS classes
2. **Modifying existing state** - Only add new state variables
3. **Breaking text formatting** - Preserve whitespace in heatmap viewer
4. **API changes** - Don't modify backend response structure
5. **Performance issues** - Memoize expensive calculations

### **Rollback Strategy:**
If any step breaks existing functionality:
1. Comment out new components
2. Revert to `<pre>{getCurrentText()}</pre>`
3. Remove new state variables
4. Test that original functionality works
5. Fix issues before proceeding

---

## 📋 **IMPLEMENTATION CHECKLIST**

- [ ] Create HeatmapToggle.tsx component
- [ ] Create ConfidenceHeatmapViewer.tsx component  
- [ ] Add heatmap state to ImageProcessingWorkspace
- [ ] Add HeatmapToggle to UI layout
- [ ] Implement conditional text display
- [ ] Add handleTextUpdate function
- [ ] Create CSS for heatmap styling
- [ ] Test with redundancy enabled
- [ ] Test with redundancy disabled
- [ ] Test text editing functionality
- [ ] Verify no existing functionality broken

---

## 🎯 **SUCCESS CRITERIA**

✅ **Feature Complete When:**
1. Toggle button appears near DraftSelector when redundancy data exists
2. Heatmap mode colors words based on confidence scores
3. Hovering contested words shows alternatives popup
4. Users can edit words by unlocking and typing/clicking alternatives
5. All existing functionality (DraftSelector, enhancement, etc.) still works
6. No performance degradation in normal text view
7. Graceful handling of edge cases (no redundancy data, single draft, etc.)

This implementation will provide a powerful visualization and editing tool while maintaining the stability and functionality of the existing system. 