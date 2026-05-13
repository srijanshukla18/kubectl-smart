"""
CLI front-end using Typer framework

This module implements the exact three commands specified in the technical requirements:
- diag: root-cause analysis of a single workload
- graph: dependency visualization (ASCII)  
- top: predictive capacity and certificate outlook
"""

import asyncio
import logging
import sys
from enum import Enum
from typing import Optional

import structlog
import typer
from typing_extensions import Annotated

import re

# Lazy imports to speed up --help

def _configure_logging(debug: bool = False):
    """Configure structured logging lazily.

    Normal CLI output should stay clean; diagnostics are printed intentionally by
    renderers. Internal collector/parser logs are only emitted with --debug.
    """
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stderr,
        level=logging.DEBUG if debug else logging.CRITICAL,
        force=True,
    )
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer()
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

# Create the main Typer app
app = typer.Typer(
    name="kubectl-smart",
    help="Intelligent kubectl plugin for Kubernetes debugging",
    add_completion=False,
    rich_markup_mode="rich",
    context_settings={"help_option_names": ["-h", "--help"]},
)


class ResourceType(str, Enum):
    """Supported resource types for diag and graph commands"""
    POD = "pod"
    DEPLOYMENT = "deploy"
    DEPLOYMENT_FULL = "deployment"
    STATEFULSET = "sts" 
    STATEFULSET_FULL = "statefulset"
    JOB = "job"
    SERVICE = "svc"
    SERVICE_FULL = "service"
    INGRESS = "ingress"
    REPLICASET = "rs"
    REPLICASET_FULL = "replicaset"
    DAEMONSET = "ds"
    DAEMONSET_FULL = "daemonset"


NAME_PATTERN = re.compile(r"^[a-z0-9]([-a-z0-9]*[a-z0-9])?$")
CONTEXT_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+$")


def _validate_namespace(namespace: Optional[str]) -> None:
    if namespace is None:
        return
    if len(namespace) > 63 or not NAME_PATTERN.fullmatch(namespace):
        raise typer.BadParameter("Namespace must match DNS-1123 label (lowercase alphanumerics plus '-') and be ≤63 chars.")


def _validate_resource_name(name: str) -> None:
    if len(name) > 253 or not NAME_PATTERN.fullmatch(name.split('.')[0]):
        # Allow for pod.template hash with dots by checking prefix, but still guard obvious bad input
        raise typer.BadParameter("Resource name must match Kubernetes DNS-1123 label (lowercase alphanumerics plus '-').")


def _validate_context(context: Optional[str]) -> None:
    if context is None:
        return
    if not CONTEXT_PATTERN.fullmatch(context):
        raise typer.BadParameter("Context may only contain letters, numbers, underscore, dot, or dash.")


def _resolve_context(context: Optional[str]) -> Optional[str]:
    """Use an explicit context, or a demo/test default from the environment."""
    if context:
        return context

    import os

    return os.getenv("KUBECTL_SMART_CONTEXT") or None



def version_callback(value: bool):
    """Show version and exit"""
    if value:
        from kubectl_smart import __version__

        typer.echo(f"kubectl-smart v{__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: Annotated[Optional[bool], typer.Option("--version", callback=version_callback, help="Show version and exit")] = None,
    debug: Annotated[bool, typer.Option("--debug", help="Enable debug logging")] = False,
    
):
    """
    kubectl-smart: Intelligent kubectl plugin for Kubernetes debugging
    
    [bold]Core Commands (Bare-bones Power Trio):[/bold]
    • [cyan]diag[/cyan]  - Root-cause analysis of workloads  
    • [cyan]graph[/cyan] - Dependency visualization (ASCII)
    • [cyan]top[/cyan]   - Predictive capacity & certificate outlook
    
    [bold]Performance:[/bold] ≤3s on 2k-resource clusters | Read-only operations
    """
    # Configure logging when actually needed
    _configure_logging(debug=debug)
    
    if debug:
        # Also set environment variable for other components
        import os
        os.environ['KUBECTL_SMART_DEBUG'] = '1'
    
    


@app.command()
def diag(
    resource_type: Annotated[ResourceType, typer.Argument(help="Resource type (pod, deploy, sts, job)")],
    name: Annotated[Optional[str], typer.Argument(help="Resource name (or use --all)")] = None,
    namespace: Annotated[Optional[str], typer.Option("--namespace", "-n", help="Namespace")] = None,
    context: Annotated[Optional[str], typer.Option("--context", help="kubectl context")] = None,
    output: Annotated[str, typer.Option("--output", "-o", help="Output format (text, json)")] = "text",
    watch: Annotated[bool, typer.Option("--watch", "-w", help="Watch for changes and re-run diagnosis")] = False,
    all_resources: Annotated[bool, typer.Option("--all", help="Diagnose all resources of this type")] = False,
    interval: Annotated[int, typer.Option("--interval", help="Watch interval in seconds")] = 5,
):
    """
    🎯 Root-cause analysis of workloads

    [bold]Purpose:[/bold] One-shot diagnosis that surfaces root cause and top contributing factors

    [bold]Output Sections:[/bold]
    1. Header — object identity & status
    2. Root Cause — highest-score issue
    3. Contributing Factors — next 2 issues (if ≥50 score)
    4. Suggested Action — kubectl snippets & guidance

    [bold]Exit Codes:[/bold] 0=no issues ≥50 | 1=warnings | 2=critical

    [bold]Examples:[/bold]
      kubectl-smart diag pod failing-pod
      kubectl-smart diag deploy my-app -n production
      kubectl-smart diag pod failing-pod -o json        # JSON output
      kubectl-smart diag pod failing-pod --watch        # Continuous monitoring
      kubectl-smart diag pod --all -n production        # Diagnose all pods
    """
    # Validate inputs
    if not name and not all_resources:
        typer.echo("Error: Either resource name or --all flag must be provided", err=True)
        raise typer.Exit(2)
    if name and all_resources:
        typer.echo("Error: Cannot use both resource name and --all flag", err=True)
        raise typer.Exit(2)
    if output not in ('text', 'json'):
        typer.echo(f"Error: Invalid output format '{output}'. Valid options: text, json", err=True)
        raise typer.Exit(2)
    if interval < 1:
        typer.echo("Error: Watch interval must be >= 1 second", err=True)
        raise typer.Exit(2)

    if name is not None:
        _validate_resource_name(name)  # type: ignore[arg-type]
    _validate_namespace(namespace)
    context = _resolve_context(context)
    _validate_context(context)

    # Lazy import models
    from ..models import ResourceKind, SubjectCtx

    # Map resource type to ResourceKind
    kind_map = {
        ResourceType.POD: ResourceKind.POD,
        ResourceType.DEPLOYMENT: ResourceKind.DEPLOYMENT,
        ResourceType.DEPLOYMENT_FULL: ResourceKind.DEPLOYMENT,
        ResourceType.STATEFULSET: ResourceKind.STATEFULSET,
        ResourceType.STATEFULSET_FULL: ResourceKind.STATEFULSET,
        ResourceType.JOB: ResourceKind.JOB,
        ResourceType.SERVICE: ResourceKind.SERVICE,
        ResourceType.SERVICE_FULL: ResourceKind.SERVICE,
        ResourceType.INGRESS: ResourceKind.INGRESS,
        ResourceType.REPLICASET: ResourceKind.REPLICASET,
        ResourceType.REPLICASET_FULL: ResourceKind.REPLICASET,
        ResourceType.DAEMONSET: ResourceKind.DAEMONSET,
        ResourceType.DAEMONSET_FULL: ResourceKind.DAEMONSET,
    }

    # Handle batch mode (--all)
    if all_resources:
        from ..batch import BatchAnalyzer
        from ..renderers.json_renderer import JsonRenderer

        analyzer = BatchAnalyzer()
        kind = kind_map[resource_type]

        try:
            batch_result = asyncio.run(analyzer.diagnose_all(
                kind=kind,
                namespace=namespace,
                context=context,
            ))

            if output == "json":
                renderer = JsonRenderer(pretty=True)
                typer.echo(renderer.render_batch(
                    batch_result.results,
                    {
                        "total": batch_result.total_resources,
                        "successful": batch_result.successful,
                        "failed": batch_result.failed,
                        "duration": batch_result.duration,
                        "errors": batch_result.errors,
                    }
                ))
            else:
                # Text output for batch
                typer.echo(f"\n📋 BATCH DIAGNOSIS: {resource_type.value}s")
                if namespace:
                    typer.echo(f"Namespace: {namespace}")
                typer.echo(f"Total: {batch_result.total_resources} | "
                          f"Analyzed: {batch_result.successful} | "
                          f"Failed: {batch_result.failed}")
                typer.echo("=" * 60)

                for result in batch_result.results:
                    status = result.resource.status if result.resource else "Unknown"
                    issues_str = ""
                    if result.critical_issues:
                        issues_str = f"🔴 {len(result.critical_issues)} critical"
                    elif result.warning_issues:
                        issues_str = f"🟡 {len(result.warning_issues)} warning"
                    else:
                        issues_str = "✅ healthy"

                    root_cause_str = ""
                    if result.root_cause:
                        root_cause_str = f" - {result.root_cause.title}"

                    typer.echo(f"  {result.subject.name}: {status} | {issues_str}{root_cause_str}")

                if batch_result.errors:
                    typer.echo(f"\n⚠️  Errors ({len(batch_result.errors)}):")
                    for error in batch_result.errors[:5]:
                        typer.echo(f"  - {error.get('resource')}: {error.get('error')}")

                typer.echo(f"\n⏱️  Completed in {batch_result.duration:.2f}s")

            # Exit code: 2 if any critical/warning issues found
            has_issues = any(r.critical_issues or r.warning_issues for r in batch_result.results)
            raise typer.Exit(2 if has_issues else 0)

        except typer.Exit:
            raise
        except Exception as e:
            typer.echo(f"Error: {e}", err=True)
            raise typer.Exit(2)

    # Single resource mode
    subject = SubjectCtx(
        kind=kind_map[resource_type],
        name=name,
        namespace=namespace,
        context=context,
        scope="resource",
    )

    # Handle watch mode
    if watch:
        from ..watch import ResourceWatcher

        watcher = ResourceWatcher(
            subject=subject,
            interval_seconds=float(interval),
        )

        try:
            asyncio.run(watcher.start(output_format=output))
        except KeyboardInterrupt:
            pass
        raise typer.Exit(0)

    # Lazy import to avoid slow startup
    from .commands import DiagCommand

    # Create and run command
    command = DiagCommand()

    try:
        if output == "json":
            # Use execute_raw to get DiagnosisResult for JSON rendering
            from ..renderers.json_renderer import JsonRenderer

            diagnosis_result = asyncio.run(command.execute_raw(subject))
            renderer = JsonRenderer(pretty=True)
            typer.echo(renderer.render_diagnosis(diagnosis_result))

            # Determine exit code
            exit_code = 2 if diagnosis_result.critical_issues or diagnosis_result.warning_issues else 0
            raise typer.Exit(exit_code)
        else:
            result = asyncio.run(command.execute(subject))
            typer.echo(result.output)

            # Set exit code based on issues found
            import os
            if os.getenv('KUBECTL_SMART_DEBUG'):
                typer.echo(f"Debug: result.exit_code = {result.exit_code}", err=True)
            raise typer.Exit(result.exit_code)

    except typer.Exit:
        raise  # Re-raise typer.Exit to ensure correct exit code
    except Exception as e:
        import os
        if os.getenv('KUBECTL_SMART_DEBUG'):
            typer.echo(f"Debug: Exception caught: {e}", err=True)
        if output == "json":
            from ..renderers.json_renderer import JsonRenderer
            renderer = JsonRenderer(pretty=True)
            typer.echo(renderer.render_error(str(e)))
        else:
            typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(2)


@app.command()
def graph(
    resource_type: Annotated[ResourceType, typer.Argument(help="Resource type (pod, deploy, sts, job)")],
    name: Annotated[str, typer.Argument(help="Resource name")],
    namespace: Annotated[Optional[str], typer.Option("--namespace", "-n", help="Namespace")] = None,
    context: Annotated[Optional[str], typer.Option("--context", help="kubectl context")] = None,
    upstream: Annotated[bool, typer.Option("--upstream", help="Show upstream dependencies")] = False,
    downstream: Annotated[bool, typer.Option("--downstream", help="Show downstream dependencies")] = False,
):
    """
    🔗 Dependency visualization (ASCII tree)
    
    [bold]Purpose:[/bold] Show what's upstream/downstream of target for blast-radius checks
    
    [bold]Features:[/bold]
    • ASCII dependency tree with health indicators
    • Upstream: what this resource depends on
    • Downstream: what depends on this resource  
    • Reuses graph from diag if run in same process
    
    [bold]Examples:[/bold]
      kubectl-smart graph pod checkout-xyz --upstream
      kubectl-smart graph deploy my-app --downstream
      kubectl-smart graph sts database -n prod
    """
    _validate_resource_name(name)
    _validate_namespace(namespace)
    context = _resolve_context(context)
    _validate_context(context)
    
    # Default to downstream if neither specified
    if not upstream and not downstream:
        downstream = True
    
    direction = "both" if upstream and downstream else "upstream" if upstream else "downstream"
    
    # Lazy import models
    from ..models import ResourceKind, SubjectCtx
    
    # Map resource type to ResourceKind
    kind_map = {
        ResourceType.POD: ResourceKind.POD,
        ResourceType.DEPLOYMENT: ResourceKind.DEPLOYMENT,
        ResourceType.DEPLOYMENT_FULL: ResourceKind.DEPLOYMENT,
        ResourceType.STATEFULSET: ResourceKind.STATEFULSET,
        ResourceType.STATEFULSET_FULL: ResourceKind.STATEFULSET,
        ResourceType.JOB: ResourceKind.JOB,
        ResourceType.SERVICE: ResourceKind.SERVICE,
        ResourceType.SERVICE_FULL: ResourceKind.SERVICE,
        ResourceType.INGRESS: ResourceKind.INGRESS,
        ResourceType.REPLICASET: ResourceKind.REPLICASET,
        ResourceType.REPLICASET_FULL: ResourceKind.REPLICASET,
        ResourceType.DAEMONSET: ResourceKind.DAEMONSET,
        ResourceType.DAEMONSET_FULL: ResourceKind.DAEMONSET,
    }
    
    # Create subject context
    subject = SubjectCtx(
        kind=kind_map[resource_type],
        name=name,
        namespace=namespace,
        context=context,
        scope="resource",
    )
    
    # Lazy import to avoid slow startup
    from .commands import GraphCommand
    
    # Create and run command
    command = GraphCommand()
    
    try:
        result = asyncio.run(command.execute(subject, direction))
        typer.echo(result.output)
        raise typer.Exit(result.exit_code)
    except typer.Exit:
        raise
    except Exception as e:
        import os
        if os.getenv('KUBECTL_SMART_DEBUG'):
            typer.echo(f"Debug: Exception caught: {e}", err=True)
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(2)


@app.command()
def top(
    namespace: Annotated[str, typer.Argument(help="Namespace to analyze")],
    context: Annotated[Optional[str], typer.Option("--context", help="kubectl context")] = None,
    horizon: Annotated[int, typer.Option("--horizon", "-h", help="Forecast horizon in hours", min=1, max=168)] = 48,
):
    """
    📈 Predictive capacity & certificate outlook
    
    [bold]Purpose:[/bold] Forecast disk, memory, CPU, and certificate expirations over next 48h
    
    [bold]Features:[/bold]
    • Holt-Winters time-series forecasting (or linear fallback)
    • Certificate expiry detection (<14 days warning)
    • Only shows actionable risks (≥90% utilization or expiring)
    • Works with metrics-server or degrades gracefully
    
    [bold]Examples:[/bold]
      kubectl-smart top production
      kubectl-smart top kube-system --horizon=24  
      kubectl-smart top staging
    """
    _validate_namespace(namespace)
    context = _resolve_context(context)
    _validate_context(context)
    
    # Lazy import models
    from ..models import ResourceKind, SubjectCtx
    
    # Create subject context for namespace analysis
    subject = SubjectCtx(
        kind=ResourceKind.NAMESPACE,
        name=namespace,
        namespace=namespace,
        context=context,
        scope="namespace",
    )
    
    # Lazy import to avoid slow startup
    from .commands import TopCommand
    
    # Create and run command
    command = TopCommand(forecast_horizon_hours=horizon)
    
    try:
        result = asyncio.run(command.execute(subject))
        typer.echo(result.output)
        raise typer.Exit(result.exit_code)
    except typer.Exit:
        raise
    except Exception as e:
        import os
        if os.getenv('KUBECTL_SMART_DEBUG'):
            typer.echo(f"Debug: Exception caught: {e}", err=True)
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(2)


# Legacy commands for backward compatibility (hidden from help)
@app.command(hidden=True)
def describe(
    resource_type: str,
    name: str,
    namespace: Optional[str] = typer.Option(None, "--namespace", "-n"),
    
):
    """Legacy describe command - use 'diag' instead"""
    typer.echo("⚠️  'describe' is deprecated. Use 'kubectl-smart diag' instead.")
    typer.echo(f"   Try: kubectl-smart diag {resource_type} {name}")
    raise typer.Exit(1)


@app.command(hidden=True) 
def deps(
    resource_type: str,
    name: str,
    namespace: Optional[str] = typer.Option(None, "--namespace", "-n"),
):
    """Legacy deps command - use 'graph' instead"""
    typer.echo("⚠️  'deps' is deprecated. Use 'kubectl-smart graph' instead.")
    typer.echo(f"   Try: kubectl-smart graph {resource_type} {name}")
    raise typer.Exit(1)


@app.command(hidden=True)
def events(
    namespace: Optional[str] = typer.Option(None, "--namespace", "-n"),
):
    """Legacy events command - use 'diag' or 'top' instead"""
    typer.echo("⚠️  'events' is deprecated. Use 'kubectl-smart diag' or 'top' instead.")
    typer.echo("   Try: kubectl-smart diag pod <name> or kubectl-smart top <namespace>")
    raise typer.Exit(1)


if __name__ == "__main__":
    app()
