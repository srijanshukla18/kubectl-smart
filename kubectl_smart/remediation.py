"""
Automated remediation for common Kubernetes issues

This module provides automated fixes for common problems detected
during diagnosis. Use with caution - always review before applying.
"""

import asyncio
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from enum import Enum

import structlog

from .models import Issue, ResourceRecord, IssueSeverity

logger = structlog.get_logger(__name__)


class RemediationAction(str, Enum):
    """Types of remediation actions"""
    RESTART_POD = "restart_pod"
    SCALE_DEPLOYMENT = "scale_deployment"
    UPDATE_IMAGE = "update_image"
    ADD_RESOURCES = "add_resources"
    FIX_PROBE = "fix_probe"
    CREATE_SECRET = "create_secret"
    PATCH_CONFIG = "patch_config"


@dataclass
class Remediation:
    """A remediation action"""
    action: RemediationAction
    description: str
    command: str
    risk_level: str  # "low", "medium", "high"
    automated: bool  # Can be applied automatically
    requires_confirmation: bool
    details: Dict[str, Any]


class RemediationEngine:
    """Engine for generating and applying remediations"""

    def __init__(self, dry_run: bool = True):
        """Initialize remediation engine

        Args:
            dry_run: If True, only show what would be done
        """
        self.dry_run = dry_run

    def generate_remediations(
        self,
        resource: ResourceRecord,
        issues: List[Issue],
    ) -> List[Remediation]:
        """Generate remediation actions for issues

        Args:
            resource: Resource with issues
            issues: List of issues

        Returns:
            List of possible remediations
        """
        remediations = []

        for issue in issues:
            remediation = self._generate_remediation_for_issue(resource, issue)
            if remediation:
                remediations.append(remediation)

        return remediations

    def _generate_remediation_for_issue(
        self,
        resource: ResourceRecord,
        issue: Issue,
    ) -> Optional[Remediation]:
        """Generate remediation for a specific issue

        Args:
            resource: Resource with issue
            issue: Issue to remediate

        Returns:
            Remediation or None if no automated fix available
        """
        reason = issue.reason.lower()
        message = issue.message.lower()

        # CrashLoopBackOff - restart pod
        if "crashloopbackoff" in reason:
            return Remediation(
                action=RemediationAction.RESTART_POD,
                description=f"Restart pod {resource.name} to clear crash loop",
                command=f"kubectl delete pod {resource.name}" +
                        (f" -n {resource.namespace}" if resource.namespace else ""),
                risk_level="medium",
                automated=True,
                requires_confirmation=True,
                details={
                    "reason": "Deleting pod will trigger controller to create new one",
                    "downtime": "Brief downtime during pod restart",
                },
            )

        # ImagePullBackOff - check image name
        if "imagepullbackoff" in reason or "errimagepull" in reason:
            return Remediation(
                action=RemediationAction.UPDATE_IMAGE,
                description=f"Fix image pull issue for {resource.name}",
                command=f"# Manual intervention required:\n" +
                        f"# 1. Verify image name and tag\n" +
                        f"# 2. Check image pull secrets\n" +
                        f"# 3. Update deployment with correct image",
                risk_level="medium",
                automated=False,
                requires_confirmation=True,
                details={
                    "reason": "Image pull failures require manual verification",
                    "steps": [
                        "Verify image exists in registry",
                        "Check image pull secrets are configured",
                        "Update image name if incorrect",
                    ],
                },
            )

        # OOMKilled - increase memory limits
        if "oomkilled" in message or "out of memory" in message:
            return Remediation(
                action=RemediationAction.ADD_RESOURCES,
                description=f"Increase memory limits for {resource.name}",
                command=f"# Increase memory limits:\n" +
                        f"kubectl set resources deployment {resource.name} " +
                        f"--limits=memory=512Mi " +
                        (f"-n {resource.namespace}" if resource.namespace else ""),
                risk_level="low",
                automated=False,  # Requires knowing appropriate limits
                requires_confirmation=True,
                details={
                    "reason": "Pod was killed due to memory limits",
                    "recommendation": "Analyze actual memory usage and set appropriate limits",
                },
            )

        # Failed scheduling - scale down or add nodes
        if "failedscheduling" in reason:
            if "insufficient" in message:
                return Remediation(
                    action=RemediationAction.SCALE_DEPLOYMENT,
                    description=f"Insufficient resources - consider scaling down or adding nodes",
                    command=f"# Option 1: Scale down deployment\n" +
                            f"kubectl scale deployment {resource.name} --replicas=1 " +
                            (f"-n {resource.namespace}" if resource.namespace else "") +
                            f"\n# Option 2: Add more nodes to cluster",
                    risk_level="high",
                    automated=False,
                    requires_confirmation=True,
                    details={
                        "reason": "Cluster has insufficient resources",
                        "options": ["Scale down deployment", "Add more nodes", "Adjust resource requests"],
                    },
                )

        # Readiness probe failure
        if "readiness" in reason or "liveness" in reason:
            return Remediation(
                action=RemediationAction.FIX_PROBE,
                description=f"Fix probe configuration for {resource.name}",
                command=f"# Review and adjust probe settings:\n" +
                        f"kubectl edit deployment {resource.name} " +
                        (f"-n {resource.namespace}" if resource.namespace else "") +
                        f"\n# Increase initialDelaySeconds if app needs more startup time\n" +
                        f"# Adjust periodSeconds and timeoutSeconds if needed",
                risk_level="low",
                automated=False,
                requires_confirmation=True,
                details={
                    "reason": "Probe failing - may need timing adjustments",
                    "common_fixes": [
                        "Increase initialDelaySeconds",
                        "Increase timeoutSeconds",
                        "Fix probe endpoint",
                    ],
                },
            )

        return None

    async def apply_remediation(
        self,
        remediation: Remediation,
        confirm: bool = True,
    ) -> Dict[str, Any]:
        """Apply a remediation action

        Args:
            remediation: Remediation to apply
            confirm: Require user confirmation

        Returns:
            Result dictionary
        """
        if not remediation.automated:
            return {
                "applied": False,
                "reason": "Manual intervention required",
                "instructions": remediation.command,
            }

        if self.dry_run:
            return {
                "applied": False,
                "dry_run": True,
                "would_execute": remediation.command,
                "description": remediation.description,
            }

        if confirm and remediation.requires_confirmation:
            # In a real implementation, prompt user for confirmation
            # For now, return pending confirmation
            return {
                "applied": False,
                "reason": "Requires confirmation",
                "command": remediation.command,
                "risk_level": remediation.risk_level,
            }

        # Execute remediation
        try:
            logger.info(
                "Applying remediation",
                action=remediation.action,
                command=remediation.command,
            )

            # Execute command
            process = await asyncio.create_subprocess_shell(
                remediation.command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await process.communicate()

            if process.returncode == 0:
                return {
                    "applied": True,
                    "action": remediation.action,
                    "output": stdout.decode(),
                }
            else:
                return {
                    "applied": False,
                    "reason": "Command failed",
                    "error": stderr.decode(),
                }

        except Exception as e:
            logger.error("Failed to apply remediation", error=str(e))
            return {
                "applied": False,
                "reason": "Exception occurred",
                "error": str(e),
            }

    def format_remediations(self, remediations: List[Remediation]) -> str:
        """Format remediations for display

        Args:
            remediations: List of remediations

        Returns:
            Formatted string
        """
        if not remediations:
            return "\nℹ️  No automated remediations available\n"

        lines = [
            "\n🔧 AUTOMATED REMEDIATION OPTIONS",
            "=" * 60,
        ]

        for i, rem in enumerate(remediations, 1):
            risk_icon = {
                "low": "🟢",
                "medium": "🟡",
                "high": "🔴",
            }.get(rem.risk_level, "⚪")

            auto_status = "✅ Automated" if rem.automated else "👤 Manual"

            lines.append(f"\n{i}. {rem.description}")
            lines.append(f"   Risk: {risk_icon} {rem.risk_level.upper()}")
            lines.append(f"   Status: {auto_status}")
            lines.append(f"\n   Command:")

            # Indent command
            for cmd_line in rem.command.split("\n"):
                lines.append(f"   {cmd_line}")

            if rem.details:
                lines.append(f"\n   Details:")
                if "reason" in rem.details:
                    lines.append(f"   • {rem.details['reason']}")
                if "steps" in rem.details:
                    for step in rem.details["steps"]:
                        lines.append(f"     - {step}")

        lines.append("\n" + "=" * 60)
        lines.append(f"\n💡 To apply automated fixes, use: --apply")
        lines.append(f"⚠️  Always review commands before applying!")

        return "\n".join(lines)
