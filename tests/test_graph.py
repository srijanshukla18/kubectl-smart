"""Tests for kubectl_smart/graph/builder.py"""


from kubectl_smart.graph.builder import GraphBuilder
from kubectl_smart.models import ResourceKind, ResourceRecord


class TestGraphBuilder:
    """Tests for GraphBuilder class"""

    def test_graph_builder_init(self):
        """Test GraphBuilder initialization"""
        builder = GraphBuilder()
        assert builder.graph is not None
        assert builder.graph.is_directed()
        assert builder.resources == {}
        assert builder.uid_to_vertex == {}
        assert builder.vertex_to_uid == {}

    def test_add_vertex(self):
        """Test adding a vertex to the graph"""
        builder = GraphBuilder()
        resource = ResourceRecord(
            kind=ResourceKind.POD,
            name="test-pod",
            uid="pod-uid-123",
            namespace="default",
            status="Running",
        )
        vertex_id = builder._add_vertex(resource)

        assert vertex_id is not None
        assert builder.graph.vcount() == 1
        assert resource.uid in builder.uid_to_vertex
        assert resource.uid in builder.resources

    def test_add_duplicate_vertex(self):
        """Test adding duplicate vertex returns existing ID"""
        builder = GraphBuilder()
        resource = ResourceRecord(
            kind=ResourceKind.POD,
            name="test-pod",
            uid="pod-uid-123",
            namespace="default",
        )
        vertex_id1 = builder._add_vertex(resource)
        vertex_id2 = builder._add_vertex(resource)

        assert vertex_id1 == vertex_id2
        assert builder.graph.vcount() == 1

    def test_add_resources(self):
        """Test adding multiple resources"""
        builder = GraphBuilder()
        resources = [
            ResourceRecord(
                kind=ResourceKind.POD,
                name="pod-1",
                uid="pod-uid-1",
                namespace="default",
            ),
            ResourceRecord(
                kind=ResourceKind.POD,
                name="pod-2",
                uid="pod-uid-2",
                namespace="default",
            ),
        ]
        builder.add_resources(resources)

        assert builder.graph.vcount() == 2
        assert len(builder.resources) == 2

    def test_add_edge(self):
        """Test adding an edge between vertices"""
        builder = GraphBuilder()
        pod = ResourceRecord(
            kind=ResourceKind.POD,
            name="test-pod",
            uid="pod-uid-123",
            namespace="default",
        )
        node = ResourceRecord(
            kind=ResourceKind.NODE,
            name="test-node",
            uid="node-uid-123",
        )
        builder._add_vertex(pod)
        builder._add_vertex(node)
        builder._add_edge(pod.uid, node.uid, "scheduled-on")

        assert builder.graph.ecount() == 1

    def test_add_duplicate_edge(self):
        """Test adding duplicate edge doesn't create new edge"""
        builder = GraphBuilder()
        pod = ResourceRecord(
            kind=ResourceKind.POD,
            name="test-pod",
            uid="pod-uid-123",
            namespace="default",
        )
        node = ResourceRecord(
            kind=ResourceKind.NODE,
            name="test-node",
            uid="node-uid-123",
        )
        builder._add_vertex(pod)
        builder._add_vertex(node)
        builder._add_edge(pod.uid, node.uid, "scheduled-on")
        builder._add_edge(pod.uid, node.uid, "scheduled-on")

        assert builder.graph.ecount() == 1

    def test_add_edge_missing_vertex(self):
        """Test adding edge with missing vertex does nothing"""
        builder = GraphBuilder()
        pod = ResourceRecord(
            kind=ResourceKind.POD,
            name="test-pod",
            uid="pod-uid-123",
            namespace="default",
        )
        builder._add_vertex(pod)
        builder._add_edge(pod.uid, "nonexistent-uid", "test")

        assert builder.graph.ecount() == 0


class TestGraphBuilderRelationships:
    """Tests for relationship extraction"""

    def test_extract_pod_node_relationship(self):
        """Test Pod scheduled-on Node relationship"""
        builder = GraphBuilder()
        node = ResourceRecord(
            kind=ResourceKind.NODE,
            name="worker-1",
            uid="node-uid-123",
        )
        pod = ResourceRecord(
            kind=ResourceKind.POD,
            name="test-pod",
            uid="pod-uid-123",
            namespace="default",
            properties={"spec": {"nodeName": "worker-1"}},
        )
        builder.add_resources([node, pod])

        deps = builder.get_dependencies(pod.uid, "upstream")
        # Node should be in upstream dependencies
        assert node.uid in deps

    def test_extract_pod_pvc_relationship(self):
        """Test Pod mounts PVC relationship"""
        builder = GraphBuilder()
        pvc = ResourceRecord(
            kind=ResourceKind.PVC,
            name="data-pvc",
            uid="pvc-uid-123",
            namespace="default",
        )
        pod = ResourceRecord(
            kind=ResourceKind.POD,
            name="test-pod",
            uid="pod-uid-123",
            namespace="default",
            properties={
                "spec": {
                    "volumes": [
                        {"name": "data", "persistentVolumeClaim": {"claimName": "data-pvc"}}
                    ]
                }
            },
        )
        builder.add_resources([pvc, pod])

        deps = builder.get_dependencies(pod.uid, "upstream")
        assert pvc.uid in deps

    def test_extract_pod_configmap_relationship(self):
        """Test Pod mounts ConfigMap relationship"""
        builder = GraphBuilder()
        cm = ResourceRecord(
            kind=ResourceKind.CONFIGMAP,
            name="app-config",
            uid="cm-uid-123",
            namespace="default",
        )
        pod = ResourceRecord(
            kind=ResourceKind.POD,
            name="test-pod",
            uid="pod-uid-123",
            namespace="default",
            properties={
                "spec": {
                    "volumes": [{"name": "config", "configMap": {"name": "app-config"}}]
                }
            },
        )
        builder.add_resources([cm, pod])

        deps = builder.get_dependencies(pod.uid, "upstream")
        assert cm.uid in deps

    def test_extract_pod_secret_relationship(self):
        """Test Pod mounts Secret relationship"""
        builder = GraphBuilder()
        secret = ResourceRecord(
            kind=ResourceKind.SECRET,
            name="tls-secret",
            uid="secret-uid-123",
            namespace="default",
        )
        pod = ResourceRecord(
            kind=ResourceKind.POD,
            name="test-pod",
            uid="pod-uid-123",
            namespace="default",
            properties={
                "spec": {
                    "volumes": [{"name": "tls", "secret": {"secretName": "tls-secret"}}]
                }
            },
        )
        builder.add_resources([secret, pod])

        deps = builder.get_dependencies(pod.uid, "upstream")
        assert secret.uid in deps

    def test_extract_pod_serviceaccount_relationship(self):
        """Test Pod uses ServiceAccount relationship"""
        builder = GraphBuilder()
        sa = ResourceRecord(
            kind=ResourceKind.SERVICEACCOUNT,
            name="my-sa",
            uid="sa-uid-123",
            namespace="default",
        )
        pod = ResourceRecord(
            kind=ResourceKind.POD,
            name="test-pod",
            uid="pod-uid-123",
            namespace="default",
            properties={"spec": {"serviceAccountName": "my-sa"}},
        )
        builder.add_resources([sa, pod])

        deps = builder.get_dependencies(pod.uid, "upstream")
        assert sa.uid in deps

    def test_extract_pod_env_config_and_secret_relationships(self):
        """Test Pod env/envFrom references to ConfigMaps and Secrets."""
        builder = GraphBuilder()
        cm = ResourceRecord(
            kind=ResourceKind.CONFIGMAP,
            name="app-config",
            uid="cm-uid-123",
            namespace="default",
        )
        secret = ResourceRecord(
            kind=ResourceKind.SECRET,
            name="runtime-secret",
            uid="secret-uid-123",
            namespace="default",
        )
        pod = ResourceRecord(
            kind=ResourceKind.POD,
            name="test-pod",
            uid="pod-uid-123",
            namespace="default",
            properties={
                "spec": {
                    "containers": [
                        {
                            "name": "app",
                            "envFrom": [
                                {"configMapRef": {"name": "app-config"}},
                            ],
                            "env": [
                                {
                                    "name": "TOKEN",
                                    "valueFrom": {
                                        "secretKeyRef": {
                                            "name": "runtime-secret",
                                            "key": "token",
                                        }
                                    },
                                }
                            ],
                        }
                    ]
                }
            },
        )
        builder.add_resources([cm, secret, pod])

        deps = builder.get_dependencies(pod.uid, "upstream")
        assert cm.uid in deps
        assert secret.uid in deps

    def test_extract_pod_missing_required_env_secret_relationship(self):
        """Test missing required env Secrets are visible as red dependency nodes."""
        builder = GraphBuilder()
        pod = ResourceRecord(
            kind=ResourceKind.POD,
            name="test-pod",
            uid="pod-uid-123",
            namespace="default",
            properties={
                "spec": {
                    "containers": [
                        {
                            "name": "app",
                            "env": [
                                {
                                    "name": "TOKEN",
                                    "valueFrom": {
                                        "secretKeyRef": {
                                            "name": "runtime-secret",
                                            "key": "token",
                                        }
                                    },
                                }
                            ],
                        }
                    ]
                }
            },
        )
        builder.add_resources([pod])

        deps = builder.get_dependencies(pod.uid, "upstream")
        assert len(deps) == 1
        missing = builder.resources[deps[0]]
        assert missing.kind == ResourceKind.SECRET
        assert missing.name == "runtime-secret"
        assert missing.status == "Missing"
        assert missing.properties["missing"] is True
        assert "🔴 Secret/default/runtime-secret" in builder.to_ascii(pod.uid, "upstream")

    def test_extract_pod_optional_missing_env_secret_not_added(self):
        """Test optional missing env Secrets do not produce false red nodes."""
        builder = GraphBuilder()
        pod = ResourceRecord(
            kind=ResourceKind.POD,
            name="test-pod",
            uid="pod-uid-123",
            namespace="default",
            properties={
                "spec": {
                    "containers": [
                        {
                            "name": "app",
                            "envFrom": [
                                {
                                    "secretRef": {
                                        "name": "optional-secret",
                                        "optional": True,
                                    }
                                }
                            ],
                        }
                    ]
                }
            },
        )
        builder.add_resources([pod])

        assert builder.get_dependencies(pod.uid, "upstream") == []

    def test_extract_deployment_replicaset_relationship(self):
        """Test Deployment owns ReplicaSet relationship"""
        builder = GraphBuilder()
        deployment = ResourceRecord(
            kind=ResourceKind.DEPLOYMENT,
            name="my-deploy",
            uid="deploy-uid-123",
            namespace="default",
        )
        rs = ResourceRecord(
            kind=ResourceKind.REPLICASET,
            name="my-deploy-abc123",
            uid="rs-uid-123",
            namespace="default",
            properties={
                "metadata": {
                    "ownerReferences": [
                        {"kind": "Deployment", "uid": "deploy-uid-123"}
                    ]
                }
            },
        )
        builder.add_resources([deployment, rs])

        deps = builder.get_dependencies(deployment.uid, "downstream")
        assert rs.uid in deps

    def test_extract_replicaset_pod_relationship(self):
        """Test ReplicaSet owns Pod relationship"""
        builder = GraphBuilder()
        rs = ResourceRecord(
            kind=ResourceKind.REPLICASET,
            name="my-rs",
            uid="rs-uid-123",
            namespace="default",
        )
        pod = ResourceRecord(
            kind=ResourceKind.POD,
            name="my-pod",
            uid="pod-uid-123",
            namespace="default",
            properties={
                "metadata": {
                    "ownerReferences": [{"kind": "ReplicaSet", "uid": "rs-uid-123"}]
                }
            },
        )
        builder.add_resources([rs, pod])

        deps = builder.get_dependencies(rs.uid, "downstream")
        assert pod.uid in deps

    def test_extract_service_pod_relationship(self):
        """Test Service selects Pod relationship"""
        builder = GraphBuilder()
        pod = ResourceRecord(
            kind=ResourceKind.POD,
            name="my-pod",
            uid="pod-uid-123",
            namespace="default",
            labels={"app": "myapp"},
        )
        svc = ResourceRecord(
            kind=ResourceKind.SERVICE,
            name="my-svc",
            uid="svc-uid-123",
            namespace="default",
            properties={"spec": {"selector": {"app": "myapp"}}},
        )
        builder.add_resources([pod, svc])

        deps = builder.get_dependencies(svc.uid, "upstream")
        assert pod.uid in deps

        pod_dependents = builder.get_dependencies(pod.uid, "downstream")
        assert svc.uid in pod_dependents

    def test_extract_service_endpoints_relationship(self):
        """Test Service resolves through an Endpoints object."""
        builder = GraphBuilder()
        svc = ResourceRecord(
            kind=ResourceKind.SERVICE,
            name="api",
            uid="svc-uid-123",
            namespace="default",
            properties={"spec": {"selector": {"app": "api"}}},
        )
        endpoints = ResourceRecord(
            kind=ResourceKind.ENDPOINTS,
            name="api",
            uid="endpoints-uid-123",
            namespace="default",
            status="Unavailable",
        )
        builder.add_resources([svc, endpoints])

        deps = builder.get_dependencies(svc.uid, "upstream")
        assert endpoints.uid in deps

        dependents = builder.get_dependencies(endpoints.uid, "downstream")
        assert svc.uid in dependents

    def test_extract_ingress_service_and_tls_relationships(self):
        """Test Ingress routes to Services and uses TLS Secrets."""
        builder = GraphBuilder()
        service = ResourceRecord(
            kind=ResourceKind.SERVICE,
            name="checkout",
            uid="svc-uid-123",
            namespace="default",
        )
        secret = ResourceRecord(
            kind=ResourceKind.SECRET,
            name="checkout-tls",
            uid="secret-uid-123",
            namespace="default",
        )
        ingress = ResourceRecord(
            kind=ResourceKind.INGRESS,
            name="checkout",
            uid="ingress-uid-123",
            namespace="default",
            properties={
                "spec": {
                    "tls": [{"secretName": "checkout-tls"}],
                    "rules": [
                        {
                            "http": {
                                "paths": [
                                    {
                                        "backend": {
                                            "service": {
                                                "name": "checkout",
                                                "port": {"number": 80},
                                            }
                                        }
                                    }
                                ]
                            }
                        }
                    ],
                }
            },
        )
        builder.add_resources([service, secret, ingress])

        deps = builder.get_dependencies(ingress.uid, "upstream")
        assert service.uid in deps
        assert secret.uid in deps

    def test_extract_ingress_missing_backend_service_relationship(self):
        """Test missing Ingress backend Services are visible as red dependency nodes."""
        builder = GraphBuilder()
        ingress = ResourceRecord(
            kind=ResourceKind.INGRESS,
            name="checkout",
            uid="ingress-uid-123",
            namespace="default",
            properties={
                "spec": {
                    "rules": [
                        {
                            "http": {
                                "paths": [
                                    {
                                        "backend": {
                                            "service": {
                                                "name": "missing-checkout",
                                                "port": {"number": 80},
                                            }
                                        }
                                    }
                                ]
                            }
                        }
                    ]
                }
            },
        )
        builder.add_resources([ingress])

        deps = builder.get_dependencies(ingress.uid, "upstream")
        assert len(deps) == 1
        missing = builder.resources[deps[0]]
        assert missing.kind == ResourceKind.SERVICE
        assert missing.name == "missing-checkout"
        assert missing.status == "Missing"

    def test_extract_pvc_pv_relationship(self):
        """Test PVC binds-to PV relationship"""
        builder = GraphBuilder()
        pv = ResourceRecord(
            kind=ResourceKind.PV,
            name="pv-1",
            uid="pv-uid-123",
        )
        pvc = ResourceRecord(
            kind=ResourceKind.PVC,
            name="my-pvc",
            uid="pvc-uid-123",
            namespace="default",
            properties={"status": {"volumeName": "pv-1"}},
        )
        builder.add_resources([pv, pvc])

        deps = builder.get_dependencies(pvc.uid, "upstream")
        assert pv.uid in deps

    def test_extract_statefulset_pod_relationship(self):
        """Test StatefulSet owns Pod relationship"""
        builder = GraphBuilder()
        sts = ResourceRecord(
            kind=ResourceKind.STATEFULSET,
            name="my-sts",
            uid="sts-uid-123",
            namespace="default",
            properties={"spec": {"replicas": 2}},
        )
        pod0 = ResourceRecord(
            kind=ResourceKind.POD,
            name="my-sts-0",
            uid="pod-uid-0",
            namespace="default",
        )
        pod1 = ResourceRecord(
            kind=ResourceKind.POD,
            name="my-sts-1",
            uid="pod-uid-1",
            namespace="default",
        )
        builder.add_resources([sts, pod0, pod1])

        deps = builder.get_dependencies(sts.uid, "downstream")
        assert pod0.uid in deps
        assert pod1.uid in deps

    def test_extract_daemonset_pod_relationship(self):
        """Test DaemonSet owns Pod relationship"""
        builder = GraphBuilder()
        ds = ResourceRecord(
            kind=ResourceKind.DAEMONSET,
            name="my-ds",
            uid="ds-uid-123",
            namespace="default",
        )
        pod = ResourceRecord(
            kind=ResourceKind.POD,
            name="my-ds-abc",
            uid="pod-uid-123",
            namespace="default",
            properties={
                "metadata": {
                    "ownerReferences": [{"kind": "DaemonSet", "uid": "ds-uid-123"}]
                }
            },
        )
        builder.add_resources([ds, pod])

        deps = builder.get_dependencies(ds.uid, "downstream")
        assert pod.uid in deps


class TestGraphBuilderMethods:
    """Tests for GraphBuilder utility methods"""

    def test_find_resource_uid(self):
        """Test _find_resource_uid finds resources correctly"""
        builder = GraphBuilder()
        resource = ResourceRecord(
            kind=ResourceKind.POD,
            name="my-pod",
            uid="pod-uid-123",
            namespace="default",
        )
        builder.add_resources([resource])

        found_uid = builder._find_resource_uid(
            ResourceKind.POD, "my-pod", "default"
        )
        assert found_uid == "pod-uid-123"

    def test_find_resource_uid_not_found(self):
        """Test _find_resource_uid returns None for missing resource"""
        builder = GraphBuilder()
        found_uid = builder._find_resource_uid(
            ResourceKind.POD, "nonexistent", "default"
        )
        assert found_uid is None

    def test_labels_match_selector_full_match(self):
        """Test _labels_match_selector with full match"""
        builder = GraphBuilder()
        labels = {"app": "myapp", "env": "prod"}
        selector = {"app": "myapp"}
        assert builder._labels_match_selector(labels, selector) is True

    def test_labels_match_selector_no_match(self):
        """Test _labels_match_selector with no match"""
        builder = GraphBuilder()
        labels = {"app": "otherapp"}
        selector = {"app": "myapp"}
        assert builder._labels_match_selector(labels, selector) is False

    def test_labels_match_selector_empty_selector(self):
        """Test _labels_match_selector with empty selector"""
        builder = GraphBuilder()
        labels = {"app": "myapp"}
        selector = {}
        assert builder._labels_match_selector(labels, selector) is True

    def test_get_dependencies_upstream(self):
        """Test get_dependencies with upstream direction"""
        builder = GraphBuilder()
        pod = ResourceRecord(
            kind=ResourceKind.POD,
            name="test-pod",
            uid="pod-uid-123",
            namespace="default",
        )
        node = ResourceRecord(
            kind=ResourceKind.NODE,
            name="test-node",
            uid="node-uid-123",
        )
        builder._add_vertex(pod)
        builder._add_vertex(node)
        builder._add_edge(pod.uid, node.uid, "scheduled-on")

        upstream = builder.get_dependencies(pod.uid, "upstream")
        assert node.uid in upstream

        downstream = builder.get_dependencies(node.uid, "downstream")
        assert pod.uid in downstream

    def test_get_dependencies_nonexistent_uid(self):
        """Test get_dependencies with nonexistent UID returns empty"""
        builder = GraphBuilder()
        deps = builder.get_dependencies("nonexistent-uid", "downstream")
        assert deps == []


class TestGraphBuilderAscii:
    """Tests for ASCII tree generation"""

    def test_to_ascii_simple(self):
        """Test to_ascii generates output"""
        builder = GraphBuilder()
        resource = ResourceRecord(
            kind=ResourceKind.POD,
            name="test-pod",
            uid="pod-uid-123",
            namespace="default",
            status="Running",
        )
        builder.add_resources([resource])

        ascii_output = builder.to_ascii(resource.uid)
        assert "Pod/default/test-pod" in ascii_output

    def test_to_ascii_nonexistent_resource(self):
        """Test to_ascii with nonexistent resource returns error"""
        builder = GraphBuilder()
        ascii_output = builder.to_ascii("nonexistent-uid")
        assert "not found" in ascii_output

    def test_to_ascii_with_dependencies(self):
        """Test to_ascii shows dependencies"""
        builder = GraphBuilder()
        pod = ResourceRecord(
            kind=ResourceKind.POD,
            name="test-pod",
            uid="pod-uid-123",
            namespace="default",
            status="Running",
            properties={"spec": {"nodeName": "worker-1"}},
        )
        node = ResourceRecord(
            kind=ResourceKind.NODE,
            name="worker-1",
            uid="node-uid-123",
            status="Ready",
        )
        builder.add_resources([pod, node])

        ascii_output = builder.to_ascii(pod.uid, direction="downstream")
        assert "Pod/default/test-pod" in ascii_output

    def test_get_status_icon(self):
        """Test _get_status_icon returns correct icons"""
        builder = GraphBuilder()
        assert builder._get_status_icon("Running") == "🟢"
        assert builder._get_status_icon("Active") == "🟢"
        assert builder._get_status_icon("Ready") == "🟢"
        assert builder._get_status_icon("Failed") == "🔴"
        assert builder._get_status_icon("Pending") == "🟡"
        assert builder._get_status_icon("Unknown") == "🔴"
        assert builder._get_status_icon(None) == "⚪"
        assert builder._get_status_icon("SomeOther") == "⚪"


class TestGraphBuilderAnalysis:
    """Tests for graph analysis methods"""

    def test_find_cycles_empty_graph(self):
        """Test find_cycles on empty graph"""
        builder = GraphBuilder()
        cycles = builder.find_cycles()
        assert cycles == []

    def test_find_cycles_dag(self):
        """Test find_cycles on DAG returns empty"""
        builder = GraphBuilder()
        pod = ResourceRecord(
            kind=ResourceKind.POD,
            name="pod",
            uid="pod-uid",
            namespace="default",
        )
        node = ResourceRecord(
            kind=ResourceKind.NODE,
            name="node",
            uid="node-uid",
        )
        builder._add_vertex(pod)
        builder._add_vertex(node)
        builder._add_edge(pod.uid, node.uid, "scheduled-on")

        cycles = builder.find_cycles()
        assert cycles == []

    def test_get_shortest_path(self):
        """Test get_shortest_path finds path"""
        builder = GraphBuilder()
        a = ResourceRecord(kind=ResourceKind.POD, name="a", uid="a-uid", namespace="default")
        b = ResourceRecord(kind=ResourceKind.POD, name="b", uid="b-uid", namespace="default")
        c = ResourceRecord(kind=ResourceKind.POD, name="c", uid="c-uid", namespace="default")

        builder._add_vertex(a)
        builder._add_vertex(b)
        builder._add_vertex(c)
        builder._add_edge(a.uid, b.uid, "depends")
        builder._add_edge(b.uid, c.uid, "depends")

        path = builder.get_shortest_path(a.uid, c.uid)
        assert len(path) == 3
        assert path[0] == a.uid
        assert path[-1] == c.uid

    def test_get_shortest_path_no_path(self):
        """Test get_shortest_path returns empty when no path exists"""
        builder = GraphBuilder()
        a = ResourceRecord(kind=ResourceKind.POD, name="a", uid="a-uid", namespace="default")
        b = ResourceRecord(kind=ResourceKind.POD, name="b", uid="b-uid", namespace="default")

        builder._add_vertex(a)
        builder._add_vertex(b)
        # No edge between them

        path = builder.get_shortest_path(a.uid, b.uid)
        assert path == []

    def test_get_shortest_path_nonexistent_uid(self):
        """Test get_shortest_path with nonexistent UID returns empty"""
        builder = GraphBuilder()
        path = builder.get_shortest_path("nonexistent1", "nonexistent2")
        assert path == []

    def test_get_graph_stats(self):
        """Test get_graph_stats returns correct statistics"""
        builder = GraphBuilder()
        a = ResourceRecord(kind=ResourceKind.POD, name="a", uid="a-uid", namespace="default")
        b = ResourceRecord(kind=ResourceKind.POD, name="b", uid="b-uid", namespace="default")

        builder._add_vertex(a)
        builder._add_vertex(b)
        builder._add_edge(a.uid, b.uid, "depends")

        stats = builder.get_graph_stats()
        assert stats["vertices"] == 2
        assert stats["edges"] == 1
        assert "density" in stats
        assert "is_dag" in stats
        assert "components" in stats

    def test_get_graph_stats_empty_graph(self):
        """Test get_graph_stats on empty graph"""
        builder = GraphBuilder()
        stats = builder.get_graph_stats()
        assert stats["vertices"] == 0
        assert stats["edges"] == 0
