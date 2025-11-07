"""
Health checks and system validation for kubectl-smart

Validates:
- kubectl installation and version
- Cluster connectivity
- Required permissions (RBAC)
- Dependencies
- System resources
"""

import asyncio
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from typing import List, Optional

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class HealthCheckResult:
    """Result of a health check"""
    name: str
    status: str  # "pass", "warn", "fail"
    message: str
    details: Optional[dict] = None


class HealthChecker:
    """System health checker for kubectl-smart"""

    def __init__(self):
        self.results: List[HealthCheckResult] = []

    async def run_all_checks(self) -> List[HealthCheckResult]:
        """Run all health checks

        Returns:
            List of health check results
        """
        self.results = []

        # Run checks concurrently
        await asyncio.gather(
            self.check_python_version(),
            self.check_kubectl_installed(),
            self.check_kubectl_version(),
            self.check_cluster_connectivity(),
            self.check_dependencies(),
            return_exceptions=True,
        )

        return self.results

    async def check_python_version(self) -> HealthCheckResult:
        """Check Python version meets requirements"""
        result = HealthCheckResult(
            name="Python Version",
            status="pass",
            message="",
        )

        version_info = sys.version_info
        version_str = f"{version_info.major}.{version_info.minor}.{version_info.micro}"

        if version_info < (3, 9):
            result.status = "fail"
            result.message = f"Python {version_str} is too old. Required: Python 3.9+"
        else:
            result.status = "pass"
            result.message = f"Python {version_str} OK"
            result.details = {
                "version": version_str,
                "implementation": sys.implementation.name,
            }

        self.results.append(result)
        return result

    async def check_kubectl_installed(self) -> HealthCheckResult:
        """Check if kubectl is installed"""
        result = HealthCheckResult(
            name="kubectl Installation",
            status="pass",
            message="",
        )

        try:
            process = await asyncio.create_subprocess_exec(
                "which", "kubectl",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await process.communicate()

            if process.returncode == 0:
                kubectl_path = stdout.decode().strip()
                result.status = "pass"
                result.message = f"kubectl found at {kubectl_path}"
                result.details = {"path": kubectl_path}
            else:
                result.status = "fail"
                result.message = "kubectl not found in PATH"

        except Exception as e:
            result.status = "fail"
            result.message = f"Failed to check kubectl: {e}"

        self.results.append(result)
        return result

    async def check_kubectl_version(self) -> HealthCheckResult:
        """Check kubectl version"""
        result = HealthCheckResult(
            name="kubectl Version",
            status="pass",
            message="",
        )

        try:
            process = await asyncio.create_subprocess_exec(
                "kubectl", "version", "--client", "--output=json",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await process.communicate()

            if process.returncode == 0:
                version_data = json.loads(stdout.decode())
                version_str = version_data.get("clientVersion", {}).get("gitVersion", "unknown")

                # Extract version number (e.g., v1.28.0 -> 1.28)
                match = re.match(r"v?(\d+)\.(\d+)", version_str)
                if match:
                    major, minor = int(match.group(1)), int(match.group(2))

                    if major < 1 or (major == 1 and minor < 20):
                        result.status = "warn"
                        result.message = f"kubectl {version_str} is old. Recommended: v1.20+"
                    else:
                        result.status = "pass"
                        result.message = f"kubectl {version_str} OK"

                    result.details = {
                        "version": version_str,
                        "major": major,
                        "minor": minor,
                    }
                else:
                    result.status = "warn"
                    result.message = f"Could not parse kubectl version: {version_str}"

            else:
                result.status = "warn"
                result.message = "Could not get kubectl version"

        except Exception as e:
            result.status = "warn"
            result.message = f"Failed to check kubectl version: {e}"

        self.results.append(result)
        return result

    async def check_cluster_connectivity(self) -> HealthCheckResult:
        """Check if cluster is accessible"""
        result = HealthCheckResult(
            name="Cluster Connectivity",
            status="pass",
            message="",
        )

        try:
            process = await asyncio.create_subprocess_exec(
                "kubectl", "cluster-info",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                timeout=5.0,
            )
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=5.0)

            if process.returncode == 0:
                result.status = "pass"
                result.message = "Cluster is accessible"

                # Extract cluster info
                output = stdout.decode()
                result.details = {"cluster_info": output[:200]}  # First 200 chars
            else:
                error_msg = stderr.decode()
                result.status = "fail"
                result.message = f"Cannot connect to cluster: {error_msg[:100]}"

        except asyncio.TimeoutError:
            result.status = "fail"
            result.message = "Cluster connection timed out (>5s)"
        except Exception as e:
            result.status = "warn"
            result.message = f"Could not check cluster connectivity: {e}"

        self.results.append(result)
        return result

    async def check_dependencies(self) -> HealthCheckResult:
        """Check Python dependencies are installed"""
        result = HealthCheckResult(
            name="Python Dependencies",
            status="pass",
            message="",
        )

        required_modules = [
            "typer",
            "pydantic",
            "structlog",
            "rich",
            "igraph",
            "statsmodels",
        ]

        missing = []
        for module in required_modules:
            try:
                __import__(module)
            except ImportError:
                missing.append(module)

        if missing:
            result.status = "fail"
            result.message = f"Missing dependencies: {', '.join(missing)}"
            result.details = {"missing": missing}
        else:
            result.status = "pass"
            result.message = "All dependencies installed"

        self.results.append(result)
        return result

    async def check_rbac_permissions(self, namespace: str = "default") -> HealthCheckResult:
        """Check RBAC permissions for common operations

        Args:
            namespace: Namespace to check permissions in

        Returns:
            Health check result
        """
        result = HealthCheckResult(
            name="RBAC Permissions",
            status="pass",
            message="",
        )

        resources_to_check = ["pods", "deployments", "services", "events"]
        denied = []

        try:
            for resource in resources_to_check:
                process = await asyncio.create_subprocess_exec(
                    "kubectl", "auth", "can-i", "get", resource,
                    "--namespace", namespace,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, _ = await process.communicate()

                if stdout.decode().strip() != "yes":
                    denied.append(resource)

            if denied:
                result.status = "warn"
                result.message = f"Missing permissions for: {', '.join(denied)}"
                result.details = {"denied_resources": denied}
            else:
                result.status = "pass"
                result.message = f"All permissions OK in namespace '{namespace}'"

        except Exception as e:
            result.status = "warn"
            result.message = f"Could not check RBAC permissions: {e}"

        self.results.append(result)
        return result

    def print_results(self, verbose: bool = False) -> None:
        """Print health check results

        Args:
            verbose: Show detailed information
        """
        print("\n🏥 kubectl-smart Health Check\n")
        print("=" * 60)

        status_icons = {
            "pass": "✅",
            "warn": "⚠️",
            "fail": "❌",
        }

        for result in self.results:
            icon = status_icons.get(result.status, "❓")
            print(f"{icon} {result.name}: {result.message}")

            if verbose and result.details:
                for key, value in result.details.items():
                    print(f"   {key}: {value}")

        print("=" * 60)

        # Summary
        pass_count = sum(1 for r in self.results if r.status == "pass")
        warn_count = sum(1 for r in self.results if r.status == "warn")
        fail_count = sum(1 for r in self.results if r.status == "fail")

        print(f"\nSummary: {pass_count} passed, {warn_count} warnings, {fail_count} failed")

        if fail_count > 0:
            print("\n⚠️  Some health checks failed. kubectl-smart may not work correctly.")
            print("   Please address the failures above before using kubectl-smart.")
            return False
        elif warn_count > 0:
            print("\n⚠️  Some health checks have warnings. kubectl-smart should work but may have limitations.")
            return True
        else:
            print("\n✅ All health checks passed! kubectl-smart is ready to use.")
            return True


async def run_health_checks(verbose: bool = False) -> bool:
    """Run all health checks and print results

    Args:
        verbose: Show detailed information

    Returns:
        True if all critical checks passed
    """
    checker = HealthChecker()
    await checker.run_all_checks()
    return checker.print_results(verbose=verbose)


def quick_health_check() -> bool:
    """Quick synchronous health check (kubectl + cluster only)

    Returns:
        True if basic checks passed
    """
    try:
        # Check kubectl
        result = subprocess.run(
            ["kubectl", "version", "--client"],
            capture_output=True,
            timeout=2.0,
        )
        if result.returncode != 0:
            return False

        # Check cluster
        result = subprocess.run(
            ["kubectl", "cluster-info"],
            capture_output=True,
            timeout=3.0,
        )
        return result.returncode == 0

    except Exception:
        return False
