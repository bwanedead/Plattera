"""
BioPython Alignment Visualizer Module
====================================

Generates HTML visualization with aligned text, confidence heatmaps, and suggestion panels
for BioPython alignment results.
"""

import logging
import base64
import io
from typing import Dict, List, Any, Optional
from pathlib import Path

logger = logging.getLogger(__name__)

# Check visualization dependencies
try:
    import matplotlib.pyplot as plt
    import seaborn as sns
    import numpy as np
    VISUALIZATION_AVAILABLE = True
except ImportError:
    VISUALIZATION_AVAILABLE = False
    logger.warning("❌ Visualization libraries not available - install with: pip install seaborn matplotlib")


class BioPythonAlignmentVisualizer:
    """Generates visualizations for BioPython alignment results"""
    
    def __init__(self):
        self.confidence_colors = {
            'high': '#28a745',    # Green
            'medium': '#ffc107',  # Yellow
            'low': '#dc3545'      # Red
        }
        
        self.difference_color = '#fd7e14'  # Orange for differences
    
    def generate_complete_visualization(self, alignment_results: Dict[str, Any],
                                      confidence_results: Dict[str, Any],
                                      difference_results: Dict[str, Any]) -> str:
        """
        Generate complete HTML visualization with all components
        
        Args:
            alignment_results: Results from consistency aligner
            confidence_results: Results from confidence scorer
            difference_results: Results from difference detection
            
        Returns:
            str: Complete HTML content
        """
        logger.info("🎨 VISUALIZATION ► Generating complete HTML visualization")
        
        try:
            # Generate individual components
            aligned_text_html = self._generate_aligned_text_html(
                alignment_results, confidence_results
            )
            
            heatmap_data = confidence_results.get('block_confidences', {})
            heatmap_html = self._generate_heatmap_html(heatmap_data)
            
            suggestion_panel_html = self._generate_suggestion_panel_html(
                difference_results.get('formatted_differences', [])
            )
            
            summary_html = self._generate_summary_html(
                alignment_results, confidence_results, difference_results
            )
            
            # Combine into complete HTML page
            complete_html = self._create_complete_html_page(
                aligned_text_html, heatmap_html, suggestion_panel_html, summary_html
            )
            
            logger.info("✅ VISUALIZATION COMPLETE ► HTML generated successfully")
            return complete_html
            
        except Exception as e:
            logger.error(f"❌ Visualization generation failed: {e}")
            return self._generate_error_html(str(e))
    
    def _generate_aligned_text_html(self, alignment_results: Dict[str, Any],
                                   confidence_results: Dict[str, Any]) -> str:
        """Generate HTML for aligned text with confidence coloring"""
        html_parts = ['<div class="aligned-text-section">']
        html_parts.append('<h2>📝 Aligned Text by Block</h2>')
        
        for block_id, block_data in alignment_results.get('blocks', {}).items():
            aligned_sequences = block_data.get('aligned_sequences', [])
            
            if not aligned_sequences:
                continue
            
            # Get confidence data for this block
            block_confidence = confidence_results.get('block_confidences', {}).get(block_id, {})
            confidence_levels = block_confidence.get('confidence_levels', [])
            
            html_parts.append(f'<div class="block-section" id="block-{block_id}">')
            html_parts.append(f'<h3>Block: {block_id}</h3>')
            
            # Generate aligned text for each draft
            for seq_data in aligned_sequences:
                draft_id = seq_data['draft_id']
                tokens = seq_data['tokens']
                
                html_parts.append(f'<div class="draft-row">')
                html_parts.append(f'<span class="draft-label">{draft_id}:</span>')
                html_parts.append(f'<span class="token-sequence">')
                
                # Add each token with confidence coloring
                for i, token in enumerate(tokens):
                    confidence_level = confidence_levels[i] if i < len(confidence_levels) else 'low'
                    color = self.confidence_colors.get(confidence_level, '#cccccc')
                    
                    if token == '-':
                        # Gap token
                        html_parts.append(
                            f'<span class="token gap-token" style="background-color: #f8f9fa; color: #6c757d;">−</span>'
                        )
                    else:
                        # Regular token
                        html_parts.append(
                            f'<span class="token" style="background-color: {color}; color: white;" '
                            f'title="Confidence: {confidence_level}">{token}</span>'
                        )
                
                html_parts.append('</span>')
                html_parts.append('</div>')
            
            html_parts.append('</div>')
        
        html_parts.append('</div>')
        return '\n'.join(html_parts)
    
    def _generate_heatmap_html(self, heatmap_data: Dict[str, Any]) -> str:
        """Generate HTML with embedded confidence heatmaps"""
        if not VISUALIZATION_AVAILABLE:
            return '<div class="heatmap-section"><p>⚠️ Visualization libraries not available</p></div>'
        
        html_parts = ['<div class="heatmap-section">']
        html_parts.append('<h2>🔥 Confidence Heatmap</h2>')
        
        for block_id, block_heatmap in heatmap_data.items():
            try:
                # Generate heatmap image
                heatmap_base64 = self._create_confidence_heatmap(block_heatmap)
                
                html_parts.append(f'<div class="block-heatmap" id="heatmap-{block_id}">')
                html_parts.append(f'<h3>Block: {block_id}</h3>')
                
                # Add statistics
                avg_conf = block_heatmap.get('average_confidence', 0)
                high_count = block_heatmap.get('high_confidence_positions', 0)
                medium_count = block_heatmap.get('medium_confidence_positions', 0)
                low_count = block_heatmap.get('low_confidence_positions', 0)
                
                html_parts.append('<div class="heatmap-stats">')
                html_parts.append(f'<p><strong>Average Confidence:</strong> {avg_conf:.3f}</p>')
                html_parts.append(f'<p><strong>High:</strong> {high_count} | ')
                html_parts.append(f'<strong>Medium:</strong> {medium_count} | ')
                html_parts.append(f'<strong>Low:</strong> {low_count}</p>')
                html_parts.append('</div>')
                
                # Embed heatmap image
                if heatmap_base64:
                    html_parts.append(
                        f'<img src="data:image/png;base64,{heatmap_base64}" '
                        f'alt="Confidence heatmap for {block_id}" class="heatmap-image">'
                    )
                else:
                    html_parts.append('<p>⚠️ Could not generate heatmap</p>')
                
                html_parts.append('</div>')
                
            except Exception as e:
                logger.warning(f"Failed to generate heatmap for block {block_id}: {e}")
                html_parts.append(f'<p>⚠️ Error generating heatmap for {block_id}</p>')
        
        html_parts.append('</div>')
        return '\n'.join(html_parts)
    
    def _create_confidence_heatmap(self, block_heatmap: Dict[str, Any]) -> Optional[str]:
        """Create a confidence heatmap and return as base64 encoded PNG"""
        try:
            matrix = block_heatmap.get('matrix', [])
            if not matrix or not matrix[0]:
                return None
            
            # Create matplotlib figure
            fig, ax = plt.subplots(figsize=(12, 2))
            
            # Create heatmap with seaborn
            sns.heatmap(
                matrix,
                annot=False,
                cmap='RdYlGn',  # Red-Yellow-Green colormap
                vmin=0,
                vmax=1,
                cbar_kws={'label': 'Confidence Score'},
                ax=ax,
                xticklabels=False,
                yticklabels=block_heatmap.get('row_labels', ['Consensus'])
            )
            
            ax.set_title('Token-level Confidence Scores')
            ax.set_xlabel('Token Position')
            
            # Save to base64
            buffer = io.BytesIO()
            plt.savefig(buffer, format='png', bbox_inches='tight', dpi=100)
            buffer.seek(0)
            
            image_base64 = base64.b64encode(buffer.getvalue()).decode('utf-8')
            
            plt.close(fig)
            return image_base64
            
        except Exception as e:
            logger.warning(f"Failed to create heatmap: {e}")
            return None
    
    def _generate_suggestion_panel_html(self, formatted_differences: List[Dict[str, Any]]) -> str:
        """Generate HTML for suggestion panel with differences"""
        html_parts = ['<div class="suggestion-panel-section">']
        html_parts.append('<h2>🔍 Differences & Suggestions</h2>')
        
        if not formatted_differences:
            html_parts.append('<p>✅ No differences found - all drafts are in perfect agreement!</p>')
        else:
            html_parts.append(f'<p>Found <strong>{len(formatted_differences)}</strong> differences across all blocks:</p>')
            
            # Group differences by block
            differences_by_block = {}
            for diff in formatted_differences:
                block_id = diff['block_id']
                if block_id not in differences_by_block:
                    differences_by_block[block_id] = []
                differences_by_block[block_id].append(diff)
            
            # Generate suggestions for each block
            for block_id, block_differences in differences_by_block.items():
                html_parts.append(f'<div class="block-differences" id="differences-{block_id}">')
                html_parts.append(f'<h3>Block: {block_id}</h3>')
                html_parts.append('<table class="differences-table">')
                html_parts.append('<thead>')
                html_parts.append('<tr>')
                html_parts.append('<th>Position</th>')
                html_parts.append('<th>Reference (Draft 1)</th>')
                html_parts.append('<th>Alternatives</th>')
                html_parts.append('<th>Confidence</th>')
                html_parts.append('</tr>')
                html_parts.append('</thead>')
                html_parts.append('<tbody>')
                
                for diff in block_differences:
                    position = diff['position']
                    reference_token = diff['reference_token']
                    alternatives = diff['alternatives']
                    confidence = diff['confidence']
                    
                    html_parts.append('<tr>')
                    html_parts.append(f'<td>{position}</td>')
                    html_parts.append(f'<td class="reference-token">{reference_token}</td>')
                    
                    # Format alternatives
                    alt_html = []
                    for alt in alternatives:
                        alt_html.append(f'{alt["draft_id"]}: <strong>{alt["token"]}</strong>')
                    html_parts.append(f'<td class="alternatives">{" | ".join(alt_html)}</td>')
                    
                    # Confidence with color coding
                    if confidence >= 0.8:
                        conf_class = 'high-confidence'
                    elif confidence >= 0.4:
                        conf_class = 'medium-confidence'
                    else:
                        conf_class = 'low-confidence'
                    
                    html_parts.append(f'<td class="confidence {conf_class}">{confidence:.3f}</td>')
                    html_parts.append('</tr>')
                
                html_parts.append('</tbody>')
                html_parts.append('</table>')
                html_parts.append('</div>')
        
        html_parts.append('</div>')
        return '\n'.join(html_parts)
    
    def _generate_summary_html(self, alignment_results: Dict[str, Any],
                              confidence_results: Dict[str, Any],
                              difference_results: Dict[str, Any]) -> str:
        """Generate HTML summary section"""
        html_parts = ['<div class="summary-section">']
        html_parts.append('<h2>📊 Alignment Summary</h2>')
        
        # Overall statistics
        overall_stats = confidence_results.get('overall_stats', {})
        
        html_parts.append('<div class="summary-grid">')
        
        # Basic stats
        html_parts.append('<div class="summary-card">')
        html_parts.append('<h4>📋 Basic Statistics</h4>')
        html_parts.append(f'<p><strong>Total Blocks:</strong> {len(alignment_results.get("blocks", {}))}</p>')
        html_parts.append(f'<p><strong>Total Positions:</strong> {overall_stats.get("total_positions", 0)}</p>')
        html_parts.append(f'<p><strong>Total Differences:</strong> {overall_stats.get("total_differences", 0)}</p>')
        html_parts.append(f'<p><strong>Average Confidence:</strong> {overall_stats.get("average_confidence", 0):.3f}</p>')
        html_parts.append('</div>')
        
        # Confidence distribution
        html_parts.append('<div class="summary-card">')
        html_parts.append('<h4>🎯 Confidence Distribution</h4>')
        total_pos = overall_stats.get("total_positions", 1)
        high_pct = (overall_stats.get("high_confidence_positions", 0) / total_pos) * 100
        medium_pct = (overall_stats.get("medium_confidence_positions", 0) / total_pos) * 100
        low_pct = (overall_stats.get("low_confidence_positions", 0) / total_pos) * 100
        
        html_parts.append(f'<p><span style="color: {self.confidence_colors["high"]}">●</span> ')
        html_parts.append(f'<strong>High:</strong> {overall_stats.get("high_confidence_positions", 0)} ({high_pct:.1f}%)</p>')
        html_parts.append(f'<p><span style="color: {self.confidence_colors["medium"]}">●</span> ')
        html_parts.append(f'<strong>Medium:</strong> {overall_stats.get("medium_confidence_positions", 0)} ({medium_pct:.1f}%)</p>')
        html_parts.append(f'<p><span style="color: {self.confidence_colors["low"]}">●</span> ')
        html_parts.append(f'<strong>Low:</strong> {overall_stats.get("low_confidence_positions", 0)} ({low_pct:.1f}%)</p>')
        html_parts.append('</div>')
        
        # Difference categories
        html_parts.append('<div class="summary-card">')
        html_parts.append('<h4>🔍 Difference Categories</h4>')
        category_counts = difference_results.get('category_counts', {})
        
        html_parts.append(f'<p><strong>Coordinates:</strong> {category_counts.get("coordinate_differences", 0)}</p>')
        html_parts.append(f'<p><strong>Words:</strong> {category_counts.get("word_differences", 0)}</p>')
        html_parts.append(f'<p><strong>Punctuation:</strong> {category_counts.get("punctuation_differences", 0)}</p>')
        html_parts.append(f'<p><strong>Other:</strong> {category_counts.get("other_differences", 0)}</p>')
        html_parts.append('</div>')
        
        html_parts.append('</div>')
        html_parts.append('</div>')
        
        return '\n'.join(html_parts)
    
    def _create_complete_html_page(self, aligned_text_html: str, heatmap_html: str,
                                  suggestion_panel_html: str, summary_html: str) -> str:
        """Create complete HTML page with all components"""
        return f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>BioPython Alignment Results</title>
    <style>
        {self._get_css_styles()}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>🧬 BioPython Legal Document Alignment Results</h1>
            <p class="subtitle">Consistency-based multiple sequence alignment with confidence analysis</p>
        </header>
        
        <nav class="navigation">
            <a href="#summary">📊 Summary</a>
            <a href="#aligned-text">📝 Aligned Text</a>
            <a href="#heatmap">🔥 Heatmap</a>
            <a href="#differences">🔍 Differences</a>
        </nav>
        
        <main>
            <section id="summary">
                {summary_html}
            </section>
            
            <section id="aligned-text">
                {aligned_text_html}
            </section>
            
            <section id="heatmap">
                {heatmap_html}
            </section>
            
            <section id="differences">
                {suggestion_panel_html}
            </section>
        </main>
        
        <footer>
            <p>Generated by BioPython Alignment Engine | Plattera Legal Document Processing</p>
        </footer>
    </div>
</body>
</html>
"""
    
    def _get_css_styles(self) -> str:
        """Get CSS styles for the HTML visualization"""
        return """
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            margin: 0;
            padding: 0;
            background-color: #f8f9fa;
            line-height: 1.6;
        }
        
        .container {
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
        }
        
        header {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 30px;
            border-radius: 10px;
            text-align: center;
            margin-bottom: 30px;
        }
        
        header h1 {
            margin: 0;
            font-size: 2.5em;
        }
        
        .subtitle {
            margin: 10px 0 0 0;
            opacity: 0.9;
            font-size: 1.1em;
        }
        
        .navigation {
            background: white;
            padding: 15px;
            border-radius: 8px;
            margin-bottom: 30px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            text-align: center;
        }
        
        .navigation a {
            display: inline-block;
            padding: 10px 20px;
            margin: 0 10px;
            background: #6c757d;
            color: white;
            text-decoration: none;
            border-radius: 5px;
            transition: background-color 0.3s;
        }
        
        .navigation a:hover {
            background: #495057;
        }
        
        section {
            background: white;
            margin-bottom: 30px;
            padding: 30px;
            border-radius: 10px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }
        
        h2 {
            color: #495057;
            border-bottom: 3px solid #dee2e6;
            padding-bottom: 10px;
            margin-bottom: 25px;
        }
        
        h3 {
            color: #6c757d;
            margin-top: 25px;
        }
        
        .summary-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            margin-top: 20px;
        }
        
        .summary-card {
            background: #f8f9fa;
            padding: 20px;
            border-radius: 8px;
            border-left: 4px solid #007bff;
        }
        
        .summary-card h4 {
            margin-top: 0;
            color: #495057;
        }
        
        .block-section {
            margin-bottom: 30px;
            padding: 20px;
            background: #f8f9fa;
            border-radius: 8px;
            border-left: 4px solid #28a745;
        }
        
        .draft-row {
            margin-bottom: 15px;
            display: flex;
            align-items: center;
        }
        
        .draft-label {
            font-weight: bold;
            min-width: 100px;
            color: #495057;
        }
        
        .token-sequence {
            display: flex;
            flex-wrap: wrap;
            gap: 2px;
        }
        
        .token {
            padding: 2px 6px;
            border-radius: 3px;
            font-family: 'Courier New', monospace;
            font-size: 0.9em;
            white-space: nowrap;
        }
        
        .gap-token {
            font-style: italic;
        }
        
        .heatmap-image {
            max-width: 100%;
            height: auto;
            border: 1px solid #dee2e6;
            border-radius: 5px;
        }
        
        .heatmap-stats {
            background: #e9ecef;
            padding: 15px;
            border-radius: 5px;
            margin-bottom: 15px;
        }
        
        .differences-table {
            width: 100%;
            border-collapse: collapse;
            margin-top: 15px;
        }
        
        .differences-table th,
        .differences-table td {
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid #dee2e6;
        }
        
        .differences-table th {
            background: #f8f9fa;
            font-weight: bold;
            color: #495057;
        }
        
        .reference-token {
            font-family: 'Courier New', monospace;
            background: #e9ecef;
            padding: 4px 8px;
            border-radius: 3px;
        }
        
        .alternatives {
            font-family: 'Courier New', monospace;
        }
        
        .high-confidence {
            background: #d4edda;
            color: #155724;
            font-weight: bold;
        }
        
        .medium-confidence {
            background: #fff3cd;
            color: #856404;
            font-weight: bold;
        }
        
        .low-confidence {
            background: #f8d7da;
            color: #721c24;
            font-weight: bold;
        }
        
        footer {
            text-align: center;
            padding: 20px;
            color: #6c757d;
            border-top: 1px solid #dee2e6;
            margin-top: 40px;
        }
        
        @media (max-width: 768px) {
            .container {
                padding: 10px;
            }
            
            .token-sequence {
                font-size: 0.8em;
            }
            
            .differences-table {
                font-size: 0.9em;
            }
        }
        """
    
    def _generate_error_html(self, error_message: str) -> str:
        """Generate error HTML page"""
        return f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Alignment Error</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 50px; background: #f8f9fa; }}
        .error-container {{ background: white; padding: 30px; border-radius: 10px; text-align: center; }}
        .error-title {{ color: #dc3545; font-size: 2em; margin-bottom: 20px; }}
        .error-message {{ color: #6c757d; font-size: 1.1em; }}
    </style>
</head>
<body>
    <div class="error-container">
        <h1 class="error-title">❌ Visualization Error</h1>
        <p class="error-message">An error occurred while generating the alignment visualization:</p>
        <p><code>{error_message}</code></p>
        <p>Please check the alignment results and try again.</p>
    </div>
</body>
</html>
""" 