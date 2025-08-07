"""
Base parser classes and implementations

Parsers convert raw data blobs from collectors into structured ResourceRecord objects.
They must be deterministic and side-effect free as per the technical specification.
"""

import json
import re
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Dict, List, Optional

import structlog

from ..models import RawBlob, ResourceKind, ResourceRecord

logger = structlog.get_logger(__name__)


class ParserError(Exception):
    """Base exception for parser errors"""
    pass


class Parser(ABC):
    """Abstract base class for all parsers
    
    Parsers must be deterministic and side-effect free.
    They convert RawBlob data into structured ResourceRecord objects.
    """
    
    @abstractmethod
    def feed(self, blob: RawBlob) -> List[ResourceRecord]:
        """Parse raw blob into ResourceRecord objects
        
        Args:
            blob: Raw data blob from collector
            
        Returns:
            List of parsed ResourceRecord objects
            
        Raises:
            ParserError: When parsing fails
        """
        pass
    
    def _safe_get(self, data: Dict[str, Any], path: str, default: Any = None) -> Any:
        """Safely get nested dictionary value using dot notation"""
        keys = path.split('.')
        value = data
        
        try:
            for key in keys:
                if isinstance(value, dict):
                    value = value[key]
                elif isinstance(value, list) and key.isdigit():
                    value = value[int(key)]
                else:
                    return default
            return value
        except (KeyError, IndexError, TypeError, ValueError):
            return default
    
    def _parse_timestamp(self, timestamp_str: Optional[str]) -> Optional[datetime]:
        """Parse Kubernetes timestamp string to datetime"""
        if not timestamp_str:
            return None
        
        try:
            # Handle RFC3339 format with or without nanoseconds
            if '.' in timestamp_str and 'Z' in timestamp_str:
                # Format: 2023-01-01T12:00:00.123456789Z
                timestamp_str = re.sub(r'\.(\d{6})\d*Z', r'.\1Z', timestamp_str)
                return datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
            elif 'Z' in timestamp_str:
                # Format: 2023-01-01T12:00:00Z
                return datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
            else:
                # Try to parse as-is
                return datetime.fromisoformat(timestamp_str)
        except (ValueError, TypeError) as e:
            logger.warning("Failed to parse timestamp", timestamp=timestamp_str, error=str(e))
            return None


class KubernetesResourceParser(Parser):
    """Parser for standard Kubernetes resource JSON"""
    
    def feed(self, blob: RawBlob) -> List[ResourceRecord]:
        """Parse Kubernetes resource JSON into ResourceRecord objects"""
        if blob.content_type != "application/json":
            return []
        
        try:
            data = blob.data
            if isinstance(data, str):
                data = json.loads(data)
            
            if not isinstance(data, dict):
                return []
            
            # Handle both single resources and lists
            if data.get('kind') == 'List':
                items = data.get('items', [])
                return [self._parse_single_resource(item) for item in items if item]
            else:
                resource = self._parse_single_resource(data)
                return [resource] if resource else []
                
        except Exception as e:
            logger.warning("Failed to parse Kubernetes resource", error=str(e))
            return []
    
    def _parse_single_resource(self, data: Dict[str, Any]) -> Optional[ResourceRecord]:
        """Parse a single Kubernetes resource object"""
        try:
            # Extract basic metadata
            kind_str = data.get('kind', 'Unknown')
            metadata = data.get('metadata', {})
            
            # Map kind string to enum
            try:
                kind = ResourceKind(kind_str)
            except ValueError:
                logger.debug("Unknown resource kind", kind=kind_str)
                return None
            
            name = metadata.get('name')
            uid = metadata.get('uid', '')
            namespace = metadata.get('namespace')
            
            if not name or not uid:
                logger.debug("Resource missing name or UID", data=metadata)
                return None
            
            # Extract timestamps
            creation_timestamp = self._parse_timestamp(
                metadata.get('creationTimestamp')
            )
            
            # Extract labels and annotations
            labels = metadata.get('labels', {})
            annotations = metadata.get('annotations', {})
            
            # Extract status
            status = self._extract_resource_status(data, kind)
            
            # Store the full resource data in properties
            properties = {
                'spec': data.get('spec', {}),
                'status': data.get('status', {}),
                'metadata': metadata,
            }
            
            return ResourceRecord(
                kind=kind,
                name=name,
                uid=uid,
                namespace=namespace,
                properties=properties,
                status=status,
                creation_timestamp=creation_timestamp,
                labels=labels,
                annotations=annotations,
            )
            
        except Exception as e:
            logger.warning("Failed to parse single resource", error=str(e))
            return None
    
    def _extract_resource_status(self, data: Dict[str, Any], kind: ResourceKind) -> Optional[str]:
        """Extract status string based on resource type"""
        status_obj = data.get('status', {})
        
        if kind == ResourceKind.POD:
            return status_obj.get('phase', 'Unknown')
        
        elif kind == ResourceKind.NODE:
            conditions = status_obj.get('conditions', [])
            for condition in conditions:
                if condition.get('type') == 'Ready':
                    return 'Ready' if condition.get('status') == 'True' else 'NotReady'
            return 'Unknown'
        
        elif kind in [ResourceKind.DEPLOYMENT, ResourceKind.STATEFULSET, ResourceKind.DAEMONSET]:
            conditions = status_obj.get('conditions', [])
            for condition in conditions:
                if condition.get('type') == 'Available':
                    return 'Available' if condition.get('status') == 'True' else 'Unavailable'
            return 'Unknown'
        
        elif kind == ResourceKind.PVC:
            return status_obj.get('phase', 'Unknown')
        
        elif kind == ResourceKind.PV:
            return status_obj.get('phase', 'Unknown')
        
        elif kind == ResourceKind.SERVICE:
            # Services don't have a clear status, assume Active if it exists
            return 'Active'
        
        elif kind == ResourceKind.JOB:
            conditions = status_obj.get('conditions', [])
            for condition in conditions:
                if condition.get('type') == 'Complete':
                    return 'Complete' if condition.get('status') == 'True' else 'Running'
                elif condition.get('type') == 'Failed':
                    return 'Failed' if condition.get('status') == 'True' else 'Running'
            return 'Running'
        
        else:
            # Default to Active for other resource types
            return 'Active'


class EventParser(Parser):
    """Parser for Kubernetes events"""
    
    def feed(self, blob: RawBlob) -> List[ResourceRecord]:
        """Parse Kubernetes events into ResourceRecord objects"""
        if blob.content_type != "application/json":
            return []
        
        try:
            data = blob.data
            if isinstance(data, str):
                data = json.loads(data)
            
            if not isinstance(data, dict):
                return []
            
            items = data.get('items', [])
            events = []
            
            for item in items:
                event = self._parse_single_event(item)
                if event:
                    events.append(event)
            
            return events
            
        except Exception as e:
            logger.warning("Failed to parse events", error=str(e))
            return []
    
    def _parse_single_event(self, data: Dict[str, Any]) -> Optional[ResourceRecord]:
        """Parse a single Kubernetes event"""
        try:
            metadata = data.get('metadata', {})
            involved_object = data.get('involvedObject', {})
            
            name = metadata.get('name', '')
            uid = metadata.get('uid', '')
            namespace = metadata.get('namespace')
            
            if not uid:
                return None
            
            # Extract event details
            reason = data.get('reason', 'Unknown')
            message = data.get('message', '')
            event_type = data.get('type', 'Normal')
            first_timestamp = self._parse_timestamp(data.get('firstTimestamp'))
            last_timestamp = self._parse_timestamp(data.get('lastTimestamp'))
            count = data.get('count', 1)
            
            # Store event-specific properties
            properties = {
                'reason': reason,
                'message': message,
                'type': event_type,
                'count': count,
                'involvedObject': involved_object,
                'source': data.get('source', {}),
                'firstTimestamp': first_timestamp.isoformat() if first_timestamp else None,
                'lastTimestamp': last_timestamp.isoformat() if last_timestamp else None,
            }
            
            return ResourceRecord(
                kind=ResourceKind.EVENT,
                name=name or f"event-{uid[:8]}",
                uid=uid,
                namespace=namespace,
                properties=properties,
                status=event_type,
                creation_timestamp=first_timestamp,
            )
            
        except Exception as e:
            logger.warning("Failed to parse single event", error=str(e))
            return None


class TextParser(Parser):
    """Parser for plain text output (logs, describe, etc.)"""
    
    def feed(self, blob: RawBlob) -> List[ResourceRecord]:
        """Parse text blob - returns empty list as text doesn't create resources"""
        # Text parsers typically don't create ResourceRecord objects
        # but may extract information for other purposes
        return []


class MetricsParser(Parser):
    """Parser for metrics-server output"""
    
    def feed(self, blob: RawBlob) -> List[ResourceRecord]:
        """Parse metrics output into resource records with metrics data"""
        if blob.content_type != "text/plain":
            return []
        
        try:
            data = blob.data
            if isinstance(data, dict):
                data = data.get('raw', '')
            
            if not isinstance(data, str):
                return []
            
            # Parse metrics table output
            lines = data.strip().split('\n')
            if len(lines) < 2:  # Need header and at least one data line
                return []
            
            header = lines[0]
            if 'CPU' not in header or 'MEMORY' not in header:
                return []
            
            resources = []
            for line in lines[1:]:
                resource = self._parse_metrics_line(line)
                if resource:
                    resources.append(resource)
            
            return resources
            
        except Exception as e:
            logger.warning("Failed to parse metrics", error=str(e))
            return []
    
    def _parse_metrics_line(self, line: str) -> Optional[ResourceRecord]:
        """Parse a single metrics line"""
        try:
            parts = line.split()
            if len(parts) < 3:
                return None
            
            name = parts[0]
            cpu = parts[1]
            memory = parts[2]
            
            # Create a pseudo-resource for metrics
            properties = {
                'metrics': {
                    'cpu': cpu,
                    'memory': memory,
                }
            }
            
            return ResourceRecord(
                kind=ResourceKind.POD,  # Assume pod metrics for now
                name=name,
                uid=f"metrics-{name}",
                properties=properties,
                status='Active'
            )
            
        except Exception as e:
            logger.debug("Failed to parse metrics line", line=line, error=str(e))
            return None


class ParserRegistry:
    """Registry for managing parsers"""
    
    def __init__(self):
        self._parsers = {}
        self._register_defaults()
    
    def _register_defaults(self):
        """Register default parsers"""
        self._parsers.update({
            'kubernetes': KubernetesResourceParser(),
            'events': EventParser(),
            'text': TextParser(),
            'metrics': MetricsParser(),
        })
    
    def register(self, name: str, parser: Parser):
        """Register a custom parser"""
        self._parsers[name] = parser
    
    def get_parser(self, blob: RawBlob) -> Parser:
        """Get appropriate parser for a blob"""
        if blob.source == "kubectl_events":
            return self._parsers['events']
        elif blob.content_type == "text/plain":
            if blob.source == "metrics_server":
                return self._parsers['metrics']
            else:
                return self._parsers['text']
        else:
            return self._parsers['kubernetes']
    
    def parse(self, blob: RawBlob) -> List[ResourceRecord]:
        """Parse a blob using the appropriate parser"""
        parser = self.get_parser(blob)
        return parser.feed(blob)


# Global registry instance
registry = ParserRegistry()