/**
 * Polygon Drawing Controls
 * Handles user interaction for drawing polygons from schema descriptions
 */
import React, { useState, useMemo } from 'react';
import { drawPolygonFromSchema, PolygonResult } from '../../services/polygonApi';
import { VisualizationWorkspace } from '../visualization/VisualizationWorkspace';

interface Description {
  description_id: number;
  is_complete: boolean;
  plss: any;
  metes_and_bounds: any;
}

interface PolygonDrawingControlsProps {
  schemaData: any;
  isVisible: boolean;
}

export const PolygonDrawingControls: React.FC<PolygonDrawingControlsProps> = ({
  schemaData,
  isVisible
}) => {
  const [drawingStates, setDrawingStates] = useState<Record<number, 'idle' | 'loading' | 'success' | 'error'>>({});
  const [polygonResults, setPolygonResults] = useState<Record<number, PolygonResult>>({});
  const [viewingPolygon, setViewingPolygon] = useState<PolygonResult | null>(null);
  const [errors, setErrors] = useState<Record<number, string>>({});

  // Get complete descriptions that can be drawn
  const drawableDescriptions = useMemo(() => {
    if (!schemaData?.descriptions) return [];
    
    return schemaData.descriptions.filter((desc: Description) => {
      return desc.is_complete && 
             desc.metes_and_bounds?.boundary_courses?.length >= 3;
    });
  }, [schemaData]);

  const handleDrawPolygon = async (descriptionId: number) => {
    setDrawingStates(prev => ({ ...prev, [descriptionId]: 'loading' }));
    setErrors(prev => ({ ...prev, [descriptionId]: '' }));

    try {
      // Create request with single description
      const singleDescriptionData = {
        ...schemaData,
        descriptions: schemaData.descriptions.filter((desc: Description) => 
          desc.description_id === descriptionId
        )
      };

      const response = await drawPolygonFromSchema({
        parcel_data: singleDescriptionData,
        options: {
          coordinate_system: 'local',
          distance_units: 'feet',
          closure_tolerance_feet: 1.0,
          output_format: 'coordinates'
        }
      });

      if (response.success && response.polygons && response.polygons.length > 0) {
        const polygon = response.polygons[0];
        setPolygonResults(prev => ({ ...prev, [descriptionId]: polygon }));
        setDrawingStates(prev => ({ ...prev, [descriptionId]: 'success' }));
        
        // Auto-open the viewer
        setViewingPolygon(polygon);
      } else {
        throw new Error(response.error || 'Failed to generate polygon');
      }
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Unknown error';
      setErrors(prev => ({ ...prev, [descriptionId]: errorMessage }));
      setDrawingStates(prev => ({ ...prev, [descriptionId]: 'error' }));
    }
  };

  const handleViewPolygon = (descriptionId: number) => {
    const polygon = polygonResults[descriptionId];
    if (polygon) {
      setViewingPolygon(polygon);
    }
  };

  if (!isVisible || drawableDescriptions.length === 0) {
    return null;
  }

  return (
    <>
      <div className="polygon-drawing-controls-minimal">
        <div className="controls-header-minimal">
          <span className="controls-title">🔧 Available Polygons</span>
        </div>

        <div className="polygon-items">
          {drawableDescriptions.map((desc: Description) => {
            const state = drawingStates[desc.description_id] || 'idle';
            const hasResult = !!polygonResults[desc.description_id];
            const error = errors[desc.description_id];

            return (
              <div key={desc.description_id} className="polygon-item">
                <div className="polygon-item-content">
                  <span className="description-name">
                    Description {desc.description_id}
                  </span>
                  <span className="course-info">
                    {desc.metes_and_bounds.boundary_courses.length} courses
                  </span>
                </div>

                <div className="polygon-actions">
                  {!hasResult ? (
                    <button
                      className={`draw-btn ${state}`}
                      onClick={() => handleDrawPolygon(desc.description_id)}
                      disabled={state === 'loading'}
                    >
                      {state === 'loading' ? (
                        <>
                          <div className="mini-spinner"></div>
                          Drawing
                        </>
                      ) : (
                        'Draw'
                      )}
                    </button>
                  ) : (
                    <button
                      className="view-btn"
                      onClick={() => handleViewPolygon(desc.description_id)}
                    >
                      View
                    </button>
                  )}
                </div>

                {error && (
                  <div className="error-text">
                    {error}
                  </div>
                )}

                {hasResult && (
                  <div className="result-info">
                    {(polygonResults[desc.description_id].properties.area_calculated / 43560).toFixed(2)} acres
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* Visualization Workspace */}
      {viewingPolygon && (
        <VisualizationWorkspace
          polygon={viewingPolygon}
          schemaData={schemaData} // Add schema data
          isOpen={!!viewingPolygon}
          onClose={() => setViewingPolygon(null)}
        />
      )}
    </>
  );
};