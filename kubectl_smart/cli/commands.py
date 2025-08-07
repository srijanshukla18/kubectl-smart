"""
Command implementations for the three core commands

This module implements the business logic for diag, graph, and top commands
as specified in the technical requirements.
"""

import asyncio
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional

import structlog

from ..collectors.base import registry as collector_registry
from ..forecast.predictor import ForecastingEngine
from ..graph.builder import GraphBuilder
from ..models import (
    AnalysisConfig,
    DiagnosisResult,
    GraphResult,
    ResourceRecord,
    SubjectCtx,
    TopResult,
)
from ..parsers.base import registry as parser_registry
from ..renderers.terminal import TerminalRenderer
from ..scoring.engine import ScoringEngine

logger = structlog.get_logger(__name__)


@dataclass
class CommandResult:
    """Result of command execution"""
    output: str
    exit_code: int = 0
    analysis_duration: float = 0.0


class BaseCommand:
    """Base class for all commands"""
    
    def __init__(self, config: Optional[AnalysisConfig] = None):
        self.config = config or AnalysisConfig()
        self.graph_builder = GraphBuilder()
        self.scoring_engine = ScoringEngine()
        self.forecasting_engine = ForecastingEngine(
            forecast_horizon_hours=self.config.forecast_horizon_hours
        )
    
    async def _collect_data(self, subject: SubjectCtx, collector_names: List[str]) -> List[ResourceRecord]:
        """Collect data using multiple collectors concurrently"""
        start_time = time.time()
        
        # Create collectors
        collectors = []
        for name in collector_names:
            try:
                if name == 'describe':
                    collector = collector_registry.create(name, resource_type=subject.kind.value.lower())
                elif name == 'get':
                    collector = collector_registry.create(name, resource_type=subject.kind.value.lower())
                else:
                    collector = collector_registry.create(name)
                collectors.append(collector)
            except Exception as e:
                logger.warning("Failed to create collector", name=name, error=str(e))
        
        # Collect data concurrently
        tasks = [collector.collect(subject) for collector in collectors]
        blobs = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Parse collected data
        all_resources = []
        for i, blob in enumerate(blobs):
            if isinstance(blob, Exception):
                logger.warning("Collector failed", collector=collectors[i].name, error=str(blob))
                continue
            
            try:
                resources = parser_registry.parse(blob)
                all_resources.extend(resources)
            except Exception as e:
                logger.warning("Failed to parse data", collector=collectors[i].name, error=str(e))
        
        collection_time = time.time() - start_time
        logger.debug("Data collection completed", 
                    resources=len(all_resources), 
                    duration=collection_time)
        
        return all_resources
    
    


class DiagCommand(BaseCommand):
    """Implementation of the diag command
    
    As specified in the technical requirements:
    - Collectors invoked: Get, Describe, Events, Logs
    - Output sections: Header, Root Cause, Contributing Factors, Suggested Action
    - Exit codes: 0 = no issues ≥50; 1 = warnings; 2 = critical
    """
    
    async def execute(self, subject: SubjectCtx) -> CommandResult:
        """Execute diagnosis command"""
        start_time = time.time()
        
        try:
            # Collect data using specified collectors
            collector_names = ['get', 'describe', 'events', 'logs']
            all_resources = await self._collect_data(subject, collector_names)
            
            # Build dependency graph
            self.graph_builder.add_resources(all_resources)
            
            # Find target resource
            target_resource = None
            for resource in all_resources:
                if (resource.kind == subject.kind and 
                    resource.name == subject.name and
                    resource.namespace == subject.namespace):
                    target_resource = resource
                    break
            
            if not target_resource:
                # Resource not found
                analysis_duration = time.time() - start_time
                renderer = TerminalRenderer(colors_enabled=self.config.colors_enabled)
                output = renderer.render_error(f"Resource {subject.full_name} not found")
                
                # All errors return exit_code=2
                return CommandResult(output=output, exit_code=2, analysis_duration=analysis_duration)
            
            # Extract events related to this resource
            events = [r for r in all_resources if r.kind.value == "Event"]
            
            # Analyze issues
            issues = self.scoring_engine.analyze_issues(all_resources, events, self.graph_builder)
            
            # Filter issues related to target resource
            target_issues = [
                issue for issue in issues 
                if issue.resource_uid == target_resource.uid
            ]
            
            # Identify root cause and contributing factors
            root_cause = self.scoring_engine.get_root_cause(target_issues)
            contributing_factors = self.scoring_engine.get_contributing_factors(target_issues, root_cause)
            
            # Generate suggested actions
            suggested_actions = self._generate_suggested_actions(target_resource, root_cause, contributing_factors)
            
            analysis_duration = time.time() - start_time
            
            # Create result
            result = DiagnosisResult(
                subject=subject,
                resource=target_resource,
                issues=target_issues,
                root_cause=root_cause,
                contributing_factors=contributing_factors,
                suggested_actions=suggested_actions,
                analysis_duration=analysis_duration,
            )
            
            # Render output
            renderer = TerminalRenderer(colors_enabled=self.config.colors_enabled)
            output = renderer.render_diagnosis(result)
            
            # Determine exit code (0 for success, 2 for any issues)
            exit_code = 0
            if result.critical_issues or result.warning_issues:
                exit_code = 2  # Any issues found, return 2
            
            logger.debug(f"DiagCommand: critical_issues={result.critical_issues}, warning_issues={result.warning_issues}")
            return CommandResult(
                output=output, 
                exit_code=exit_code, 
                analysis_duration=analysis_duration
            )
            
        except BaseException as e:
            if isinstance(e, SystemExit):
                raise  # Re-raise SystemExit to ensure proper exit code propagation
            analysis_duration = time.time() - start_time
            logger.error("Diagnosis command failed", error=str(e))
            
            renderer = TerminalRenderer(colors_enabled=self.config.colors_enabled)
            output = renderer.render_error(f"Diagnosis failed: {e}")
            
            logger.debug(f"DiagCommand returning exit_code=2 due to exception: {e}")
            return CommandResult(output=output, exit_code=2, analysis_duration=analysis_duration)
    
    def _generate_suggested_actions(self, resource: ResourceRecord, root_cause, contributing_factors) -> List[str]:
        """Generate specific suggested actions based on diagnosis"""
        actions = []
        
        # Generic actions based on resource status
        if resource.status in ['Failed', 'Pending', 'Unknown']:
            actions.append(f"Check logs: kubectl logs {resource.name}")
            if resource.namespace:
                actions[-1] += f" -n {resource.namespace}"
        
        # Actions based on root cause
        if root_cause:
            if 'FailedMount' in root_cause.reason:
                actions.append("Check PVC status: kubectl get pvc")
                actions.append("Verify storage class: kubectl get storageclass")
            elif 'FailedScheduling' in root_cause.reason:
                actions.append("Check node resources: kubectl top nodes")
                actions.append("Check pod resource requests vs available capacity")
            elif 'ImagePullBackOff' in root_cause.reason:
                actions.append("Verify image name and tag")
                actions.append("Check image pull secrets if using private registry")
        
        # Actions based on resource type
        if resource.kind.value == "Pod":
            actions.append(f"Get detailed info: kubectl describe pod {resource.name}")
            if resource.namespace:
                actions[-1] += f" -n {resource.namespace}"
        
        return actions[:self.config.max_suggested_actions]


class GraphCommand(BaseCommand):
    """Implementation of the graph command
    
    As specified in the technical requirements:
    - Uses graph built during last diag run in same process; else re-collect minimal data
    - Provides ASCII tree visualization with health indicators
    """
    
    async def execute(self, subject: SubjectCtx, direction: str = "downstream") -> CommandResult:
        """Execute graph command"""
        start_time = time.time()
        
        try:
            # Check if we have an existing graph, otherwise collect minimal data
            if self.graph_builder.graph.vcount() == 0:
                # No existing graph, collect minimal data
                collector_names = ['get', 'describe']
                all_resources = await self._collect_data(subject, collector_names)
                self.graph_builder.add_resources(all_resources)
            
            # Find target resource
            target_uid = None
            target_resource = None
            
            for uid, resource in self.graph_builder.resources.items():
                if (resource.kind == subject.kind and 
                    resource.name == subject.name and
                    resource.namespace == subject.namespace):
                    target_uid = uid
                    target_resource = resource
                    break
            
            if not target_uid:
                analysis_duration = time.time() - start_time
                renderer = TerminalRenderer(colors_enabled=self.config.colors_enabled)
                output = renderer.render_error(f"Resource {subject.full_name} not found in graph")
                
                # All errors return exit_code=2
                return CommandResult(output=output, exit_code=2, analysis_duration=analysis_duration)
            
            # Generate ASCII graph
            ascii_graph = self.graph_builder.to_ascii(target_uid, direction, max_depth=3)
            
            # Get dependencies
            dependencies = self.graph_builder.get_dependencies(target_uid, direction)
            
            # Build edges list
            edges = []
            for dep_uid in dependencies:
                dep_resource = self.graph_builder.resources.get(dep_uid)
                if dep_resource:
                    edges.append({
                        'source': target_resource.full_name,
                        'target': dep_resource.full_name,
                        'type': direction
                    })
            
            analysis_duration = time.time() - start_time
            
            # Create result
            result = GraphResult(
                subject=subject,
                nodes=list(self.graph_builder.resources.values()),
                edges=edges,
                ascii_graph=ascii_graph,
                upstream_count=len(self.graph_builder.get_dependencies(target_uid, "upstream")),
                downstream_count=len(self.graph_builder.get_dependencies(target_uid, "downstream")),
                analysis_duration=analysis_duration,
            )
            
            # Render output
            renderer = TerminalRenderer(colors_enabled=self.config.colors_enabled)
            output = renderer.render_graph(result)
            
            return CommandResult(output=output, exit_code=0, analysis_duration=analysis_duration)
            
        except BaseException as e:
            if isinstance(e, SystemExit):
                raise  # Re-raise SystemExit to ensure proper exit code propagation
            analysis_duration = time.time() - start_time
            logger.error("Graph command failed", error=str(e))
            
            renderer = TerminalRenderer(colors_enabled=self.config.colors_enabled)
            output = renderer.render_error(f"Graph analysis failed: {e}")
                
            logger.debug(f"GraphCommand returning exit_code=2 due to exception: {e}")
            return CommandResult(output=output, exit_code=2, analysis_duration=analysis_duration)


class TopCommand(BaseCommand):
    """Implementation of the top command
    
    As specified in the technical requirements:
    - Pulls kubectl top pods; groups by PVC and Secret expiries
    - Forecast horizon: 48h; list only issues predicted to cross 90% or expire
    """
    
    def __init__(self, forecast_horizon_hours: int = 48, **kwargs):
        super().__init__(**kwargs)
        self.forecast_horizon_hours = forecast_horizon_hours
        self.forecasting_engine = ForecastingEngine(
            forecast_horizon_hours=forecast_horizon_hours
        )
    
    async def execute(self, subject: SubjectCtx) -> CommandResult:
        """Execute top command"""
        start_time = time.time()
        
        try:
            # Collect data for namespace analysis
            collector_names = ['get', 'metrics', 'kubelet']
            all_resources = await self._collect_data(subject, collector_names)
            
            # Filter to namespace resources
            namespace_resources = [
                r for r in all_resources 
                if r.namespace == subject.name or r.kind.value in ['Node', 'PersistentVolume']
            ]
            
            # Get metrics data for forecasting
            metrics_data = [r for r in all_resources if r.properties.get('metrics')]
            
            # Predict capacity issues (nodes + PVCs)
            capacity_warnings = self.forecasting_engine.predict_capacity_issues(
                namespace_resources, metrics_data
            )
            
            # Predict certificate expiry
            certificate_warnings = self.forecasting_engine.predict_certificate_expiry(
                namespace_resources
            )
            
            analysis_duration = time.time() - start_time
            
            # Create result
            result = TopResult(
                subject=subject,
                capacity_warnings=capacity_warnings,
                certificate_warnings=certificate_warnings,
                forecast_horizon_hours=self.forecast_horizon_hours,
                analysis_duration=analysis_duration,
            )
            
            # Render output
            renderer = TerminalRenderer(colors_enabled=self.config.colors_enabled)
            output = renderer.render_top(result)
            
            # Exit code 0 even if warnings exist; top is advisory
            return CommandResult(output=output, exit_code=0, analysis_duration=analysis_duration)
            
        except Exception as e:
            analysis_duration = time.time() - start_time
            logger.error("Top command failed", error=str(e))
            
            renderer = TerminalRenderer(colors_enabled=self.config.colors_enabled)
            output = renderer.render_error(f"Predictive analysis failed: {e}")
                
            # All errors return exit_code=2
            return CommandResult(output=output, exit_code=2, analysis_duration=analysis_duration)