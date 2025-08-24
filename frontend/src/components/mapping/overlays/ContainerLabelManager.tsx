/**
 * Container Label Manager
 * Dedicated module for PLSS labeling logic specific to container overlays
 * Handles feature-to-label mapping, dynamic label positioning, and professional styling
 */

import React, { useCallback, useRef } from 'react';
import { ContainerLayer } from '../../../services/plss/containerApi';

export interface ContainerLabelFeature {
  type: 'Feature';
  geometry: {
    type: 'Point';
    coordinates: [number, number];
  };
  properties: {
    label: string;
    type: string;
    style: string;
    angle: number;
    featureId: string;
  };
}

export interface ContainerLabelOptions {
  showGridLabels: boolean;
  showTownshipLabels: boolean;
  showRangeLabels: boolean;
  showSectionLabels: boolean;
  showQuarterSectionLabels: boolean;
  showSubdivisionLabels: boolean;
}

interface ContainerLabelManagerProps {
  map: any;
  layerId: string;
  features: any[];
  layerType: ContainerLayer;
  color: string;
  options: ContainerLabelOptions;
  onLabelsCreated?: (labelFeatures: ContainerLabelFeature[]) => void;
}

export const ContainerLabelManager: React.FC<ContainerLabelManagerProps> = ({
  map,
  layerId,
  features,
  layerType,
  color,
  options,
  onLabelsCreated,
}) => {
  const labelLayerId = `${layerId}-labels`;
  const labelElements = useRef<HTMLDivElement[]>([]);
  const eventHandlers = useRef<Array<() => void>>([]);
  const renderCount = useRef<number>(0);
  const lastRenderTime = useRef<number>(0);

  // 🧹 CLEANUP FUNCTION
  const cleanupLabels = useCallback(() => {
    console.log(`🧹 Cleaning up labels for ${labelLayerId}`);
    
    // Remove HTML elements
    labelElements.current.forEach(el => {
      try {
        if (el && el.parentNode) {
          el.parentNode.removeChild(el);
        }
      } catch (error) {
        console.warn('Error removing label element:', error);
      }
    });
    labelElements.current = [];
    
    // Remove event handlers
    eventHandlers.current.forEach(handler => {
      try {
        handler();
      } catch (error) {
        console.warn('Error removing event handler:', error);
      }
    });
    eventHandlers.current = [];
    
    // Remove map sources/layers
    try {
      if (map.getLayer(labelLayerId)) {
        map.removeLayer(labelLayerId);
      }
      if (map.getSource(labelLayerId)) {
        map.removeSource(labelLayerId);
      }
    } catch (error) {
      console.warn('Error removing map layers:', error);
    }
  }, [map, labelLayerId]);

  // 🎯 FEATURE ANALYSIS HELPERS
  const analyzeFeatureGeometry = useCallback((feature: any) => {
    const geometry = feature.geometry;
    if (!geometry || !geometry.coordinates || !Array.isArray(geometry.coordinates[0])) {
      console.warn('Invalid geometry for feature:', feature);
      return null;
    }
    
    const ring = geometry.coordinates[0];
    if (ring.length < 3) {
      console.warn('Ring too small for analysis:', ring.length);
      return null;
    }
    
    // Calculate bounding box
    let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
    ring.forEach(([x, y]: number[]) => {
      minX = Math.min(minX, x);
      maxX = Math.max(maxX, x);
      minY = Math.min(minY, y);
      maxY = Math.max(maxY, y);
    });
    
    return {
      ring,
      bounds: { minX, maxX, minY, maxY },
      width: maxX - minX,
      height: maxY - minY,
      center: [(minX + maxX) / 2, (minY + maxY) / 2] as [number, number]
    };
  }, []);

  // 🎯 ROAD-STYLE LINE LABELING HELPERS
  const findLinePoints = useCallback((analysis: any, numPoints: number = 3) => {
    const { ring } = analysis;
    if (!ring || ring.length < 2) return [];
    
    const points: Array<{ coordinates: [number, number]; angle: number }> = [];
    
    // Calculate total length of the line
    let totalLength = 0;
    for (let i = 1; i < ring.length; i++) {
      const [x1, y1] = ring[i - 1];
      const [x2, y2] = ring[i];
      totalLength += Math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2);
    }
    
    // Find points at regular intervals along the line
    const segmentLength = totalLength / (numPoints + 1);
    let currentLength = segmentLength;
    let segmentIndex = 0;
    let segmentStart = 0;
    
    for (let pointIndex = 0; pointIndex < numPoints; pointIndex++) {
      // Find the segment where this point should be
      while (segmentIndex < ring.length - 1) {
        const [x1, y1] = ring[segmentIndex];
        const [x2, y2] = ring[segmentIndex + 1];
        const segmentLen = Math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2);
        
        if (currentLength <= segmentLen) {
          // Calculate position within this segment
          const ratio = currentLength / segmentLen;
          const x = x1 + (x2 - x1) * ratio;
          const y = y1 + (y2 - y1) * ratio;
          
          // Calculate angle of this segment
          const angle = Math.atan2(y2 - y1, x2 - x1) * (180 / Math.PI);
          
          points.push({
            coordinates: [x, y] as [number, number],
            angle: angle
          });
          
          currentLength += segmentLength;
          break;
        } else {
          currentLength -= segmentLen;
          segmentIndex++;
        }
      }
    }
    
    return points;
  }, []);

  const findHorizontalLinePoints = useCallback((analysis: any, numPoints: number = 2) => {
    const { ring, bounds } = analysis;
    if (!ring || ring.length < 2) return [];
    
    const points: Array<{ coordinates: [number, number]; angle: number }> = [];
    
    // Get map bounds to understand the viewport and container area
    let mapBounds;
    try {
      const mapSize = map.getSize ? map.getSize() : map.getContainer().getBoundingClientRect();
      const width = mapSize.width || mapSize.right - mapSize.left;
      const height = mapSize.height || mapSize.bottom - mapSize.top;
      
      const topLeft = map.unproject([0, 0]);
      const bottomRight = map.unproject([width, height]);
      
      mapBounds = {
        minX: topLeft.lng,
        maxX: bottomRight.lng,
        minY: bottomRight.lat,
        maxY: topLeft.lat
      };
    } catch (error) {
      console.warn('Could not get map bounds, using feature bounds:', error);
      mapBounds = bounds;
    }
    
    // Find points within the visible map area, prioritizing the container area
    const visibleWidth = Math.min(bounds.maxX, mapBounds.maxX) - Math.max(bounds.minX, mapBounds.minX);
    const step = visibleWidth / (numPoints + 1);
    
    for (let i = 1; i <= numPoints; i++) {
      // Calculate x position within the visible area
      const x = Math.max(bounds.minX, mapBounds.minX) + step * i;
      
      // Find the y-coordinate by interpolating along the line
      let y = bounds.minY;
      for (let j = 0; j < ring.length - 1; j++) {
        const [x1, y1] = ring[j];
        const [x2, y2] = ring[j + 1];
        
        if ((x1 <= x && x <= x2) || (x2 <= x && x <= x1)) {
          const ratio = (x - x1) / (x2 - x1);
          y = y1 + (y2 - y1) * ratio;
          break;
        }
      }
      
      // Only add point if it's within the visible map area
      if (x >= mapBounds.minX && x <= mapBounds.maxX && y >= mapBounds.minY && y <= mapBounds.maxY) {
        points.push({
          coordinates: [x, y] as [number, number],
          angle: 0
        });
      }
    }
    
    // If no points found in visible area, add one point in the center of the visible area
    if (points.length === 0) {
      const centerX = (mapBounds.minX + mapBounds.maxX) / 2;
      const centerY = (mapBounds.minY + mapBounds.maxY) / 2;
      
      // Find the y-coordinate on the line for this x
      let y = bounds.minY;
      for (let j = 0; j < ring.length - 1; j++) {
        const [x1, y1] = ring[j];
        const [x2, y2] = ring[j + 1];
        
        if ((x1 <= centerX && centerX <= x2) || (x2 <= centerX && centerX <= x1)) {
          const ratio = (centerX - x1) / (x2 - x1);
          y = y1 + (y2 - y1) * ratio;
          break;
        }
      }
      
      points.push({
        coordinates: [centerX, y] as [number, number],
        angle: 0
      });
    }
    
    return points;
  }, [map]);

  const findVerticalLinePoints = useCallback((analysis: any, numPoints: number = 2) => {
    const { ring, bounds } = analysis;
    if (!ring || ring.length < 2) return [];
    
    const points: Array<{ coordinates: [number, number]; angle: number }> = [];
    
    // Get map bounds to understand the viewport and container area
    let mapBounds;
    try {
      const mapSize = map.getSize ? map.getSize() : map.getContainer().getBoundingClientRect();
      const width = mapSize.width || mapSize.right - mapSize.left;
      const height = mapSize.height || mapSize.bottom - mapSize.top;
      
      const topLeft = map.unproject([0, 0]);
      const bottomRight = map.unproject([width, height]);
      
      mapBounds = {
        minX: topLeft.lng,
        maxX: bottomRight.lng,
        minY: bottomRight.lat,
        maxY: topLeft.lat
      };
    } catch (error) {
      console.warn('Could not get map bounds, using feature bounds:', error);
      mapBounds = bounds;
    }
    
    // Find points within the visible map area, prioritizing the container area
    const visibleHeight = Math.min(bounds.maxY, mapBounds.maxY) - Math.max(bounds.minY, mapBounds.minY);
    const step = visibleHeight / (numPoints + 1);
    
    for (let i = 1; i <= numPoints; i++) {
      // Calculate y position within the visible area
      const y = Math.max(bounds.minY, mapBounds.minY) + step * i;
      
      // Find the x-coordinate by interpolating along the line
      let x = bounds.minX;
      for (let j = 0; j < ring.length - 1; j++) {
        const [x1, y1] = ring[j];
        const [x2, y2] = ring[j + 1];
        
        if ((y1 <= y && y <= y2) || (y2 <= y && y <= y1)) {
          const ratio = (y - y1) / (y2 - y1);
          x = x1 + (x2 - x1) * ratio;
          break;
        }
      }
      
      // Only add point if it's within the visible map area
      if (x >= mapBounds.minX && x <= mapBounds.maxX && y >= mapBounds.minY && y <= mapBounds.maxY) {
        points.push({
          coordinates: [x, y] as [number, number],
          angle: 90
        });
      }
    }
    
    // If no points found in visible area, add one point in the center of the visible area
    if (points.length === 0) {
      const centerX = (mapBounds.minX + mapBounds.maxX) / 2;
      const centerY = (mapBounds.minY + mapBounds.maxY) / 2;
      
      // Find the x-coordinate on the line for this y
      let x = bounds.minX;
      for (let j = 0; j < ring.length - 1; j++) {
        const [x1, y1] = ring[j];
        const [x2, y2] = ring[j + 1];
        
        if ((y1 <= centerY && centerY <= y2) || (y2 <= centerY && centerY <= y1)) {
          const ratio = (centerY - y1) / (y2 - y1);
          x = x1 + (x2 - x1) * ratio;
          break;
        }
      }
      
      points.push({
        coordinates: [x, centerY] as [number, number],
        angle: 90
      });
    }
    
    return points;
  }, [map]);

  // 🎯 FAIL-SAFE EDGE MIDPOINTS (keep for fallback)
  const getEdgeMidpoints = useCallback((analysis: any) => {
    // Get the actual map bounds instead of hardcoded container bounds
    let mapBounds;
    try {
      // Try to get bounds from the map
      const mapCenter = map.getCenter();
      const mapZoom = map.getZoom();
      
      // Calculate approximate bounds based on center and zoom
      const latLngToPoint = (lat: number, lng: number) => {
        const point = map.project([lng, lat]);
        return point;
      };
      
      // Get corners of the map viewport
      const mapSize = map.getSize ? map.getSize() : map.getContainer().getBoundingClientRect();
      const width = mapSize.width || mapSize.right - mapSize.left;
      const height = mapSize.height || mapSize.bottom - mapSize.top;
      
      // Convert screen corners back to lat/lng
      const topLeft = map.unproject([0, 0]);
      const bottomRight = map.unproject([width, height]);
      
      mapBounds = {
        minX: topLeft.lng,
        maxX: bottomRight.lng,
        minY: bottomRight.lat,
        maxY: topLeft.lat
      };
      
      console.log(`🗺️ Map bounds calculated:`, mapBounds);
    } catch (error) {
      console.warn('Could not get map bounds, using fallback:', error);
      // Fallback to container bounds
      mapBounds = {
        minX: -107.52,
        maxX: -107.48,
        minY: 41.48,
        maxY: 41.52
      };
    }
    
    // Calculate midpoints within the visible map area
    const centerX = (mapBounds.minX + mapBounds.maxX) / 2;
    const centerY = (mapBounds.minY + mapBounds.maxY) / 2;
    
    return {
      township: {
        bottom: [centerX, mapBounds.minY] as [number, number],
        top: [centerX, mapBounds.maxY] as [number, number],
      },
      range: {
        left: [mapBounds.minX, centerY] as [number, number],
        right: [mapBounds.maxX, centerY] as [number, number],
      },
    };
  }, [map]);

  // 🏷️ LABEL GENERATION BY FEATURE TYPE
  const generateGridLabels = useCallback((feature: any): ContainerLabelFeature[] => {
    const props = feature.properties;
    const analysis = analyzeFeatureGeometry(feature);
    if (!analysis) return [];
    
    const townshipStr = `T${props.township_number?.toString().padStart(2, '0') || '??'}${props.township_direction || 'N'}`;
    const rangeStr = `R${props.range_number?.toString().padStart(2, '0') || '??'}${props.range_direction || 'W'}`;
    const gridLabel = `${townshipStr} ${rangeStr}`;
    
    console.log(`🏷️ Generated grid label: ${gridLabel} for feature ${props.feature_type || 'unknown'}`);
    
    return [{
      type: 'Feature',
      geometry: {
        type: 'Point',
        coordinates: analysis.center as [number, number]
      },
      properties: {
        label: gridLabel,
        type: 'grid-primary',
        style: 'primary',
        angle: 0,
        featureId: `${layerType}-${props.township_number}-${props.range_number}`
      }
    }];
  }, [analyzeFeatureGeometry, layerType]);

  const generateTownshipLabels = useCallback((feature: any): ContainerLabelFeature[] => {
    const props = feature.properties;
    const analysis = analyzeFeatureGeometry(feature);
    if (!analysis) return [];

    const townshipNum = parseInt(props.township_number);
    const townshipDir = (props.township_direction || 'N').toUpperCase();

    console.log(`🏷️ Township labeling (road-style) for T${townshipNum}${townshipDir}`, analysis.bounds);

         // Find points along the horizontal township lines
     const linePoints = findHorizontalLinePoints(analysis, 1); // 1 label per line to avoid confusion
    console.log(`📍 Township line points: ${linePoints.length} points found`);

    // This feature represents Township T N boundary line
    // The line itself should be labeled as "Township T N"
    const labelText = `Township ${townshipNum} ${townshipDir}`;

    const labels: ContainerLabelFeature[] = [];

    // Create labels for each point along the line
    linePoints.forEach((point, index) => {
      labels.push({
        type: 'Feature',
        geometry: { type: 'Point', coordinates: point.coordinates },
        properties: {
          label: labelText,
          type: 'township-boundary',
          style: 'boundary',
          angle: point.angle,
          featureId: `${layerType}-${townshipNum}-${index}`,
        },
      });
    });

    console.log(`🏷️ Generated ${labels.length} township labels for Township ${townshipNum} ${townshipDir}`);
    return labels;
  }, [analyzeFeatureGeometry, findHorizontalLinePoints, layerType]);

  const generateRangeLabels = useCallback((feature: any): ContainerLabelFeature[] => {
    const props = feature.properties;
    const analysis = analyzeFeatureGeometry(feature);
    if (!analysis) return [];

    const rangeNum = parseInt(props.range_number);
    const rangeDir = (props.range_direction || 'W').toUpperCase();

    console.log(`🏷️ Range labeling (road-style) for R${rangeNum}${rangeDir}`, analysis.bounds);

         // Find points along the vertical range lines
     const linePoints = findVerticalLinePoints(analysis, 1); // 1 label per line to avoid confusion
    console.log(`📍 Range line points: ${linePoints.length} points found`);

    // This feature represents Range R W boundary line
    // The line itself should be labeled as "Range R W"
    const labelText = `Range ${rangeNum} ${rangeDir}`;

    const labels: ContainerLabelFeature[] = [];

    // Create labels for each point along the line
    linePoints.forEach((point, index) => {
      labels.push({
        type: 'Feature',
        geometry: { type: 'Point', coordinates: point.coordinates },
        properties: {
          label: labelText,
          type: 'range-boundary',
          style: 'boundary',
          angle: point.angle,
          featureId: `${layerType}-${rangeNum}-${index}`,
        },
      });
    });

    console.log(`🏷️ Generated ${labels.length} range labels for Range ${rangeNum} ${rangeDir}`);
    return labels;
  }, [analyzeFeatureGeometry, findVerticalLinePoints, layerType]);

  const generateSectionLabels = useCallback((feature: any): ContainerLabelFeature[] => {
    const props = feature.properties;
    const analysis = analyzeFeatureGeometry(feature);
    if (!analysis) return [];
    
    // Extract section number from multiple possible sources
    let sectionNumber = props.section_number || props.SECNUM || props.section || props.SEC;
    
    if (!sectionNumber && props.label) {
      const sectionMatch = props.label.match(/(?:Section\s+|Sec\s+|S)(\d+)/i);
      if (sectionMatch) {
        sectionNumber = parseInt(sectionMatch[1]);
      }
    }
    
    if (!sectionNumber && props.display_label) {
      const sectionMatch = props.display_label.match(/(?:Section\s+|Sec\s+|S)(\d+)/i);
      if (sectionMatch) {
        sectionNumber = parseInt(sectionMatch[1]);
      }
    }
    
    const sectionLabel = sectionNumber ? `Section ${sectionNumber}` : 'Section';
    
    console.log(`🏷️ Generated section label: ${sectionLabel} for feature ${props.feature_type || 'unknown'}`);
    
    return [{
      type: 'Feature',
      geometry: {
        type: 'Point',
        coordinates: analysis.center as [number, number]
      },
      properties: {
        label: sectionLabel,
        type: 'section-primary',
        style: 'section',
        angle: 0,
        featureId: `${layerType}-${sectionNumber || 'unknown'}`
      }
    }];
  }, [analyzeFeatureGeometry, layerType]);

  const generateQuarterSectionLabels = useCallback((feature: any): ContainerLabelFeature[] => {
    const props = feature.properties;
    const analysis = analyzeFeatureGeometry(feature);
    if (!analysis) return [];
    
    let sectionNumber = props.section_number || props.SECNUM || props.section;
    let quarterInfo = props.quarter_sections || props.label || props.display_label;
    
    // Parse quarter section designation
    let quarterAbbrev = '';
    if (quarterInfo) {
      if (quarterInfo.toLowerCase().includes('northwest')) quarterAbbrev = 'NW¼';
      else if (quarterInfo.toLowerCase().includes('northeast')) quarterAbbrev = 'NE¼';
      else if (quarterInfo.toLowerCase().includes('southwest')) quarterAbbrev = 'SW¼';
      else if (quarterInfo.toLowerCase().includes('southeast')) quarterAbbrev = 'SE¼';
      else quarterAbbrev = 'Q¼';
    }
    
    const quarterLabel = `${quarterAbbrev} Sec ${sectionNumber || '?'}`;
    
    console.log(`🏷️ Generated quarter section label: ${quarterLabel} for feature ${props.feature_type || 'unknown'}`);
    
    return [{
      type: 'Feature',
      geometry: {
        type: 'Point',
        coordinates: analysis.center as [number, number]
      },
      properties: {
        label: quarterLabel,
        type: 'quarter-section-primary',
        style: 'quarter-section',
        angle: 0,
        featureId: `${layerType}-${sectionNumber}-${quarterAbbrev}`
      }
    }];
  }, [analyzeFeatureGeometry, layerType]);

  const generateSubdivisionLabels = useCallback((feature: any): ContainerLabelFeature[] => {
    const props = feature.properties;
    const analysis = analyzeFeatureGeometry(feature);
    if (!analysis) return [];
    
    let subdivisionLabel = props.label || props.display_label || 'Subdivision';
    
    console.log(`🏷️ Generated subdivision label: ${subdivisionLabel} for feature ${props.feature_type || 'unknown'}`);
    
    return [{
      type: 'Feature',
      geometry: {
        type: 'Point',
        coordinates: analysis.center as [number, number]
      },
      properties: {
        label: subdivisionLabel,
        type: 'subdivision-primary',
        style: 'subdivision',
        angle: 0,
        featureId: `${layerType}-subdivision`
      }
    }];
  }, [analyzeFeatureGeometry, layerType]);

  // 🎨 LABEL STYLING
  const getLabelStyle = useCallback((style: string, zoom: number, color: string, angle: number): string => {
    const baseStyle = `
      position: absolute;
      pointer-events: none;
      white-space: nowrap;
      font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
      font-weight: 600;
      text-align: center;
      border-radius: 1px;
      box-shadow: 0 1px 2px rgba(0,0,0,0.15);
      transform: translate(-50%, -50%) rotate(${angle}deg);
      z-index: 1000;
      background: ${color};
      color: white;
      padding: 1px 3px;
      text-shadow: 1px 1px 1px rgba(0,0,0,0.3);
    `;
    
    // Adjust font size based on zoom and style
    let fontSize: number;
    switch (style) {
      case 'primary':
        fontSize = Math.max(13, Math.min(18, zoom * 1.6));
        break;
      case 'boundary':
        fontSize = Math.max(12, Math.min(16, zoom * 1.4));
        break;
      case 'section':
        fontSize = Math.max(13, Math.min(18, zoom * 1.6));
        break;
      case 'quarter-section':
        fontSize = Math.max(11, Math.min(15, zoom * 1.3));
        break;
      case 'subdivision':
        fontSize = Math.max(10, Math.min(14, zoom * 1.2));
        break;
      default:
        fontSize = Math.max(11, Math.min(15, zoom * 1.3));
    }
    
    return baseStyle + `font-size: ${fontSize}px;`;
  }, []);

  // 🎯 PANEL OVERLAP DETECTION
  const isPanelOverlap = useCallback((point: { x: number; y: number }): boolean => {
    if (!(window as any)._cachedSidePanel) {
      (window as any)._cachedSidePanel = document.querySelector('.map-side-panel');
    }
    
    const sidePanel = (window as any)._cachedSidePanel;
    if (!sidePanel) return false;
    
    const panelRect = sidePanel.getBoundingClientRect();
    const buffer = 20;
    
    return point.x >= (panelRect.left - buffer) && 
           point.x <= (panelRect.right + buffer) &&
           point.y >= (panelRect.top - buffer) && 
           point.y <= (panelRect.bottom + buffer);
  }, []);

  // 🏗️ MAIN LABEL GENERATION
  const generateLabels = useCallback((): ContainerLabelFeature[] => {
    console.log(`🏷️ Generating labels for ${layerType} layer with ${features.length} features`);
    
    const allLabels: ContainerLabelFeature[] = [];
    
    // Calculate township bounds from all features to prioritize township container area
    let townshipBounds: any = null;
    if (features.length > 0) {
      const firstFeature = features[0];
      const analysis = analyzeFeatureGeometry(firstFeature);
      if (analysis) {
        // Use the bounds of the first feature as a reference for township container area
        townshipBounds = analysis.bounds;
        console.log(`🗺️ Township bounds calculated:`, townshipBounds);
      }
    }
    
    features.forEach((feature, index) => {
      console.log(`🏷️ Processing feature ${index + 1}/${features.length}:`, feature.properties);
      
      let featureLabels: ContainerLabelFeature[] = [];
      
      switch (layerType) {
        case 'grid':
          if (options.showGridLabels) {
            featureLabels = generateGridLabels(feature);
          }
          break;
                 case 'township':
           if (options.showTownshipLabels) {
             featureLabels = generateTownshipLabels(feature);
           }
           break;
         case 'range':
           if (options.showRangeLabels) {
             featureLabels = generateRangeLabels(feature);
           }
           break;
        case 'sections':
          if (options.showSectionLabels) {
            featureLabels = generateSectionLabels(feature);
          }
          break;
        case 'quarter-sections':
          if (options.showQuarterSectionLabels) {
            featureLabels = generateQuarterSectionLabels(feature);
          }
          break;
        case 'subdivisions':
          if (options.showSubdivisionLabels) {
            featureLabels = generateSubdivisionLabels(feature);
          }
          break;
        default:
          console.warn(`Unknown layer type: ${layerType}`);
      }
      
      allLabels.push(...featureLabels);
    });
    
    console.log(`🏷️ Generated ${allLabels.length} total labels for ${layerType} layer`);
    return allLabels;
  }, [features, layerType, options, analyzeFeatureGeometry, generateGridLabels, generateTownshipLabels, generateRangeLabels, generateSectionLabels, generateQuarterSectionLabels, generateSubdivisionLabels]);

  // 🎨 RENDER LABELS
  const renderLabels = useCallback((labelFeatures: ContainerLabelFeature[]) => {
    console.log(`🎨 Rendering ${labelFeatures.length} labels for ${labelLayerId}`);
    
    if (!map) {
      console.warn('Map not available for label rendering');
      return;
    }
    
    // Clean up existing labels first
    console.log(`🧹 Cleaning up existing labels for ${labelLayerId}`);
    
    // Remove HTML elements
    labelElements.current.forEach(el => {
      try {
        if (el && el.parentNode) {
          el.parentNode.removeChild(el);
        }
      } catch (error) {
        console.warn('Error removing label element:', error);
      }
    });
    labelElements.current = [];
    
    // Remove event handlers
    eventHandlers.current.forEach(handler => {
      try {
        handler();
      } catch (error) {
        console.warn('Error removing event handler:', error);
      }
    });
    eventHandlers.current = [];
    
    // Remove map sources/layers
    try {
      if (map.getLayer(labelLayerId)) {
        map.removeLayer(labelLayerId);
      }
      if (map.getSource(labelLayerId)) {
        map.removeSource(labelLayerId);
      }
    } catch (error) {
      console.warn('Error removing map layers:', error);
    }
    
    // Add GeoJSON source for debugging
    try {
      map.addSource(labelLayerId, {
        type: 'geojson',
        data: { type: 'FeatureCollection', features: labelFeatures }
      });
    } catch (error) {
      console.warn('Could not add label source (may already exist):', error);
    }
    
    // Create HTML label elements
    labelFeatures.forEach((feature, index) => {
      const coordinates = feature.geometry.coordinates;
      const labelText = feature.properties.label;
      const style = feature.properties.style;
      const angle = feature.properties.angle || 0;
      
      // Create label element
      const el = document.createElement('div');
      el.className = `container-label-${style}`;
      el.setAttribute('data-label-layer', labelLayerId);
      el.setAttribute('data-feature-id', feature.properties.featureId);
      el.innerHTML = labelText;
      
             // Apply initial styling
       const labelStyle = getLabelStyle(style, map.getZoom(), color, angle);
       el.style.cssText = labelStyle;
      
      // Add to map container
      const mapContainer = map.getContainer();
      mapContainer.appendChild(el);
      labelElements.current.push(el);
      
      console.log(`🎯 Created label element for "${labelText}" and added to map container`);
      
                     // Position update function - simple and stable
        const updatePosition = () => {
          try {
            const point = map.project(coordinates);
            
            // Simple position update - no viewport checking, no jittery behavior
            el.style.left = point.x + 'px';
            el.style.top = point.y + 'px';
            
            // Check for panel overlap only
            const isHidden = isPanelOverlap(point);
            el.style.display = isHidden ? 'none' : 'block';
            
            // Maintain consistent styling
            el.style.background = color;
            el.style.color = 'white';
            el.style.textShadow = '1px 1px 1px rgba(0,0,0,0.3)';
          } catch (error) {
            console.warn('Error updating label position:', error);
          }
        };
      
      // Initial position
      updatePosition();
      
             // Add throttled event handlers for smoother performance
       let moveTimeout: NodeJS.Timeout | null = null;
       let zoomTimeout: NodeJS.Timeout | null = null;
       
       const onMove = () => {
         if (moveTimeout) return; // Throttle move events
         moveTimeout = setTimeout(() => {
           updatePosition();
           moveTimeout = null;
         }, 50); // 50ms throttle
       };
       
       const onZoom = () => {
         if (zoomTimeout) return; // Throttle zoom events
         zoomTimeout = setTimeout(() => {
           updatePosition();
           zoomTimeout = null;
         }, 100); // 100ms throttle for zoom
       };
      
      map.on('move', onMove);
      map.on('zoom', onZoom);
      
             // Store cleanup function
       eventHandlers.current.push(() => {
         try {
           map.off('move', onMove);
           map.off('zoom', onZoom);
           // Clear any pending timeouts
           if (moveTimeout) {
             clearTimeout(moveTimeout);
             moveTimeout = null;
           }
           if (zoomTimeout) {
             clearTimeout(zoomTimeout);
             zoomTimeout = null;
           }
         } catch (error) {
           console.warn('Error removing event handlers:', error);
         }
       });
    });
    
    console.log(`🎨 Successfully rendered ${labelFeatures.length} labels for ${labelLayerId}`);
  }, [map, labelLayerId, color, getLabelStyle, isPanelOverlap]);

  // 🔄 MAIN EFFECT - Generate and render labels
  React.useEffect(() => {
    // 🛡️ SAFETY CHECK: Prevent infinite loops
    const now = Date.now();
    renderCount.current++;
    
    // If we've rendered more than 5 times in 1 second, something is wrong
    if (renderCount.current > 5 && (now - lastRenderTime.current) < 1000) {
      console.error(`🚨 INFINITE LOOP DETECTED: ${renderCount.current} renders in ${now - lastRenderTime.current}ms for ${layerType}`);
      return;
    }
    
    lastRenderTime.current = now;
    console.log(`🔄 ContainerLabelManager effect triggered for ${layerType} (render #${renderCount.current})`);
    
    if (!map || !features || features.length === 0) {
      console.log('No map or features available, skipping label generation');
      return;
    }
    
    // Generate labels
    const labelFeatures = generateLabels();
    
    if (labelFeatures.length === 0) {
      console.log('No labels generated, skipping render');
      return;
    }
    
    // Render labels
    renderLabels(labelFeatures);
    
    // Notify parent
    onLabelsCreated?.(labelFeatures);
    
    // Cleanup on unmount
    return () => {
      console.log(`🧹 ContainerLabelManager cleanup for ${layerType}`);
      
      // Reset render counter
      renderCount.current = 0;
      lastRenderTime.current = 0;
      
      // Inline cleanup to avoid dependency issues
      labelElements.current.forEach(el => {
        try {
          if (el && el.parentNode) {
            el.parentNode.removeChild(el);
          }
        } catch (error) {
          console.warn('Error removing label element:', error);
        }
      });
      labelElements.current = [];
      
      eventHandlers.current.forEach(handler => {
        try {
          handler();
        } catch (error) {
          console.warn('Error removing event handler:', error);
        }
      });
      eventHandlers.current = [];
      
      try {
        if (map.getLayer(labelLayerId)) {
          map.removeLayer(labelLayerId);
        }
        if (map.getSource(labelLayerId)) {
          map.removeSource(labelLayerId);
        }
      } catch (error) {
        console.warn('Error removing map layers:', error);
      }
    };
  }, [map, features, layerType, color, options, generateLabels, renderLabels, onLabelsCreated, labelLayerId]);

  // Don't render anything - this is a logic-only component
  return null;
};
