/**
 * Measurement Overlay
 * Handles rendering measurement lines and labels on the map
 */

import React, { useEffect, useCallback } from 'react';
import { useMapContext } from '../core/MapContext';
import { Measurement } from '../../../utils/measurementUtils';
import type maplibregl from 'maplibre-gl';

interface MeasurementOverlayProps {
  measurements: Measurement[];
  showCoordinates: boolean;
  onMeasurementLoad?: (measurement: Measurement) => void;
  onMeasurementUnload?: (measurement: Measurement) => void;
}

export const MeasurementOverlay: React.FC<MeasurementOverlayProps> = ({
  measurements,
  showCoordinates,
  onMeasurementLoad,
  onMeasurementUnload,
}) => {
  const { map, isLoaded } = useMapContext();

  // Draw a single measurement on the map
  const drawMeasurement = useCallback((measurement: Measurement) => {
    if (!map || measurement.points.length < 2) return;

    const lineId = `measurement-line-${measurement.id}`;
    const labelId = `measurement-label-${measurement.id}`;
    const startPointId = `measurement-start-${measurement.id}`;
    const endPointId = `measurement-end-${measurement.id}`;
    const startPointSourceId = `${startPointId}-source`;
    const endPointSourceId = `${endPointId}-source`;

    // Remove existing layers and sources safely
    [lineId, labelId, startPointId, endPointId, startPointSourceId, endPointSourceId].forEach(id => {
      try {
        if (map.getLayer(id)) {
          map.removeLayer(id);
        }
        if (map.getSource(id)) {
          map.removeSource(id);
        }
      } catch (error) {
        // Source/layer might not exist, continue silently
        console.debug(`Removing layer/source ${id}:`, error.message);
      }
    });

    // Create line geometry
    const coordinates = measurement.points.map(p => [p.lng, p.lat]);

    // Add line source safely
    try {
      map.addSource(lineId, {
        type: 'geojson',
        data: {
          type: 'Feature',
          geometry: {
            type: 'LineString',
            coordinates
          },
          properties: {}
        }
      });
    } catch (error) {
      console.warn(`Failed to add line source ${lineId}:`, error.message);
      return;
    }

    // Add line layer safely
    try {
      map.addLayer({
        id: lineId,
        type: 'line',
        source: lineId,
        paint: {
          'line-color': '#ff6b35',
          'line-width': 3,
          'line-dasharray': [2, 2],
          'line-opacity': measurement.isVisible ? 1 : 0,
        }
      });
    } catch (error) {
      console.warn(`Failed to add line layer ${lineId}:`, error.message);
      return;
    }





    // Add start and end point markers safely
    [measurement.points[0], measurement.points[1]].forEach((point, index) => {
      const pointId = index === 0 ? startPointId : endPointId;
      const pointSourceId = `${pointId}-source`;

      try {
        map.addSource(pointSourceId, {
          type: 'geojson',
          data: {
            type: 'Feature',
            geometry: {
              type: 'Point',
              coordinates: [point.lng, point.lat]
            },
            properties: {}
          }
        });
      } catch (error) {
        console.warn(`Failed to add point source ${pointSourceId}:`, error.message);
        return;
      }

      try {
        map.addLayer({
          id: pointId,
          type: 'circle',
          source: pointSourceId,
          paint: {
            'circle-radius': 6,
            'circle-color': '#ff6b35',
            'circle-stroke-color': '#ffffff',
            'circle-stroke-width': 2,
          }
        });
      } catch (error) {
        console.warn(`Failed to add point layer ${pointId}:`, error.message);
      }

      // Add coordinate text labels if enabled
      if (showCoordinates) {
        const coordLabelId = `${pointId}-coord`;
        const coordSourceId = `${coordLabelId}-source`;
        const coordText = `${point.lat.toFixed(4)}, ${point.lng.toFixed(4)}`;
        const pointLabel = index === 0 ? 'START' : 'END';

        // Offset coordinate label slightly from the point for readability
        const offsetLat = index === 0 ? 0.0001 : -0.0001;
        const coordPoint = [point.lng, point.lat + offsetLat];

        try {
          map.addSource(coordSourceId, {
            type: 'geojson',
            data: {
              type: 'Feature',
              geometry: {
                type: 'Point',
                coordinates: coordPoint
              },
              properties: {
                text: `${pointLabel}\n${coordText}`,
                snapped: point.snappedFeature ? `Snapped: ${point.snappedFeature}` : 'Manual placement'
              }
            }
          });

          // Add text label layer (if supported) or fallback to symbol
          try {
            map.addLayer({
              id: coordLabelId,
              type: 'symbol',
              source: coordSourceId,
              layout: {
                'text-field': ['get', 'text'],
                'text-size': 12
              },
              paint: {
                'text-color': '#1f2937', // gray-800
                'text-halo-color': '#ffffff',
                'text-halo-width': 2
              }
            });
            console.debug(`📍 Added coordinate text label for ${pointLabel}: ${coordText}`);
          } catch (textError) {
            // Fallback to circle marker if text labels aren't supported
            console.warn(`Text labels not supported, falling back to marker for ${coordLabelId}`);
            map.addLayer({
              id: coordLabelId,
              type: 'circle',
              source: coordSourceId,
              paint: {
                'circle-radius': 6,
                'circle-color': '#6b7280', // gray-500
                'circle-stroke-color': '#ffffff',
                'circle-stroke-width': 2,
              }
            });
          }
        } catch (error) {
          console.warn(`Failed to add coordinate label ${coordLabelId}:`, error.message);
        }
      }
    });

    onMeasurementLoad?.(measurement);
    console.log(`✅ Measurement ${measurement.id} rendered on map`);
  }, [map, showCoordinates, onMeasurementLoad]);

  // Remove a measurement from the map
  const removeMeasurement = useCallback((measurement: Measurement) => {
    if (!map) return;

    const lineId = `measurement-line-${measurement.id}`;
    const startPointId = `measurement-start-${measurement.id}`;
    const endPointId = `measurement-end-${measurement.id}`;
    const startPointSourceId = `${startPointId}-source`;
    const endPointSourceId = `${endPointId}-source`;
    const startCoordId = `${startPointId}-coord`;
    const endCoordId = `${endPointId}-coord`;
    const startCoordSourceId = `${startCoordId}-source`;
    const endCoordSourceId = `${endCoordId}-source`;

    [lineId, startPointId, endPointId, startPointSourceId, endPointSourceId, startCoordId, endCoordId, startCoordSourceId, endCoordSourceId].forEach(id => {
      try {
        if (map.getLayer(id)) map.removeLayer(id);
      } catch (error) {
        console.debug(`Error removing layer ${id}:`, error.message);
      }
      try {
        if (map.getSource(id)) map.removeSource(id);
      } catch (error) {
        console.debug(`Error removing source ${id}:`, error.message);
      }
    });

    onMeasurementUnload?.(measurement);
    console.log(`🗑️ Measurement ${measurement.id} removed from map`);
  }, [map, onMeasurementUnload]);

  // Update measurements when they change
  useEffect(() => {
    if (!map || !isLoaded) return;

    // Draw all measurements
    measurements.forEach(measurement => {
      drawMeasurement(measurement);
    });

    // Cleanup function to remove all measurements
    return () => {
      measurements.forEach(measurement => {
        removeMeasurement(measurement);
      });
    };
  }, [map, isLoaded, measurements, drawMeasurement, removeMeasurement]);

  // Handle visibility changes
  useEffect(() => {
    if (!map || !isLoaded) return;

    measurements.forEach(measurement => {
      const lineId = `measurement-line-${measurement.id}`;
      const labelId = `measurement-label-${measurement.id}`;

      if (map.getLayer(lineId)) {
        map.setPaintProperty(lineId, 'line-opacity', measurement.isVisible ? 1 : 0);
      }
      if (map.getLayer(labelId)) {
        map.setLayoutProperty(labelId, 'visibility', measurement.isVisible ? 'visible' : 'none');
      }
    });
  }, [map, isLoaded, measurements]);

  return null; // This component doesn't render anything itself
};
