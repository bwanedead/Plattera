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
  onMeasurementLoad?: (measurement: Measurement) => void;
  onMeasurementUnload?: (measurement: Measurement) => void;
}

export const MeasurementOverlay: React.FC<MeasurementOverlayProps> = ({
  measurements,
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

    // Add distance label at midpoint
    if (measurement.points.length === 2 && measurement.isVisible) {
      const midPoint = [
        (measurement.points[0].lng + measurement.points[1].lng) / 2,
        (measurement.points[0].lat + measurement.points[1].lat) / 2
      ];

      // Use circle marker instead of text label for better compatibility
      try {
        map.addSource(`${labelId}-label`, {
          type: 'geojson',
          data: {
            type: 'Feature',
            geometry: {
              type: 'Point',
              coordinates: [midPoint[0], midPoint[1]]
            },
            properties: {
              distance: `${measurement.distance.toFixed(1)} ft`
            }
          }
        });

        map.addLayer({
          id: labelId,
          type: 'circle',
          source: `${labelId}-label`,
          paint: {
            'circle-radius': 8,
            'circle-color': '#3b82f6', // blue-500
            'circle-stroke-color': '#ffffff',
            'circle-stroke-width': 2,
          }
        });

        console.debug(`✅ Added measurement label marker at ${midPoint[0].toFixed(6)}, ${midPoint[1].toFixed(6)}`);
      } catch (error) {
        console.warn(`Failed to add measurement label marker ${labelId}:`, error.message);
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
      });
    }

    onMeasurementLoad?.(measurement);
    console.log(`✅ Measurement ${measurement.id} rendered on map`);
  }, [map, onMeasurementLoad]);

  // Remove a measurement from the map
  const removeMeasurement = useCallback((measurement: Measurement) => {
    if (!map) return;

    const lineId = `measurement-line-${measurement.id}`;
    const labelId = `measurement-label-${measurement.id}`;
    const startPointId = `measurement-start-${measurement.id}`;
    const endPointId = `measurement-end-${measurement.id}`;
    const startPointSourceId = `${startPointId}-source`;
    const endPointSourceId = `${endPointId}-source`;
    const labelSourceId = `${labelId}-label`;

    [lineId, labelId, startPointId, endPointId, startPointSourceId, endPointSourceId, labelSourceId].forEach(id => {
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
