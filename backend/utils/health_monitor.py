"""
Health Monitoring Module
========================

Monitors system resources and detects potential corruption issues in the alignment pipeline.
Provides cleanup utilities and health checks to prevent system-level state corruption.
"""

import logging
import gc
import os
import time
from typing import Dict, Any, Optional
from pathlib import Path
import psutil

logger = logging.getLogger(__name__)


class HealthMonitor:
    """
    Monitors system health and provides cleanup utilities to prevent corruption.
    """
    
    def __init__(self):
        self.start_time = time.time()
        self.memory_threshold_mb = 500  # 500MB threshold
        self.last_cleanup_time = 0
        self.cleanup_interval_seconds = 300  # 5 minutes
        
    def check_system_health(self) -> Dict[str, Any]:
        """
        Check current system health status.
        
        Returns:
            Dict with health metrics and recommendations
        """
        try:
            process = psutil.Process(os.getpid())
            memory_info = process.memory_info()
            cpu_percent = process.cpu_percent()
            
            memory_mb = memory_info.rss / 1024 / 1024
            uptime_seconds = time.time() - self.start_time
            
            health_status = {
                'memory_usage_mb': round(memory_mb, 1),
                'cpu_percent': round(cpu_percent, 1),
                'uptime_seconds': round(uptime_seconds, 1),
                'memory_threshold_exceeded': memory_mb > self.memory_threshold_mb,
                'needs_cleanup': self._should_perform_cleanup(),
                'file_system_healthy': self._check_file_system_health(),
                'overall_status': 'healthy'
            }
            
            # Determine overall status
            if health_status['memory_threshold_exceeded']:
                health_status['overall_status'] = 'warning'
                health_status['recommendations'] = ['Perform memory cleanup']
            
            if not health_status['file_system_healthy']:
                health_status['overall_status'] = 'warning'
                if 'recommendations' not in health_status:
                    health_status['recommendations'] = []
                health_status['recommendations'].append('Check file system locks')
            
            if health_status['needs_cleanup']:
                health_status['overall_status'] = 'maintenance_needed'
                if 'recommendations' not in health_status:
                    health_status['recommendations'] = []
                health_status['recommendations'].append('Perform scheduled cleanup')
            
            logger.info(f"🏥 HEALTH CHECK ► Memory: {memory_mb:.1f}MB, CPU: {cpu_percent:.1f}%, Status: {health_status['overall_status']}")
            
            return health_status
            
        except Exception as e:
            logger.error(f"❌ Health check failed: {e}")
            return {
                'overall_status': 'error',
                'error': str(e),
                'recommendations': ['Restart the application']
            }
    
    def perform_cleanup(self, force: bool = False) -> Dict[str, Any]:
        """
        Perform system cleanup to prevent corruption.
        
        Args:
            force: Force cleanup even if not scheduled
            
        Returns:
            Dict with cleanup results
        """
        if not force and not self._should_perform_cleanup():
            return {'status': 'skipped', 'reason': 'Not scheduled for cleanup'}
        
        cleanup_results = {
            'status': 'completed',
            'actions_performed': [],
            'memory_before_mb': 0,
            'memory_after_mb': 0,
            'errors': []
        }
        
        try:
            # Get memory usage before cleanup
            process = psutil.Process(os.getpid())
            memory_before = process.memory_info().rss / 1024 / 1024
            cleanup_results['memory_before_mb'] = round(memory_before, 1)
            
            logger.info(f"🧹 STARTING CLEANUP ► Memory before: {memory_before:.1f}MB")
            
            # Clear LRU caches
            try:
                from alignment.consistency_aligner import levenshtein
                cache_info = levenshtein.cache_info()
                levenshtein.cache_clear()
                cleanup_results['actions_performed'].append(f"Cleared LRU cache ({cache_info.hits} hits, {cache_info.misses} misses)")
                logger.info(f"🧹 CLEARED LRU CACHE ► {cache_info.hits} hits, {cache_info.misses} misses")
            except Exception as e:
                cleanup_results['errors'].append(f"Failed to clear LRU cache: {e}")
                logger.warning(f"⚠️ Failed to clear LRU cache: {e}")
            
            # Force garbage collection
            try:
                collected = gc.collect()
                cleanup_results['actions_performed'].append(f"Garbage collection freed {collected} objects")
                logger.info(f"🧹 GARBAGE COLLECTION ► Freed {collected} objects")
            except Exception as e:
                cleanup_results['errors'].append(f"Failed garbage collection: {e}")
                logger.warning(f"⚠️ Failed garbage collection: {e}")
            
            # Clean up file system locks
            try:
                file_cleanup = self._cleanup_file_system_locks()
                cleanup_results['actions_performed'].extend(file_cleanup)
            except Exception as e:
                cleanup_results['errors'].append(f"Failed file system cleanup: {e}")
                logger.warning(f"⚠️ Failed file system cleanup: {e}")
            
            # Get memory usage after cleanup
            memory_after = process.memory_info().rss / 1024 / 1024
            cleanup_results['memory_after_mb'] = round(memory_after, 1)
            memory_freed = memory_before - memory_after
            
            self.last_cleanup_time = time.time()
            
            logger.info(f"✅ CLEANUP COMPLETE ► Memory after: {memory_after:.1f}MB (freed {memory_freed:.1f}MB)")
            
            if memory_freed > 0:
                cleanup_results['actions_performed'].append(f"Freed {memory_freed:.1f}MB of memory")
            
        except Exception as e:
            cleanup_results['status'] = 'error'
            cleanup_results['errors'].append(f"Cleanup failed: {e}")
            logger.error(f"❌ CLEANUP FAILED: {e}")
        
        return cleanup_results
    
    def _should_perform_cleanup(self) -> bool:
        """Check if cleanup should be performed based on time interval."""
        return (time.time() - self.last_cleanup_time) > self.cleanup_interval_seconds
    
    def _check_file_system_health(self) -> bool:
        """Check if file system is healthy (no locked files)."""
        try:
            debug_dir = Path(r"C:\projects\Plattera\backend\raw_alignment_tables")
            if not debug_dir.exists():
                return True
            
            # Check for temporary files that might indicate corruption
            temp_files = list(debug_dir.glob("*.tmp"))
            if temp_files:
                logger.warning(f"⚠️ Found {len(temp_files)} temporary files that may indicate corruption")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"❌ File system health check failed: {e}")
            return False
    
    def _cleanup_file_system_locks(self) -> list:
        """Clean up any file system locks or temporary files."""
        cleanup_actions = []
        
        try:
            debug_dir = Path(r"C:\projects\Plattera\backend\raw_alignment_tables")
            if not debug_dir.exists():
                return cleanup_actions
            
            # Remove temporary files
            temp_files = list(debug_dir.glob("*.tmp"))
            for temp_file in temp_files:
                try:
                    temp_file.unlink()
                    cleanup_actions.append(f"Removed temporary file: {temp_file.name}")
                    logger.info(f"🧹 REMOVED TEMP FILE ► {temp_file.name}")
                except Exception as e:
                    logger.warning(f"⚠️ Failed to remove temporary file {temp_file.name}: {e}")
            
            # Check for corrupted debug files (very large files might indicate corruption)
            debug_files = list(debug_dir.glob("*.txt"))
            for debug_file in debug_files:
                try:
                    file_size_mb = debug_file.stat().st_size / 1024 / 1024
                    if file_size_mb > 50:  # Files larger than 50MB might be corrupted
                        logger.warning(f"⚠️ Large debug file detected: {debug_file.name} ({file_size_mb:.1f}MB)")
                        # Don't automatically delete - just log the warning
                except Exception as e:
                    logger.warning(f"⚠️ Failed to check debug file {debug_file.name}: {e}")
            
        except Exception as e:
            logger.error(f"❌ File system cleanup failed: {e}")
        
        return cleanup_actions


# Global health monitor instance
_health_monitor = None


def get_health_monitor() -> HealthMonitor:
    """Get the global health monitor instance."""
    global _health_monitor
    if _health_monitor is None:
        _health_monitor = HealthMonitor()
    return _health_monitor


def check_health() -> Dict[str, Any]:
    """Convenience function to check system health."""
    return get_health_monitor().check_system_health()


def perform_cleanup(force: bool = False) -> Dict[str, Any]:
    """Convenience function to perform cleanup."""
    return get_health_monitor().perform_cleanup(force) 