/*
🔴 CRITICAL DRAFT SELECTOR COMPONENT DOCUMENTATION 🔴
====================================================

THIS COMPONENT MANAGES REDUNDANCY DRAFT SELECTION - CRITICAL FOR HEATMAP FEATURE

CRITICAL STRUCTURES THAT MUST BE PRESERVED:
==========================================

1. POSITIONING (CRITICAL - DO NOT MODIFY):
   - CSS Classes: .draft-selector-collapsed, .draft-selector-expanded
   - Position: top: 60px, right: 40px (defined in results.css)
   - Z-index: 10 (must remain above content but below popups)
   - Size: 28x28px bubble (matches navigation buttons)

2. REDUNDANCY ANALYSIS INTERFACE (CRITICAL - REQUIRED FOR HEATMAP):
   ```typescript
   redundancyAnalysis?: {
     individual_results: Array<{          // ← HEATMAP NEEDS THIS for alternatives
       success: boolean,
       text: string,                      // ← HEATMAP NEEDS THIS for word alternatives
       tokens: number,
       error?: string
     }>,
     consensus_text: string,              // ← HEATMAP NEEDS THIS for consensus view
     best_formatted_text: string,        // ← HEATMAP NEEDS THIS for best view
     best_result_index: number,           // ← HEATMAP NEEDS THIS for marking best draft
     word_confidence_map?: Record<string, number>  // ← HEATMAP NEEDS THIS for coloring
   }
   ```

3. DRAFT SELECTION CALLBACK (CRITICAL - HEATMAP INTEGRATION POINT):
   - onDraftSelect: (draftIndex: number | 'consensus' | 'best') => void
   - This callback MUST continue to work for heatmap text switching
   - selectedDraft state MUST remain compatible

4. ANIMATEDBORDER INTEGRATION (CRITICAL - CONSISTENCY):
   - Uses AnimatedBorder component with isHovered state
   - borderRadius: 6, strokeWidth: 2
   - Must maintain same animation timing as navigation

SAFE ADDITIONS FOR HEATMAP FEATURE:
==================================

✅ SAFE TO ADD:
- Additional CSS classes for heatmap-related styling
- New optional props (with default values)
- Additional state for heatmap-specific features
- Event handlers that don't conflict with existing ones

❌ DO NOT MODIFY:
- Existing CSS class names (.draft-selector-collapsed, .draft-selector-expanded)
- Position values (top: 60px, right: 40px)
- AnimatedBorder integration pattern
- Core redundancyAnalysis interface structure
- onDraftSelect callback signature
- Existing state variable names (isVisible, isDropdownOpen, isHovered)

HEATMAP INTEGRATION REQUIREMENTS:
===============================

1. POSITIONING COORDINATION:
   - HeatmapToggle must use DIFFERENT position (right: 80px) to avoid overlap
   - Must maintain z-index hierarchy: HeatmapToggle(10) < DraftSelector(10) < Popups(1000+)

2. DATA SHARING:
   - HeatmapViewer will need access to same redundancyAnalysis data
   - Must preserve individual_results array for word alternatives
   - Must preserve word_confidence_map for confidence coloring

3. STATE COORDINATION:
   - DraftSelector selectedDraft state affects which text HeatmapViewer displays
   - Both components must respond to same draft selection changes
   - Text editing in HeatmapViewer may require draft re-evaluation

CRITICAL WIRING POINTS:
======================

1. PARENT COMPONENT INTEGRATION (ImageProcessingWorkspace):
   - Receives redundancyAnalysis from selectedResult.result.metadata.redundancy_analysis
   - onDraftSelect callback updates selectedDraft state in parent
   - Parent's getCurrentText() function uses selectedDraft to determine displayed text

2. CSS DEPENDENCIES (results.css):
   - .draft-selector-collapsed { position: absolute; top: 60px; right: 40px; z-index: 10; }
   - .draft-selector-expanded { position: absolute; top: 60px; right: 40px; z-index: 10; }
   - .draft-selector-bubble { width: 28px; height: 28px; }

3. ANIMATEDBORDER DEPENDENCIES:
   - Requires isHovered state management
   - Uses borderRadius and strokeWidth props
   - Timing must match ParcelTracerLoader (600ms intervals, 1.2s pulse)

TESTING CHECKPOINTS FOR HEATMAP INTEGRATION:
===========================================

BEFORE modifying this component:
1. ✅ Verify draft selection works (best/consensus/individual drafts)
2. ✅ Verify positioning doesn't conflict with other UI elements
3. ✅ Verify AnimatedBorder animations work correctly
4. ✅ Verify redundancy data is properly passed and displayed

AFTER heatmap integration:
1. ✅ Draft selection still works unchanged
2. ✅ Positioning remains correct with new HeatmapToggle
3. ✅ No visual conflicts or overlapping elements
4. ✅ AnimatedBorder still functions properly
5. ✅ Heatmap responds correctly to draft changes

FAILURE PREVENTION:
==================

Common mistakes that would break heatmap integration:
- Changing CSS positioning values (breaks layout coordination)
- Modifying redundancyAnalysis interface (breaks data flow)
- Changing onDraftSelect signature (breaks parent integration)
- Modifying AnimatedBorder usage (breaks visual consistency)

If this component breaks, heatmap feature will lose:
- Draft switching capability
- Access to individual draft texts for alternatives
- Consistent positioning reference point
- Visual consistency with animated borders
*/

import React, { useState } from 'react';
import { AnimatedBorder } from '../AnimatedBorder';

// CRITICAL INTERFACE - Required for heatmap feature data flow
interface DraftSelectorProps {
  redundancyAnalysis?: {
    individual_results: Array<{
      success: boolean;
      text: string;                    // ← CRITICAL: Heatmap needs this for word alternatives
      tokens: number;
      error?: string;
    }>;
    consensus_text: string;            // ← CRITICAL: Heatmap needs this for consensus display
    best_formatted_text: string;      // ← CRITICAL: Heatmap needs this for best display
    best_result_index: number;        // ← CRITICAL: Heatmap needs this for marking best
    word_confidence_map?: Record<string, number>; // ← CRITICAL: Heatmap needs this for coloring
  };
  onDraftSelect: (draftIndex: number | 'consensus' | 'best') => void; // ← CRITICAL: Heatmap text switching
  selectedDraft: number | 'consensus' | 'best';                       // ← CRITICAL: Heatmap display coordination
}

export const DraftSelector: React.FC<DraftSelectorProps> = ({
  redundancyAnalysis,
  onDraftSelect,
  selectedDraft
}) => {
  // CRITICAL STATE VARIABLES - DO NOT RENAME (heatmap positioning depends on these)
  const [isVisible, setIsVisible] = useState(false);
  const [isDropdownOpen, setIsDropdownOpen] = useState(false);
  const [isHovered, setIsHovered] = useState(false);  // ← CRITICAL: AnimatedBorder dependency

  // CRITICAL GUARD CLAUSE - Heatmap feature depends on this behavior
  if (!redundancyAnalysis || !redundancyAnalysis.individual_results) {
    return null;
  }

  const successfulResults = redundancyAnalysis.individual_results.filter(r => r.success);
  const totalDrafts = successfulResults.length;
  const bestDraftIndex = redundancyAnalysis.best_result_index;

  // Show selector even for single draft (transparency about what user is viewing)
  // Only hide if no successful results at all
  if (totalDrafts === 0) {
    return null; // No results to show
  }

  // CRITICAL CALLBACK - Heatmap integration point for draft switching
  const handleDraftSelect = (draft: number | 'consensus' | 'best') => {
    onDraftSelect(draft);  // ← CRITICAL: Must trigger parent state update for heatmap
    setIsDropdownOpen(false);
  };

  // CRITICAL LABELING FUNCTION - Updated to remove "best" option and add stars
  const getCurrentDraftLabel = () => {
    if (selectedDraft === 'consensus') return 'Consensus';
    if (selectedDraft === 'best') return `Draft ${bestDraftIndex + 1} ⭐`; // Fallback for existing "best" selections
    const draftNumber = selectedDraft + 1;
    const isBest = selectedDraft === bestDraftIndex;
    return `Draft ${draftNumber}${isBest ? ' ⭐' : ''}`;
  };

  const toggleVisibility = () => {
    setIsVisible(!isVisible);
    if (!isVisible) {
      setIsDropdownOpen(false); // Close dropdown when hiding
    }
  };

  // CRITICAL COLLAPSED STATE - Position: top: 60px, right: 40px (DO NOT MODIFY)
  if (!isVisible) {
    return (
      <div className="draft-selector-collapsed">  {/* ← CRITICAL CSS CLASS - positioning reference for heatmap */}
        <AnimatedBorder
          isHovered={isHovered}      // ← CRITICAL: Must maintain for visual consistency
          borderRadius={6}           // ← CRITICAL: Must match heatmap toggle styling
          strokeWidth={2}            // ← CRITICAL: Must match heatmap toggle styling
        >
          <button 
            className="draft-selector-bubble"  // ← CRITICAL CSS CLASS - size reference (28x28px)
            onClick={toggleVisibility}
            onMouseEnter={() => setIsHovered(true)}    // ← CRITICAL: AnimatedBorder dependency
            onMouseLeave={() => setIsHovered(false)}   // ← CRITICAL: AnimatedBorder dependency
          >
            {totalDrafts}  {/* ← CRITICAL: Heatmap feature depends on draft count display */}
          </button>
        </AnimatedBorder>
      </div>
    );
  }

  // CRITICAL EXPANDED STATE - Position: top: 60px, right: 40px (DO NOT MODIFY)
  return (
    <div className="draft-selector-expanded">  {/* ← CRITICAL CSS CLASS - positioning reference */}
      <div className="draft-selector-header">
        <div className="draft-header-left">
          <span className="draft-label">Drafts</span>
          <span className="draft-count-badge">{totalDrafts}</span>  {/* ← CRITICAL: Heatmap needs draft count */}
        </div>
        <button 
          className="draft-close-btn"
          onClick={toggleVisibility}
        >
          ×
        </button>
      </div>
      
      <div className="draft-current-selection">
        <button 
          className="draft-current-btn"
          onClick={() => setIsDropdownOpen(!isDropdownOpen)}
        >
          <span className="current-draft-name">{getCurrentDraftLabel()}</span>  {/* ← CRITICAL: Heatmap UI consistency */}
          <span className={`dropdown-arrow ${isDropdownOpen ? 'open' : ''}`}>▼</span>
        </button>
      </div>
      
      {isDropdownOpen && (
        <div className="draft-dropdown">
          {/* UPDATED: Only show individual drafts, with stars for best draft */}
          {successfulResults.map((result, index) => {
            const isBest = index === bestDraftIndex;
            return (
              <div 
                key={index}
                className={`draft-item ${selectedDraft === index ? 'active' : ''}`}
                onClick={() => handleDraftSelect(index)}  // ← CRITICAL: Triggers heatmap individual draft view
              >
                <span className="draft-name">
                  Draft {index + 1}{isBest ? ' ⭐' : ''}
                </span>
                <span className="draft-desc">{result.tokens} tokens</span>  {/* ← INFO: Heatmap may display this */}
              </div>
            );
          })}
          
          {/* OPTIONAL: Keep consensus option if available */}
          {redundancyAnalysis.consensus_text && (
            <div 
              className={`draft-item ${selectedDraft === 'consensus' ? 'active' : ''}`}
              onClick={() => handleDraftSelect('consensus')}
            >
              <span className="draft-name">Consensus</span>
              <span className="draft-desc">Combined</span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}; 