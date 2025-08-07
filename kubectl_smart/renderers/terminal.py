"""
Terminal renderer using rich for output formatting

This module implements the ANSI renderer as specified in the technical requirements,
producing the exact output format described in the product specification.
"""

import json
from typing import Any, Dict, List, Optional

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.tree import Tree

from ..models import (
    DiagnosisResult,
    GraphResult,
    Issue,
    IssueSeverity,
    ResourceRecord,
    TopResult,
)


class TerminalRenderer:
    """ANSI terminal renderer using rich library
    
    As specified in the technical requirements:
    - Uses rich library for professional output
    - No external color themes
    - Honours environment width; wrap lines at 100 chars
    - Produces stable output format
    """
    
    def __init__(self, colors_enabled: bool = True, width: Optional[int] = None):
        self.console = Console(
            color_system="auto" if colors_enabled else None,
            width=width or min(100, Console().size.width),
            legacy_windows=False
        )
        self.colors_enabled = colors_enabled
    
    def render_diagnosis(self, result: DiagnosisResult) -> str:
        """Render diagnosis result as specified in product requirements
        
        Output sections:
        1. Header — object identity
        2. Root Cause — highest-score issue  
        3. Contributing Factors — next 2 issues (if ≥ 50)
        4. Suggested Action — textual; may include kubectl snippet
        """
        console = Console(file=None, width=self.console.size.width)
        
        # Header - object identity
        with console.capture() as capture:
            if result.resource:
                status_style = self._get_status_style(result.resource.status)
                console.print(f"\n📋 DIAGNOSIS: {result.resource.full_name}")
                console.print(f"Status: [{status_style}]{result.resource.status}[/{status_style}]")
            else:
                console.print(f"\n📋 DIAGNOSIS: {result.subject.full_name}")
                console.print("Status: [red]Resource not found[/red]")
            
            # Root Cause - highest-score issue
            if result.root_cause:
                console.print(f"\n🔴 ROOT CAUSE")
                self._render_issue(console, result.root_cause, show_details=True)
            
            # Contributing Factors - next 2 issues (if ≥ 50)
            if result.contributing_factors:
                console.print(f"\n⚠️  CONTRIBUTING FACTORS ({len(result.contributing_factors)})")
                for i, factor in enumerate(result.contributing_factors, 1):
                    console.print(f"  {i}. {factor.title} (score: {factor.score:.1f})")
                    console.print(f"     {factor.description}")
            
            # Suggested Actions
            if result.suggested_actions:
                console.print(f"\n💡 SUGGESTED ACTIONS")
                for i, action in enumerate(result.suggested_actions, 1):
                    console.print(f"  {i}. {action}")
            
            # Performance info
            console.print(f"\n⏱️  Analysis completed in {result.analysis_duration:.2f}s")
        
        return capture.get()
    
    def render_graph(self, result: GraphResult) -> str:    
        """Render graph result with ASCII visualization"""
        console = Console(file=None, width=self.console.size.width)
        
        with console.capture() as capture:
            console.print(f"\n🔗 DEPENDENCY GRAPH: {result.subject.full_name}")
            
            # ASCII graph representation
            if result.ascii_graph:
                console.print()
                for line in result.ascii_graph.split('\n'):
                    console.print(line)
            
            # Summary statistics
            console.print(f"\n📊 GRAPH STATISTICS")
            console.print(f"  Resources: {len(result.nodes)}")
            console.print(f"  Dependencies: {len(result.edges)}")
            console.print(f"  Upstream: {result.upstream_count}")
            console.print(f"  Downstream: {result.downstream_count}")
            
            console.print(f"\n⏱️  Analysis completed in {result.analysis_duration:.2f}s")
        
        return capture.get()
    
    def render_top(self, result: TopResult) -> str:
        """Render top result with predictive outlook
        
        As specified: 48h horizon, list only issues predicted to cross 90% or expire
        """
        console = Console(file=None, width=self.console.size.width)
        
        with console.capture() as capture:
            scope = f"namespace {result.subject.name}" if result.subject.name else "cluster"
            console.print(f"\n📈 PREDICTIVE OUTLOOK: {scope}")
            console.print(f"Forecast horizon: {result.forecast_horizon_hours}h")
            
            # Capacity warnings
            if result.capacity_warnings:
                console.print(f"\n⚠️  CAPACITY WARNINGS ({len(result.capacity_warnings)})")
                table = Table(show_header=True, header_style="bold magenta")
                table.add_column("Resource", style="cyan")
                table.add_column("Type", style="white")
                table.add_column("Current", style="yellow") 
                table.add_column("Predicted", style="red")
                table.add_column("Action", style="green")
                
                for warning in result.capacity_warnings:
                    table.add_row(
                        warning.get('resource', 'Unknown'),
                        warning.get('type', 'Unknown'),
                        f"{warning.get('current_utilization', 0):.1f}%",
                        f"{warning.get('predicted_utilization', 0):.1f}%",
                        warning.get('suggested_action', 'Monitor')
                    )
                
                console.print(table)
            
            # Certificate warnings
            if result.certificate_warnings:
                console.print(f"\n🔒 CERTIFICATE WARNINGS ({len(result.certificate_warnings)})")
                table = Table(show_header=True, header_style="bold magenta")
                table.add_column("Resource", style="cyan")
                table.add_column("Type", style="white")
                table.add_column("Expires", style="red")
                table.add_column("Days Left", style="yellow")
                table.add_column("Action", style="green")
                
                for warning in result.certificate_warnings:
                    table.add_row(
                        warning.get('resource', 'Unknown'),
                        warning.get('certificate_type', 'Unknown'),
                        warning.get('expiry_date', 'Unknown'),
                        str(warning.get('days_until_expiry', 0)),
                        warning.get('suggested_action', 'Renew')
                    )
                
                console.print(table)
            
            # If no warnings
            if not result.capacity_warnings and not result.certificate_warnings:
                console.print("\n✅ No capacity or certificate issues predicted")
            
            console.print(f"\n⏱️  Analysis completed in {result.analysis_duration:.2f}s")
        
        return capture.get()
    
    def render_error(self, error_msg: str, details: Optional[str] = None) -> str:
        """Render error message with optional details"""
        console = Console(file=None, width=self.console.size.width)
        
        with console.capture() as capture:
            console.print(f"[red]❌ Error:[/red] {error_msg}")
            if details:
                console.print(f"[dim]{details}[/dim]")
        
        return capture.get()
    
    def render_rbac_error(self, missing_permissions: List[str]) -> str:
        """Render RBAC permission error with helpful guidance"""
        console = Console(file=None, width=self.console.size.width)
        
        with console.capture() as capture:
            console.print("[red]🔒 RBAC Permission Denied[/red]")
            console.print("\nMissing permissions for:")
            for permission in missing_permissions:
                console.print(f"  • {permission}")
            
            console.print("\n💡 To fix this issue:")
            console.print("  1. Ask your cluster admin for additional permissions")
            console.print("  2. Or run with limited scope: kubectl smart diag pod <name>")
            console.print("  3. Check current permissions: kubectl auth can-i --list")
        
        return capture.get()
    
    def _render_issue(self, console: Console, issue: Issue, show_details: bool = False) -> None:
        """Render a single issue with appropriate styling"""
        severity_style = self._get_severity_style(issue.severity)
        severity_icon = self._get_severity_icon(issue.severity)
        
        console.print(f"  {severity_icon} [{severity_style}]{issue.title}[/{severity_style}] (score: {issue.score:.1f})")
        console.print(f"    {issue.description}")
        
        if issue.critical_path:
            console.print("    [red]🎯 On critical dependency path[/red]")
        
        if show_details and issue.suggested_actions:
            console.print("    [dim]Suggested actions:[/dim]")
            for action in issue.suggested_actions[:3]:  # Limit to top 3
                console.print(f"    [dim]• {action}[/dim]")
    
    def _get_severity_style(self, severity: IssueSeverity) -> str:
        """Get rich style for issue severity"""
        if not self.colors_enabled:
            return "white"
        
        style_map = {
            IssueSeverity.CRITICAL: "red bold",
            IssueSeverity.WARNING: "yellow", 
            IssueSeverity.INFO: "blue",
        }
        return style_map.get(severity, "white")
    
    def _get_severity_icon(self, severity: IssueSeverity) -> str:
        """Get icon for issue severity"""
        icon_map = {
            IssueSeverity.CRITICAL: "🔴",
            IssueSeverity.WARNING: "🟡",
            IssueSeverity.INFO: "🔵",
        }
        return icon_map.get(severity, "⚪")
    
    def _get_status_style(self, status: Optional[str]) -> str:
        """Get rich style for resource status"""
        if not self.colors_enabled or not status:
            return "white"
        
        style_map = {
            'Running': 'green',
            'Active': 'green', 
            'Ready': 'green',
            'Available': 'green',
            'Bound': 'green',
            'Complete': 'green',
            'Failed': 'red',
            'Pending': 'yellow',
            'Unknown': 'red',
            'NotReady': 'red',
            'Unavailable': 'red',
            'Error': 'red',
        }
        return style_map.get(status, 'white')


class JSONRenderer:
    """JSON renderer for structured output and automation
    
    As specified in the technical requirements:
    - Outputs stable schema documented in docs/schema.json
    - Used for automation and API integration
    """
    
    def render_diagnosis(self, result: DiagnosisResult) -> str:
        """Render diagnosis result as JSON"""
        data = {
            "type": "diagnosis",
            "subject": {
                "kind": result.subject.kind.value,
                "name": result.subject.name,
                "namespace": result.subject.namespace,
                "full_name": result.subject.full_name,
            },
            "resource": result.resource.dict() if result.resource else None,
            "root_cause": result.root_cause.dict() if result.root_cause else None,
            "contributing_factors": [f.dict() for f in result.contributing_factors],
            "suggested_actions": result.suggested_actions,
            "analysis_duration": result.analysis_duration,
            "timestamp": result.timestamp.isoformat(),
            "summary": {
                "total_issues": len(result.issues),
                "critical_issues": len(result.critical_issues),
                "warning_issues": len(result.warning_issues),
            }
        }
        
        return json.dumps(data, indent=2, ensure_ascii=False)
    
    def render_graph(self, result: GraphResult) -> str:
        """Render graph result as JSON"""
        data = {
            "type": "graph",
            "subject": {
                "kind": result.subject.kind.value,
                "name": result.subject.name,
                "namespace": result.subject.namespace,
                "full_name": result.subject.full_name,
            },
            "nodes": [node.dict() for node in result.nodes],
            "edges": result.edges,
            "upstream_count": result.upstream_count,
            "downstream_count": result.downstream_count,
            "analysis_duration": result.analysis_duration,
            "timestamp": result.timestamp.isoformat(),
        }
        
        return json.dumps(data, indent=2, ensure_ascii=False)
    
    def render_top(self, result: TopResult) -> str:
        """Render top result as JSON"""
        data = {
            "type": "top",
            "subject": {
                "kind": result.subject.kind.value,
                "name": result.subject.name,
                "namespace": result.subject.namespace,
                "full_name": result.subject.full_name,
            },
            "forecast_horizon_hours": result.forecast_horizon_hours,
            "capacity_warnings": result.capacity_warnings,
            "certificate_warnings": result.certificate_warnings,
            "analysis_duration": result.analysis_duration,
            "timestamp": result.timestamp.isoformat(),
            "summary": {
                "total_capacity_warnings": len(result.capacity_warnings),
                "total_certificate_warnings": len(result.certificate_warnings),
            }
        }
        
        return json.dumps(data, indent=2, ensure_ascii=False)
    
    def render_error(self, error_msg: str, details: Optional[str] = None) -> str:
        """Render error as JSON"""
        data = {
            "type": "error",
            "error": error_msg,
            "details": details,
            "timestamp": DiagnosisResult.timestamp.default_factory().isoformat(),
        }
        
        return json.dumps(data, indent=2, ensure_ascii=False)
    
    def render_rbac_error(self, missing_permissions: List[str]) -> str:
        """Render RBAC error as JSON"""
        data = {
            "type": "rbac_error", 
            "error": "RBAC permission denied",
            "missing_permissions": missing_permissions,
            "suggested_actions": [
                "Request additional permissions from cluster admin",
                "Run with limited scope",
                "Check current permissions with: kubectl auth can-i --list"
            ],
            "timestamp": DiagnosisResult.timestamp.default_factory().isoformat(),
        }
        
        return json.dumps(data, indent=2, ensure_ascii=False)