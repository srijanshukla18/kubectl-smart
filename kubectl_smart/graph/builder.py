"""
Graph builder using python-igraph for dependency analysis

This module builds directed graphs of Kubernetes resource dependencies
using python-igraph as specified in the technical requirements.
"""

import warnings
from typing import Dict, List, Optional, Set, Tuple

import structlog
from igraph import Graph

from ..models import ResourceKind, ResourceRecord

logger = structlog.get_logger(__name__)

DEPENDENCY_EDGE_TYPES = {
    "scheduled-on",
    "mounts",
    "uses",
    "binds-to",
    "selects",
    "depends",
    "routes-to",
    "resolves",
}


class GraphBuilder:
    """Builds dependency graphs for Kubernetes resources using python-igraph
    
    As specified in the technical documentation:
    - Vertex key: Kubernetes UID
    - Edge labels: "owns", "mounts", "scheduled-on", "selects"
    - Library: python-igraph (C backend) for speed
    """
    
    def __init__(self):
        self.graph = Graph(directed=True)
        self.resources: Dict[str, ResourceRecord] = {}
        self.uid_to_vertex: Dict[str, int] = {}
        self.vertex_to_uid: Dict[int, str] = {}
        
    def add_resources(self, resources: List[ResourceRecord]) -> None:
        """Add resources to the graph and build dependency relationships"""
        # First pass: add all vertices
        for resource in resources:
            self._add_vertex(resource)
        
        # Second pass: add edges based on relationships
        for resource in resources:
            self._add_relationships(resource)
    
    def _add_vertex(self, resource: ResourceRecord) -> int:
        """Add a vertex for a resource"""
        if resource.uid in self.uid_to_vertex:
            return self.uid_to_vertex[resource.uid]
        
        vertex = self.graph.add_vertex(
            uid=resource.uid,
            name=resource.name,
            kind=resource.kind.value,
            namespace=resource.namespace,
            full_name=resource.full_name,
            status=resource.status,
        )
        vertex_id = vertex.index
        
        self.resources[resource.uid] = resource
        self.uid_to_vertex[resource.uid] = vertex_id
        self.vertex_to_uid[vertex_id] = resource.uid
        
        logger.debug("Added vertex", 
                    uid=resource.uid, 
                    kind=resource.kind.value, 
                    name=resource.name)
        
        return vertex_id
    
    def _add_relationships(self, resource: ResourceRecord) -> None:
        """Add dependency edges for a resource"""
        relationships = self._extract_relationships(resource)
        
        for target_uid, edge_type in relationships:
            if target_uid in self.uid_to_vertex:
                self._add_edge(resource.uid, target_uid, edge_type)
    
    def _extract_relationships(self, resource: ResourceRecord) -> List[Tuple[str, str]]:
        """Extract dependency relationships from a resource
        
        Returns list of (target_uid, edge_type) tuples
        """
        relationships = []
        
        if resource.kind == ResourceKind.POD:
            relationships.extend(self._extract_pod_relationships(resource))
        elif resource.kind == ResourceKind.DEPLOYMENT:
            relationships.extend(self._extract_deployment_relationships(resource))
        elif resource.kind == ResourceKind.REPLICASET:
            relationships.extend(self._extract_replicaset_relationships(resource))
        elif resource.kind == ResourceKind.SERVICE:
            relationships.extend(self._extract_service_relationships(resource))
        elif resource.kind == ResourceKind.INGRESS:
            relationships.extend(self._extract_ingress_relationships(resource))
        elif resource.kind == ResourceKind.PVC:
            relationships.extend(self._extract_pvc_relationships(resource))
        elif resource.kind == ResourceKind.STATEFULSET:
            relationships.extend(self._extract_statefulset_relationships(resource))
        elif resource.kind == ResourceKind.DAEMONSET:
            relationships.extend(self._extract_daemonset_relationships(resource))
        
        return relationships
    
    def _extract_pod_relationships(self, pod: ResourceRecord) -> List[Tuple[str, str]]:
        """Extract Pod dependency relationships"""
        relationships = []
        spec = pod.get_property('spec', {})
        
        # Node relationship
        node_name = spec.get('nodeName')
        if node_name:
            node_uid = self._find_resource_uid(ResourceKind.NODE, node_name)
            if node_uid:
                relationships.append((node_uid, 'scheduled-on'))
        
        # Volume relationships
        volumes = spec.get('volumes', [])
        for volume in volumes:
            # PVC relationships
            if 'persistentVolumeClaim' in volume:
                pvc_name = volume['persistentVolumeClaim']['claimName']
                pvc_uid = self._ensure_resource_uid(ResourceKind.PVC, pvc_name, pod.namespace)
                if pvc_uid:
                    relationships.append((pvc_uid, 'mounts'))
            
            # ConfigMap relationships
            if 'configMap' in volume:
                cm_name = volume['configMap']['name']
                cm_uid = None
                if not volume['configMap'].get('optional', False):
                    cm_uid = self._ensure_resource_uid(ResourceKind.CONFIGMAP, cm_name, pod.namespace)
                else:
                    cm_uid = self._find_resource_uid(ResourceKind.CONFIGMAP, cm_name, pod.namespace)
                if cm_uid:
                    relationships.append((cm_uid, 'mounts'))
            
            # Secret relationships
            if 'secret' in volume:
                secret_name = volume['secret']['secretName']
                secret_uid = None
                if not volume['secret'].get('optional', False):
                    secret_uid = self._ensure_resource_uid(ResourceKind.SECRET, secret_name, pod.namespace)
                else:
                    secret_uid = self._find_resource_uid(ResourceKind.SECRET, secret_name, pod.namespace)
                if secret_uid:
                    relationships.append((secret_uid, 'mounts'))

        # Environment variable references can be just as critical as mounted
        # files: a missing env Secret/ConfigMap prevents containers starting.
        for container in self._pod_containers(spec):
            for env_from in container.get('envFrom', []) or []:
                config_map_ref = env_from.get('configMapRef') or {}
                cm_name = config_map_ref.get('name')
                if cm_name:
                    if config_map_ref.get('optional', False):
                        cm_uid = self._find_resource_uid(ResourceKind.CONFIGMAP, cm_name, pod.namespace)
                    else:
                        cm_uid = self._ensure_resource_uid(ResourceKind.CONFIGMAP, cm_name, pod.namespace)
                    if cm_uid:
                        relationships.append((cm_uid, 'uses'))

                secret_ref = env_from.get('secretRef') or {}
                secret_name = secret_ref.get('name')
                if secret_name:
                    if secret_ref.get('optional', False):
                        secret_uid = self._find_resource_uid(ResourceKind.SECRET, secret_name, pod.namespace)
                    else:
                        secret_uid = self._ensure_resource_uid(ResourceKind.SECRET, secret_name, pod.namespace)
                    if secret_uid:
                        relationships.append((secret_uid, 'uses'))

            for env in container.get('env', []) or []:
                value_from = env.get('valueFrom') or {}
                config_map_key_ref = value_from.get('configMapKeyRef') or {}
                cm_name = config_map_key_ref.get('name')
                if cm_name:
                    if config_map_key_ref.get('optional', False):
                        cm_uid = self._find_resource_uid(ResourceKind.CONFIGMAP, cm_name, pod.namespace)
                    else:
                        cm_uid = self._ensure_resource_uid(ResourceKind.CONFIGMAP, cm_name, pod.namespace)
                    if cm_uid:
                        relationships.append((cm_uid, 'uses'))

                secret_key_ref = value_from.get('secretKeyRef') or {}
                secret_name = secret_key_ref.get('name')
                if secret_name:
                    if secret_key_ref.get('optional', False):
                        secret_uid = self._find_resource_uid(ResourceKind.SECRET, secret_name, pod.namespace)
                    else:
                        secret_uid = self._ensure_resource_uid(ResourceKind.SECRET, secret_name, pod.namespace)
                    if secret_uid:
                        relationships.append((secret_uid, 'uses'))
        
        # ServiceAccount relationship
        service_account = spec.get('serviceAccountName', 'default')
        if service_account:
            sa_uid = self._find_resource_uid(ResourceKind.SERVICEACCOUNT, service_account, pod.namespace)
            if sa_uid:
                relationships.append((sa_uid, 'uses'))
        
        return relationships

    def _pod_containers(self, spec: Dict) -> List[Dict]:
        """Return all container specs that can reference config or secrets."""
        containers = []
        for field in ("initContainers", "containers", "ephemeralContainers"):
            containers.extend(spec.get(field, []) or [])
        return containers
    
    def _extract_deployment_relationships(self, deployment: ResourceRecord) -> List[Tuple[str, str]]:
        """Extract Deployment relationships to ReplicaSets"""
        relationships = []
        
        # Find owned ReplicaSets
        for uid, resource in self.resources.items():
            if (resource.kind == ResourceKind.REPLICASET and 
                resource.namespace == deployment.namespace):
                
                # Check if this ReplicaSet is owned by this Deployment
                owner_refs = resource.get_property('metadata.ownerReferences', [])
                for owner_ref in owner_refs:
                    if (owner_ref.get('kind') == 'Deployment' and 
                        owner_ref.get('uid') == deployment.uid):
                        relationships.append((uid, 'owns'))
        
        return relationships
    
    def _extract_replicaset_relationships(self, replicaset: ResourceRecord) -> List[Tuple[str, str]]:
        """Extract ReplicaSet relationships to Pods"""
        relationships = []
        
        # Find owned Pods
        for uid, resource in self.resources.items():
            if (resource.kind == ResourceKind.POD and 
                resource.namespace == replicaset.namespace):
                
                # Check if this Pod is owned by this ReplicaSet
                owner_refs = resource.get_property('metadata.ownerReferences', [])
                for owner_ref in owner_refs:
                    if (owner_ref.get('kind') == 'ReplicaSet' and 
                        owner_ref.get('uid') == replicaset.uid):
                        relationships.append((uid, 'owns'))
        
        return relationships
    
    def _extract_service_relationships(self, service: ResourceRecord) -> List[Tuple[str, str]]:
        """Extract Service relationships to Pods via selectors"""
        relationships = []
        spec = service.get_property('spec', {})
        selector = spec.get('selector', {})
        
        # Find Pods that match the selector
        if selector:
            for uid, resource in self.resources.items():
                if (resource.kind == ResourceKind.POD and
                    resource.namespace == service.namespace):
                    pod_labels = resource.labels
                    if self._labels_match_selector(pod_labels, selector):
                        relationships.append((uid, 'selects'))

        endpoints_uid = self._find_resource_uid(ResourceKind.ENDPOINTS, service.name, service.namespace)
        if endpoints_uid:
            relationships.append((endpoints_uid, 'resolves'))
        
        return relationships

    def _extract_ingress_relationships(self, ingress: ResourceRecord) -> List[Tuple[str, str]]:
        """Extract Ingress relationships to Services and TLS Secrets."""
        relationships = []
        spec = ingress.get_property('spec', {})

        for tls in spec.get('tls', []) or []:
            secret_name = tls.get('secretName')
            if secret_name:
                secret_uid = self._ensure_resource_uid(ResourceKind.SECRET, secret_name, ingress.namespace)
                if secret_uid:
                    relationships.append((secret_uid, 'uses'))

        default_backend = spec.get('defaultBackend', {}) or {}
        default_service = (default_backend.get('service') or {}).get('name')
        if default_service:
            service_uid = self._ensure_resource_uid(ResourceKind.SERVICE, default_service, ingress.namespace)
            if service_uid:
                relationships.append((service_uid, 'routes-to'))

        for rule in spec.get('rules', []) or []:
            http = rule.get('http') or {}
            for path in http.get('paths', []) or []:
                backend = path.get('backend') or {}
                service_name = (backend.get('service') or {}).get('name')
                if service_name:
                    service_uid = self._ensure_resource_uid(ResourceKind.SERVICE, service_name, ingress.namespace)
                    if service_uid:
                        relationships.append((service_uid, 'routes-to'))

        return relationships
    
    def _extract_pvc_relationships(self, pvc: ResourceRecord) -> List[Tuple[str, str]]:
        """Extract PVC relationships to PV"""
        relationships = []
        spec = pvc.get_property('spec', {})
        status = pvc.get_property('status', {})
        
        # Check if bound to a PV
        volume_name = status.get('volumeName')
        if volume_name:
            pv_uid = self._find_resource_uid(ResourceKind.PV, volume_name)
            if pv_uid:
                relationships.append((pv_uid, 'binds-to'))
        
        return relationships
    
    def _extract_statefulset_relationships(self, sts: ResourceRecord) -> List[Tuple[str, str]]:
        """Extract StatefulSet relationships to Pods"""
        relationships = []
        
        # Find owned Pods (StatefulSet pods have predictable names)
        spec = sts.get_property('spec', {})
        replicas = spec.get('replicas', 0)
        
        for i in range(replicas):
            pod_name = f"{sts.name}-{i}"
            pod_uid = self._find_resource_uid(ResourceKind.POD, pod_name, sts.namespace)
            if pod_uid:
                relationships.append((pod_uid, 'owns'))
        
        return relationships
    
    def _extract_daemonset_relationships(self, ds: ResourceRecord) -> List[Tuple[str, str]]:
        """Extract DaemonSet relationships to Pods"""
        relationships = []
        
        # Find owned Pods
        for uid, resource in self.resources.items():
            if (resource.kind == ResourceKind.POD and 
                resource.namespace == ds.namespace):
                
                owner_refs = resource.get_property('metadata.ownerReferences', [])
                for owner_ref in owner_refs:
                    if (owner_ref.get('kind') == 'DaemonSet' and 
                        owner_ref.get('uid') == ds.uid):
                        relationships.append((uid, 'owns'))
        
        return relationships
    
    def _find_resource_uid(self, kind: ResourceKind, name: str, namespace: Optional[str] = None) -> Optional[str]:
        """Find resource UID by kind, name, and namespace"""
        for uid, resource in self.resources.items():
            if (resource.kind == kind and 
                resource.name == name and 
                resource.namespace == namespace):
                return uid
        return None

    def _ensure_resource_uid(self, kind: ResourceKind, name: str, namespace: Optional[str] = None) -> Optional[str]:
        """Find a resource UID or add a red placeholder for a required missing dependency."""
        if not name:
            return None

        existing_uid = self._find_resource_uid(kind, name, namespace)
        if existing_uid:
            return existing_uid

        namespace_key = namespace or "_cluster"
        missing_uid = f"missing:{kind.value}:{namespace_key}:{name}"
        if missing_uid not in self.resources:
            self._add_vertex(ResourceRecord(
                kind=kind,
                name=name,
                uid=missing_uid,
                namespace=namespace,
                status="Missing",
                properties={"missing": True},
            ))
        return missing_uid
    
    def _labels_match_selector(self, labels: Dict[str, str], selector: Dict[str, str]) -> bool:
        """Check if labels match a selector"""
        for key, value in selector.items():
            if labels.get(key) != value:
                return False
        return True
    
    def _add_edge(self, source_uid: str, target_uid: str, edge_type: str) -> None:
        """Add an edge between two resources"""
        if (source_uid not in self.uid_to_vertex or 
            target_uid not in self.uid_to_vertex):
            return
        
        source_vertex = self.uid_to_vertex[source_uid]
        target_vertex = self.uid_to_vertex[target_uid]
        
        # Check if edge already exists
        edge_id = self.graph.get_eid(source_vertex, target_vertex, error=False)
        if edge_id == -1:
            self.graph.add_edge(source_vertex, target_vertex, type=edge_type)
            logger.debug("Added edge", 
                        source=self.resources[source_uid].full_name,
                        target=self.resources[target_uid].full_name,
                        type=edge_type)
    
    def get_dependencies(self, resource_uid: str, direction: str = "downstream") -> List[str]:
        """Get dependencies of a resource
        
        Args:
            resource_uid: UID of the resource
            direction: "upstream" or "downstream"
            
        Returns:
            List of dependent resource UIDs
        """
        if resource_uid not in self.uid_to_vertex:
            return []
        
        vertex_id = self.uid_to_vertex[resource_uid]
        matches = []

        for edge in self.graph.es:
            edge_type = edge["type"] if "type" in edge.attributes() else ""
            is_dependency_edge = edge_type in DEPENDENCY_EDGE_TYPES

            if direction == "upstream":
                # For dependency edges, source depends on target (Pod -> PVC).
                # For ownership/selection edges, target is affected by source (Service -> Pod).
                if is_dependency_edge and edge.source == vertex_id:
                    matches.append(edge.target)
                elif not is_dependency_edge and edge.target == vertex_id:
                    matches.append(edge.source)
            else:
                # Downstream is the reverse: resources impacted by this resource.
                if is_dependency_edge and edge.target == vertex_id:
                    matches.append(edge.source)
                elif not is_dependency_edge and edge.source == vertex_id:
                    matches.append(edge.target)

        return [self.vertex_to_uid[vid] for vid in matches]
    
    def to_ascii(self, root_uid: str, direction: str = "downstream", max_depth: int = 3) -> str:
        """Generate ASCII tree representation
        
        Args:
            root_uid: Starting resource UID
            direction: "upstream" or "downstream"  
            max_depth: Maximum traversal depth
            
        Returns:
            ASCII tree string
        """
        if root_uid not in self.resources:
            return f"Resource {root_uid} not found"
        
        root_resource = self.resources[root_uid]
        lines = [f"{root_resource.full_name}"]
        
        visited = set()
        # Circuit breaker on graph size to avoid overwhelming output
        try:
            if self.graph.vcount() > 2000 or self.graph.ecount() > 5000:
                return f"Graph too large to render (vertices={self.graph.vcount()}, edges={self.graph.ecount()}). Try narrowing scope."
        except Exception:
            pass
        self._build_ascii_tree(root_uid, direction, lines, "", max_depth, 0, visited)
        
        return '\n'.join(lines)
    
    def _build_ascii_tree(
        self, 
        resource_uid: str, 
        direction: str, 
        lines: List[str], 
        prefix: str, 
        max_depth: int, 
        current_depth: int,
        visited: Set[str]
    ) -> None:
        """Recursively build ASCII tree"""
        if current_depth >= max_depth or resource_uid in visited:
            if resource_uid in visited:
                lines.append(f"{prefix}└─ 🔄 (cycle detected)")
            return
        
        visited.add(resource_uid)
        dependencies = self.get_dependencies(resource_uid, direction)
        
        for i, dep_uid in enumerate(dependencies):
            if dep_uid not in self.resources:
                continue
                
            dep_resource = self.resources[dep_uid]
            is_last = i == len(dependencies) - 1
            
            # Choose connector
            connector = "└─ " if is_last else "├─ "
            
            # Add status indicator
            status_icon = self._get_status_icon(dep_resource.status)
            
            lines.append(f"{prefix}{connector}{status_icon} {dep_resource.full_name}")
            
            # Recurse with updated prefix
            new_prefix = prefix + ("    " if is_last else "│   ")
            self._build_ascii_tree(
                dep_uid, direction, lines, new_prefix, 
                max_depth, current_depth + 1, visited.copy()
            )
    
    def _get_status_icon(self, status: Optional[str]) -> str:
        """Get status icon for resource"""
        icon_map = {
            'Running': '🟢',
            'Active': '🟢',
            'Ready': '🟢',
            'Available': '🟢',
            'Bound': '🟢',
            'Complete': '🟢',
            'Failed': '🔴',
            'Pending': '🟡',
            'Unknown': '🔴',
            'NotReady': '🔴',
            'Unavailable': '🔴',
            'Missing': '🔴',
            'CrashLoopBackOff': '🔴',
            'ImagePullBackOff': '🔴',
            'ErrImagePull': '🔴',
            'CreateContainerConfigError': '🔴',
        }
        return icon_map.get(status, '⚪')
    
    def find_cycles(self) -> List[List[str]]:
        """Find cycles in the dependency graph
        
        Returns:
            List of cycles, where each cycle is a list of resource UIDs
        """
        cycles = []
        
        # Use igraph's built-in cycle detection if available
        if hasattr(self.graph, 'feedback_arc_set'):
            try:
                feedback_edges = self.graph.feedback_arc_set()
                # Convert edge indices to resource paths
                for edge_idx in feedback_edges:
                    edge = self.graph.es[edge_idx]
                    source_uid = self.vertex_to_uid[edge.source]
                    target_uid = self.vertex_to_uid[edge.target]
                    # This is a simplified cycle representation
                    cycles.append([source_uid, target_uid])
            except Exception as e:
                logger.debug("Failed to detect cycles with igraph", error=str(e))
        
        return cycles
    
    def get_shortest_path(self, source_uid: str, target_uid: str) -> List[str]:
        """Get shortest path between two resources
        
        Args:
            source_uid: Source resource UID
            target_uid: Target resource UID
            
        Returns:
            List of resource UIDs in the shortest path
        """
        if (source_uid not in self.uid_to_vertex or 
            target_uid not in self.uid_to_vertex):
            return []
        
        source_vertex = self.uid_to_vertex[source_uid]
        target_vertex = self.uid_to_vertex[target_uid]
        
        try:
            with warnings.catch_warnings():
                warnings.filterwarnings(
                    "ignore",
                    message="Couldn't reach some vertices.*",
                    category=RuntimeWarning,
                )
                path_vertices = self.graph.get_shortest_paths(
                    source_vertex, target_vertex, output="vpath"
                )[0]
            
            return [self.vertex_to_uid[vid] for vid in path_vertices]
        except Exception as e:
            logger.debug("Failed to find shortest path", error=str(e))
            return []
    
    def get_graph_stats(self) -> Dict[str, any]:
        """Get graph statistics"""
        return {
            'vertices': self.graph.vcount(),
            'edges': self.graph.ecount(),
            'density': self.graph.density(),
            'is_dag': self.graph.is_dag(),
            'components': len(self.graph.components()),
        }
