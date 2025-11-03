import React, { useState, useEffect } from 'react';

interface ProcessingStatusProps {
  isProcessing: boolean;
  status: string;
  progress?: number;
  error?: string;
  onRetry?: () => void;
}

interface HealthStatus {
  status: string;
  memory_usage_mb: number;
  cpu_percent: number;
  uptime_seconds: number;
  overall_status: string;
  recommendations: string[];
  errors: string[];
}

interface CleanupResult {
  status: string;
  actions_performed: string[];
  memory_before_mb: number;
  memory_after_mb: number;
  memory_freed_mb: number;
  errors: string[];
}

const ProcessingStatus: React.FC<ProcessingStatusProps> = ({
  isProcessing,
  status,
  progress,
  error,
  onRetry
}) => {
  const [healthStatus, setHealthStatus] = useState<HealthStatus | null>(null);
  const [isCheckingHealth, setIsCheckingHealth] = useState(false);
  const [isPerformingCleanup, setIsPerformingCleanup] = useState(false);
  const [cleanupResult, setCleanupResult] = useState<CleanupResult | null>(null);
  const [showHealthDetails, setShowHealthDetails] = useState(false);

  const checkHealth = async () => {
    setIsCheckingHealth(true);
    try {
      const response = await fetch('http://localhost:8000/api/health');
      if (response.ok) {
        const health = await response.json();
        setHealthStatus(health);
      } else {
        console.error('Health check failed:', response.statusText);
      }
    } catch (error) {
      console.error('Health check error:', error);
    } finally {
      setIsCheckingHealth(false);
    }
  };

  const performCleanup = async () => {
    setIsPerformingCleanup(true);
    try {
      const response = await fetch('http://localhost:8000/api/cleanup', {
        method: 'POST',
      });
      if (response.ok) {
        const result = await response.json();
        setCleanupResult(result);
        // Refresh health status after cleanup
        setTimeout(checkHealth, 1000);
      } else {
        console.error('Cleanup failed:', response.statusText);
      }
    } catch (error) {
      console.error('Cleanup error:', error);
    } finally {
      setIsPerformingCleanup(false);
    }
  };

  useEffect(() => {
    // Check health on component mount
    checkHealth();
    
    // Set up periodic health checks every 30 seconds
    const healthInterval = setInterval(checkHealth, 30000);
    
    return () => clearInterval(healthInterval);
  }, []);

  const getHealthStatusColor = (status: string) => {
    switch (status) {
      case 'healthy': return 'text-green-600';
      case 'warning': return 'text-yellow-600';
      case 'maintenance_needed': return 'text-orange-600';
      case 'error': return 'text-red-600';
      default: return 'text-gray-600';
    }
  };

  const getHealthStatusIcon = (status: string) => {
    switch (status) {
      case 'healthy': return '✅';
      case 'warning': return '⚠️';
      case 'maintenance_needed': return '🔧';
      case 'error': return '❌';
      default: return '❓';
    }
  };

  if (isProcessing) {
    return (
      <div className="processing-status">
        <div className="processing-spinner">
          <div className="spinner"></div>
        </div>
        <div className="processing-text">
          <h3>Processing...</h3>
          <p>{status}</p>
          {progress !== undefined && (
            <div className="progress-bar">
              <div 
                className="progress-fill" 
                style={{ width: `${progress}%` }}
              ></div>
            </div>
          )}
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="processing-status error">
        <div className="error-icon">❌</div>
        <div className="error-text">
          <h3>Processing Error</h3>
          <p>{error}</p>
          {onRetry && (
            <button 
              onClick={onRetry}
              className="retry-button"
            >
              Retry
            </button>
          )}
        </div>
      </div>
    );
  }

  // Show health monitoring when not processing
  return (
    <div className="health-monitoring">
      <div className="health-header">
        <h3>System Health Monitor</h3>
        <button 
          onClick={checkHealth}
          disabled={isCheckingHealth}
          className="health-check-button"
        >
          {isCheckingHealth ? 'Checking...' : '🔄 Refresh'}
        </button>
      </div>

      {healthStatus && (
        <div className="health-status">
          <div className={`health-indicator ${getHealthStatusColor(healthStatus.overall_status)}`}>
            <span className="health-icon">{getHealthStatusIcon(healthStatus.overall_status)}</span>
            <span className="health-text">
              {healthStatus.overall_status.charAt(0).toUpperCase() + healthStatus.overall_status.slice(1)}
            </span>
          </div>

          <div className="health-metrics">
            <div className="metric">
              <span className="metric-label">Memory:</span>
              <span className="metric-value">{healthStatus.memory_usage_mb.toFixed(1)} MB</span>
            </div>
            <div className="metric">
              <span className="metric-label">CPU:</span>
              <span className="metric-value">{healthStatus.cpu_percent.toFixed(1)}%</span>
            </div>
            <div className="metric">
              <span className="metric-label">Uptime:</span>
              <span className="metric-value">{Math.floor(healthStatus.uptime_seconds / 60)}m</span>
            </div>
          </div>

          {healthStatus.recommendations.length > 0 && (
            <div className="health-recommendations">
              <h4>Recommendations:</h4>
              <ul>
                {healthStatus.recommendations.map((rec, index) => (
                  <li key={index}>{rec}</li>
                ))}
              </ul>
            </div>
          )}

          <div className="health-actions">
            <button 
              onClick={() => setShowHealthDetails(!showHealthDetails)}
              className="details-button"
            >
              {showHealthDetails ? 'Hide Details' : 'Show Details'}
            </button>
            
            <button 
              onClick={performCleanup}
              disabled={isPerformingCleanup}
              className="cleanup-button"
            >
              {isPerformingCleanup ? 'Cleaning...' : '🧹 Cleanup'}
            </button>
          </div>

          {showHealthDetails && (
            <div className="health-details">
              <h4>Detailed Status:</h4>
              <pre>{JSON.stringify(healthStatus, null, 2)}</pre>
            </div>
          )}
        </div>
      )}

      {cleanupResult && (
        <div className="cleanup-result">
          <h4>Cleanup Results:</h4>
          <div className="cleanup-metrics">
            <div className="metric">
              <span className="metric-label">Status:</span>
              <span className="metric-value">{cleanupResult.status}</span>
            </div>
            <div className="metric">
              <span className="metric-label">Memory Freed:</span>
              <span className="metric-value">{cleanupResult.memory_freed_mb.toFixed(1)} MB</span>
            </div>
          </div>
          {cleanupResult.actions_performed.length > 0 && (
            <div className="cleanup-actions">
              <h5>Actions Performed:</h5>
              <ul>
                {cleanupResult.actions_performed.map((action, index) => (
                  <li key={index}>{action}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default ProcessingStatus; 