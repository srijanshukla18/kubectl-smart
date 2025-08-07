"""
Core data models for kubectl-smart

These models define the standardized data structures used throughout the application,
following the technical specification exactly.
"""

from __future__ import annotations

import json
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field, validator


class ResourceKind(str, Enum):
    """Kubernetes resource kinds supported by kubectl-smart"""
    
    POD = "Pod"
    DEPLOYMENT = "Deployment"
    REPLICASET = "ReplicaSet"
    STATEFULSET = "StatefulSet"
    DAEMONSET = "DaemonSet"
    JOB = "Job"
    CRONJOB = "CronJob"
    SERVICE = "Service"
    INGRESS = "Ingress"
    CONFIGMAP = "ConfigMap"
    SECRET = "Secret"
    PVC = "PersistentVolumeClaim"
    PV = "PersistentVolume"
    STORAGECLASS = "StorageClass"
    NODE = "Node"
    NAMESPACE = "Namespace"
    SERVICEACCOUNT = "ServiceAccount"
    ROLE = "Role"
    ROLEBINDING = "RoleBinding"
    CLUSTERROLE = "ClusterRole"
    CLUSTERROLEBINDING = "ClusterRoleBinding"
    NETWORKPOLICY = "NetworkPolicy"
    HPA = "HorizontalPodAutoscaler"
    VPA = "VerticalPodAutoscaler"
    ENDPOINTS = "Endpoints"
    EVENT = "Event"


class IssueSeverity(str, Enum):
    """Issue severity levels as defined in the technical specification"""
    
    CRITICAL = "critical"  # Score >= 90
    WARNING = "warning"    # Score >= 50
    INFO = "info"         # Score < 50


class RawBlob(BaseModel):
    """Raw data blob from collectors with metadata"""
    
    data: Union[str, bytes, Dict[str, Any]]
    source: str = Field(..., description="Source collector name")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    content_type: str = Field(default="application/json")
    metadata: Dict[str, Any] = Field(default_factory=dict)
    
    class Config:
        arbitrary_types_allowed = True


class ResourceRecord(BaseModel):
    """Standardized Kubernetes resource representation
    
    This is the core data model that all resources are parsed into,
    as specified in the technical documentation.
    """
    
    kind: ResourceKind
    name: str
    uid: str = Field(..., description="Kubernetes UID for unique identification")
    namespace: Optional[str] = None
    properties: Dict[str, Any] = Field(default_factory=dict)
    events: List[Dict[str, Any]] = Field(default_factory=list)
    status: Optional[str] = None
    creation_timestamp: Optional[datetime] = None
    labels: Dict[str, str] = Field(default_factory=dict)
    annotations: Dict[str, str] = Field(default_factory=dict)
    
    @property
    def full_name(self) -> str:
        """Full resource identifier for graph keys"""
        if self.namespace:
            return f"{self.kind.value}/{self.namespace}/{self.name}"
        return f"{self.kind.value}/{self.name}"
    
    @property 
    def short_name(self) -> str:
        """Short resource identifier for display"""
        return f"{self.kind.value.lower()}/{self.name}"
    
    def get_property(self, key: str, default: Any = None) -> Any:
        """Get a property with dot notation support"""
        keys = key.split('.')
        value = self.properties
        
        try:
            for k in keys:
                value = value[k]
            return value
        except (KeyError, TypeError):
            return default


class Issue(BaseModel):
    """Represents an identified issue with severity scoring
    
    Core model for the scoring and prioritization system.
    """
    
    resource_uid: str = Field(..., description="UID of the affected resource")
    title: str = Field(..., description="Brief issue description")
    description: str = Field(..., description="Detailed issue explanation")
    severity: IssueSeverity
    score: float = Field(..., ge=0, le=100, description="Numeric score 0-100")
    reason: str = Field(..., description="Issue reason/type")
    message: str = Field(..., description="Detailed message")
    timestamp: Optional[datetime] = None
    critical_path: bool = Field(default=False, description="Is this issue on a critical path")
    contributing_factors: List[str] = Field(default_factory=list)
    suggested_actions: List[str] = Field(default_factory=list)
    related_events: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    
    @validator('severity', pre=True)
    def validate_severity(cls, v, values):
        """Auto-determine severity from score if not provided"""
        if isinstance(v, str):
            return IssueSeverity(v)
        
        score = values.get('score', 0)
        if score >= 90:
            return IssueSeverity.CRITICAL
        elif score >= 50:
            return IssueSeverity.WARNING
        else:
            return IssueSeverity.INFO
    
    def to_display_dict(self) -> Dict[str, Any]:
        """Convert to dictionary suitable for display rendering"""
        return {
            'title': self.title,
            'severity': self.severity.value,
            'score': self.score,
            'description': self.description,
            'critical_path': self.critical_path,
            'suggested_actions': self.suggested_actions,
            'timestamp': self.timestamp.isoformat() if self.timestamp else None,
        }


class SubjectCtx(BaseModel):
    """Context for the subject of analysis
    
    Carries context information through the analysis pipeline.
    """
    
    kind: ResourceKind
    name: str
    namespace: Optional[str] = None
    uid: Optional[str] = None
    context: Optional[str] = Field(default=None, description="kubectl context")
    scope: str = Field(default="resource", description="Analysis scope: resource, namespace, cluster")
    depth: int = Field(default=3, ge=1, le=5, description="Analysis depth level")
    filters: List[str] = Field(default_factory=list, description="Active filters")
    timeout: float = Field(default=30.0, description="Operation timeout in seconds")
    
    @property
    def full_name(self) -> str:
        """Full subject identifier"""
        if self.namespace:
            return f"{self.kind.value}/{self.namespace}/{self.name}"
        return f"{self.kind.value}/{self.name}"
    
    def kubectl_args(self) -> List[str]:
        """Generate kubectl arguments for this subject"""
        args = []
        if self.context:
            args.extend(['--context', self.context])
        if self.namespace:
            args.extend(['--namespace', self.namespace])
        return args


class DiagnosisResult(BaseModel):
    """Result of a diagnosis operation (diag command)"""
    
    subject: SubjectCtx
    resource: Optional[ResourceRecord] = None
    issues: List[Issue] = Field(default_factory=list)
    root_cause: Optional[Issue] = None
    contributing_factors: List[Issue] = Field(default_factory=list)
    suggested_actions: List[str] = Field(default_factory=list)
    analysis_duration: float = Field(..., description="Analysis time in seconds")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    
    @property
    def critical_issues(self) -> List[Issue]:
        """Get all critical issues"""
        return [issue for issue in self.issues if issue.severity == IssueSeverity.CRITICAL]
    
    @property
    def warning_issues(self) -> List[Issue]:
        """Get all warning issues"""
        return [issue for issue in self.issues if issue.severity == IssueSeverity.WARNING]
    
    def to_json(self) -> str:
        """Export to JSON for API/automation use"""
        return self.json(indent=2, ensure_ascii=False)


class GraphResult(BaseModel):
    """Result of a graph analysis operation (graph command)"""
    
    subject: SubjectCtx
    nodes: List[ResourceRecord] = Field(default_factory=list)
    edges: List[Dict[str, str]] = Field(default_factory=list)
    ascii_graph: str = Field(default="", description="ASCII representation")
    upstream_count: int = 0
    downstream_count: int = 0
    analysis_duration: float = Field(..., description="Analysis time in seconds")
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class TopResult(BaseModel):
    """Result of a top analysis operation (top command)"""
    
    subject: SubjectCtx
    predictions: List[Dict[str, Any]] = Field(default_factory=list)
    capacity_warnings: List[Dict[str, Any]] = Field(default_factory=list)
    certificate_warnings: List[Dict[str, Any]] = Field(default_factory=list)
    forecast_horizon_hours: int = Field(default=48)
    analysis_duration: float = Field(..., description="Analysis time in seconds")
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class AnalysisConfig(BaseModel):
    """Configuration for analysis operations"""
    
    # Performance settings
    max_concurrent_collectors: int = Field(default=5)
    collector_timeout: float = Field(default=10.0)
    cache_ttl_seconds: int = Field(default=300)  # 5 minutes
    
    # Scoring settings
    weights_file: Optional[str] = Field(default="weights.toml")
    min_critical_score: float = Field(default=90.0)
    min_warning_score: float = Field(default=50.0)
    
    # Output settings
    colors_enabled: bool = Field(default=True)
    max_display_issues: int = Field(default=10)
    max_suggested_actions: int = Field(default=5)
    
    # Forecasting settings
    forecast_horizon_hours: int = Field(default=48)
    min_samples_for_forecast: int = Field(default=7)
    cert_warning_days: int = Field(default=14)
    
    def __init__(self, **data):
        super().__init__(**data)
        
        # Load from environment variables if available
        import os
        
        if 'KUBECTL_SMART_COLORS' in os.environ:
            self.colors_enabled = os.environ['KUBECTL_SMART_COLORS'].lower() == 'true'
            
        if 'KUBECTL_SMART_CACHE_TTL' in os.environ:
            try:
                self.cache_ttl_seconds = int(os.environ['KUBECTL_SMART_CACHE_TTL'])
            except ValueError:
                pass
                
        if 'KUBECTL_SMART_TIMEOUT' in os.environ:
            try:
                self.collector_timeout = float(os.environ['KUBECTL_SMART_TIMEOUT'])
            except ValueError:
                pass


# Type aliases for common use cases
ResourceDict = Dict[str, ResourceRecord]
IssueList = List[Issue]
GraphEdges = List[Dict[str, str]]