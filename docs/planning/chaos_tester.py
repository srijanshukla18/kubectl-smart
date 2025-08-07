#!/usr/bin/env python3
"""
Chaos Monkey-style Testing Framework for kubectl-smart
======================================================

This script implements Netflix Chaos Monkey principles to test kubectl-smart
against various chaos scenarios in minikube. It generates chaos experiments
and validates kubectl-smart's analysis against kubectl's raw output.

Based on Chaos Mesh documentation and Chaos Engineering principles.
"""

import subprocess
import json
import time
import tempfile
import os
import sys
from datetime import datetime
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from enum import Enum

class ChaosType(Enum):
    """Types of chaos experiments based on Chaos Mesh capabilities"""
    POD_KILL = "pod-kill"
    NETWORK_PARTITION = "network-partition"
    NETWORK_DELAY = "network-delay"
    NETWORK_LOSS = "network-loss"
    CPU_STRESS = "cpu-stress"
    MEMORY_STRESS = "memory-stress"
    IO_STRESS = "io-stress"
    CONTAINER_KILL = "container-kill"
    POD_FAILURE = "pod-failure"
    IMAGE_PULL_FAILURE = "image-pull-failure"
    RESOURCE_EXHAUSTION = "resource-exhaustion"
    NODE_FAILURE = "node-failure"

@dataclass
class ChaosScenario:
    """Represents a chaos testing scenario"""
    name: str
    chaos_type: ChaosType
    description: str
    setup_commands: List[str]
    cleanup_commands: List[str]
    expected_kubectl_smart_behaviors: List[str]
    validation_commands: List[str]
    duration: int = 30  # seconds

class ChaosMonkeyTester:
    """Netflix Chaos Monkey-style testing framework for kubectl-smart"""
    
    def __init__(self):
        self.namespace = "chaos-test"
        self.results = []
        self.test_start_time = datetime.now()
        
    def run_command(self, cmd: str, timeout: int = 30) -> Tuple[int, str, str]:
        """Execute command and return (returncode, stdout, stderr)"""
        try:
            result = subprocess.run(
                cmd, shell=True, capture_output=True, text=True, timeout=timeout
            )
            return result.returncode, result.stdout, result.stderr
        except subprocess.TimeoutExpired:
            return 1, "", f"Command timed out after {timeout} seconds"
        except Exception as e:
            return 1, "", str(e)
    
    def setup_test_environment(self):
        """Setup isolated test environment"""
        print("🔧 Setting up chaos test environment...")
        
        # Create test namespace
        self.run_command(f"kubectl create namespace {self.namespace} --dry-run=client -o yaml | kubectl apply -f -")
        
        # Deploy baseline test applications
        test_apps = [
            # Simple web app
            f"kubectl run web-app --image=nginx:alpine -n {self.namespace}",
            f"kubectl expose pod web-app --port=80 -n {self.namespace}",
            
            # CPU-intensive app
            f"kubectl run cpu-app --image=busybox -n {self.namespace} -- sh -c 'while true; do echo computing; done'",
            
            # Memory app
            f"kubectl run memory-app --image=busybox -n {self.namespace} -- sh -c 'sleep 3600'",
            
            # Network service
            f"kubectl run api-service --image=httpd:alpine -n {self.namespace}",
            f"kubectl expose pod api-service --port=80 -n {self.namespace}",
            
            # Database simulation
            f"kubectl run db-app --image=redis:alpine -n {self.namespace}",
        ]
        
        for cmd in test_apps:
            code, stdout, stderr = self.run_command(cmd)
            if code != 0:
                print(f"⚠️  Setup warning: {cmd} -> {stderr}")
        
        # Wait for pods to be ready
        print("⏳ Waiting for test pods to be ready...")
        time.sleep(15)
        
        code, stdout, stderr = self.run_command(f"kubectl get pods -n {self.namespace}")
        print(f"📊 Test environment status:\n{stdout}")
    
    def cleanup_test_environment(self):
        """Clean up test environment"""
        print("🧹 Cleaning up test environment...")
        self.run_command(f"kubectl delete namespace {self.namespace} --ignore-not-found=true")
        
        # Clean up any orphaned resources
        cleanup_commands = [
            "kubectl delete pods --field-selector=status.phase==Failed -A",
            "kubectl delete pods --field-selector=status.phase==Succeeded -A",
        ]
        
        for cmd in cleanup_commands:
            self.run_command(cmd)
    
    def generate_chaos_scenarios(self) -> List[ChaosScenario]:
        """Generate comprehensive chaos scenarios based on Chaos Mesh patterns"""
        
        scenarios = [
            # Pod Chaos Scenarios
            ChaosScenario(
                name="pod-kill-chaos",
                chaos_type=ChaosType.POD_KILL,
                description="Kill random pods to test pod failure handling",
                setup_commands=[
                    f"kubectl delete pod web-app -n {self.namespace} &",
                ],
                cleanup_commands=[
                    f"kubectl run web-app --image=nginx:alpine -n {self.namespace} --force --grace-period=0 || true",
                ],
                expected_kubectl_smart_behaviors=[
                    "Should detect pod termination in critical events",
                    "Should show pod in Failed/Terminating state", 
                    "Should recommend investigating pod logs",
                ],
                validation_commands=[
                    f"kubectl get pods -n {self.namespace}",
                    f"kubectl get events -n {self.namespace}",
                ],
            ),
            
            # Image Pull Failure
            ChaosScenario(
                name="image-pull-failure",
                chaos_type=ChaosType.IMAGE_PULL_FAILURE,
                description="Create pod with non-existent image",
                setup_commands=[
                    f"kubectl run broken-image-pod --image=nonexistent:broken123 -n {self.namespace}",
                ],
                cleanup_commands=[
                    f"kubectl delete pod broken-image-pod -n {self.namespace} --ignore-not-found=true",
                ],
                expected_kubectl_smart_behaviors=[
                    "Should detect ImagePullBackOff as critical issue",
                    "Should provide registry access recommendations",
                    "Should show Failed/ErrImagePull events",
                ],
                validation_commands=[
                    f"kubectl get pods broken-image-pod -n {self.namespace}",
                    f"kubectl describe pod broken-image-pod -n {self.namespace}",
                ],
            ),
            
            # Resource Exhaustion
            ChaosScenario(
                name="resource-exhaustion",
                chaos_type=ChaosType.RESOURCE_EXHAUSTION,
                description="Create pods with impossible resource requests",
                setup_commands=[
                    f"kubectl run resource-hog --image=busybox -n {self.namespace} --requests=cpu=1000,memory=1000Gi -- sleep 3600",
                ],
                cleanup_commands=[
                    f"kubectl delete pod resource-hog -n {self.namespace} --ignore-not-found=true",
                ],
                expected_kubectl_smart_behaviors=[
                    "Should detect FailedScheduling events",
                    "Should recommend checking node capacity",
                    "Should show Pending pod status",
                ],
                validation_commands=[
                    f"kubectl get pods resource-hog -n {self.namespace}",
                    f"kubectl top nodes",
                ],
            ),
            
            # Container Kill
            ChaosScenario(
                name="container-kill-chaos",
                chaos_type=ChaosType.CONTAINER_KILL,
                description="Kill container processes inside running pods",
                setup_commands=[
                    f"kubectl exec cpu-app -n {self.namespace} -- sh -c 'kill 1' || true",
                ],
                cleanup_commands=[
                    # Pod should restart automatically
                ],
                expected_kubectl_smart_behaviors=[
                    "Should detect container restart events",
                    "Should show increased restart count",
                    "Should identify if restart loop occurs",
                ],
                validation_commands=[
                    f"kubectl get pods cpu-app -n {self.namespace}",
                    f"kubectl describe pod cpu-app -n {self.namespace}",
                ],
            ),
            
            # Simulated Memory Stress
            ChaosScenario(
                name="memory-stress-simulation",
                chaos_type=ChaosType.MEMORY_STRESS,
                description="Create memory-intensive workload",
                setup_commands=[
                    f"kubectl run memory-stress --image=busybox -n {self.namespace} -- sh -c 'dd if=/dev/zero of=/tmp/memory.tmp bs=1M count=512; sleep 300'",
                ],
                cleanup_commands=[
                    f"kubectl delete pod memory-stress -n {self.namespace} --ignore-not-found=true",
                ],
                expected_kubectl_smart_behaviors=[
                    "Should detect high memory usage if limits exceeded",
                    "Should recommend resource optimization",
                    "Should show OOMKilled if memory limit hit",
                ],
                validation_commands=[
                    f"kubectl top pods -n {self.namespace}",
                    f"kubectl get pods memory-stress -n {self.namespace}",
                ],
            ),
            
            # Network Service Failure 
            ChaosScenario(
                name="service-failure",
                chaos_type=ChaosType.NETWORK_PARTITION,
                description="Break service by deleting endpoints",
                setup_commands=[
                    f"kubectl delete pod api-service -n {self.namespace}",
                    # Service remains but no backend pods
                ],
                cleanup_commands=[
                    f"kubectl run api-service --image=httpd:alpine -n {self.namespace}",
                    f"kubectl expose pod api-service --port=80 -n {self.namespace} || true",
                ],
                expected_kubectl_smart_behaviors=[
                    "Should detect service with no endpoints",
                    "Should identify network/connectivity issues",
                    "Should show service status problems",
                ],
                validation_commands=[
                    f"kubectl get endpoints -n {self.namespace}",
                    f"kubectl get services -n {self.namespace}",
                ],
            ),
            
            # Multiple Pod Failure (Cascade Failure)
            ChaosScenario(
                name="cascade-failure",
                chaos_type=ChaosType.POD_FAILURE,
                description="Multiple related pod failures",
                setup_commands=[
                    f"kubectl delete pods web-app api-service db-app -n {self.namespace}",
                ],
                cleanup_commands=[
                    f"kubectl run web-app --image=nginx:alpine -n {self.namespace} || true",
                    f"kubectl run api-service --image=httpd:alpine -n {self.namespace} || true", 
                    f"kubectl run db-app --image=redis:alpine -n {self.namespace} || true",
                ],
                expected_kubectl_smart_behaviors=[
                    "Should detect multiple critical failures",
                    "Should prioritize most critical issues",
                    "Should show degraded namespace health",
                ],
                validation_commands=[
                    f"kubectl get pods -n {self.namespace}",
                    f"kubectl get events -n {self.namespace} --sort-by=.lastTimestamp",
                ],
            ),
            
            # Persistent Volume Issues
            ChaosScenario(
                name="storage-failure",
                chaos_type=ChaosType.IO_STRESS,
                description="Create pod with impossible storage requirements",
                setup_commands=[
                    f"""cat > /tmp/bad-pvc.yaml << EOF
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: impossible-storage
  namespace: {self.namespace}
spec:
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: 999999Gi
  storageClassName: nonexistent-class
EOF""",
                    "kubectl apply -f /tmp/bad-pvc.yaml",
                    f"kubectl run storage-pod --image=busybox -n {self.namespace} --overrides='{{\"spec\":{{\"containers\":[{{\"name\":\"busybox\",\"image\":\"busybox\",\"command\":[\"sleep\",\"3600\"],\"volumeMounts\":[{{\"name\":\"storage\",\"mountPath\":\"/data\"}}]}}],\"volumes\":[{{\"name\":\"storage\",\"persistentVolumeClaim\":{{\"claimName\":\"impossible-storage\"}}}}]}}}}' || true",
                ],
                cleanup_commands=[
                    f"kubectl delete pod storage-pod -n {self.namespace} --ignore-not-found=true",
                    f"kubectl delete pvc impossible-storage -n {self.namespace} --ignore-not-found=true",
                    "rm -f /tmp/bad-pvc.yaml",
                ],
                expected_kubectl_smart_behaviors=[
                    "Should detect PVC in Pending state",
                    "Should identify storage mount failures",
                    "Should recommend storage class verification",
                ],
                validation_commands=[
                    f"kubectl get pvc -n {self.namespace}",
                    f"kubectl get pods storage-pod -n {self.namespace}",
                ],
            ),
        ]
        
        return scenarios
    
    def execute_chaos_scenario(self, scenario: ChaosScenario) -> Dict:
        """Execute a single chaos scenario and collect results"""
        print(f"\n🌪️  CHAOS SCENARIO: {scenario.name}")
        print(f"📝 Description: {scenario.description}")
        print(f"⏱️  Duration: {scenario.duration}s")
        
        result = {
            "scenario": scenario.name,
            "chaos_type": scenario.chaos_type.value,
            "description": scenario.description,
            "start_time": datetime.now().isoformat(),
            "success": False,
            "kubectl_output": {},
            "kubectl_smart_output": {},
            "validation_results": [],
            "errors": [],
        }
        
        try:
            # Execute setup commands
            print("🔧 Setting up chaos scenario...")
            for cmd in scenario.setup_commands:
                print(f"   Running: {cmd}")
                code, stdout, stderr = self.run_command(cmd)
                if code != 0 and "already exists" not in stderr:
                    result["errors"].append(f"Setup failed: {cmd} -> {stderr}")
            
            # Wait for chaos to take effect
            print(f"⏳ Waiting {scenario.duration}s for chaos to manifest...")
            time.sleep(scenario.duration)
            
            # Collect kubectl baseline data
            print("📊 Collecting kubectl baseline data...")
            kubectl_data = self.collect_kubectl_data()
            result["kubectl_output"] = kubectl_data
            
            # Collect kubectl-smart analysis  
            print("🎯 Running kubectl-smart analysis...")
            smart_data = self.collect_kubectl_smart_data()
            result["kubectl_smart_output"] = smart_data
            
            # Run validation commands
            print("✅ Running validation checks...")
            for cmd in scenario.validation_commands:
                code, stdout, stderr = self.run_command(cmd)
                result["validation_results"].append({
                    "command": cmd,
                    "returncode": code,
                    "stdout": stdout,
                    "stderr": stderr
                })
            
            # Validate expectations
            validation_score = self.validate_scenario_expectations(
                scenario, result["kubectl_smart_output"], result["kubectl_output"]
            )
            result["validation_score"] = validation_score
            result["success"] = validation_score > 0.7  # 70% threshold
            
            print(f"📈 Validation Score: {validation_score:.2f}")
            
        except Exception as e:
            result["errors"].append(f"Scenario execution failed: {str(e)}")
            print(f"❌ Scenario failed: {e}")
        
        finally:
            # Cleanup
            print("🧹 Cleaning up chaos scenario...")
            for cmd in scenario.cleanup_commands:
                if cmd.strip():  # Skip empty commands
                    self.run_command(cmd)
            
            # Wait for cleanup
            time.sleep(5)
        
        result["end_time"] = datetime.now().isoformat()
        return result
    
    def collect_kubectl_data(self) -> Dict:
        """Collect baseline kubectl data for comparison"""
        kubectl_data = {}
        
        commands = [
            f"kubectl get pods -n {self.namespace} -o json",
            f"kubectl get events -n {self.namespace} -o json",
            f"kubectl get services -n {self.namespace} -o json",
            f"kubectl get pvc -n {self.namespace} -o json",
            "kubectl get nodes -o json",
            "kubectl top nodes --no-headers",
            f"kubectl top pods -n {self.namespace} --no-headers",
        ]
        
        for cmd in commands:
            try:
                code, stdout, stderr = self.run_command(cmd)
                key = cmd.split()[-2] if "-o" in cmd else cmd.split()[-1]
                kubectl_data[key] = {
                    "command": cmd,
                    "returncode": code,
                    "stdout": stdout,
                    "stderr": stderr
                }
                if code == 0 and stdout.strip().startswith('{'):
                    try:
                        kubectl_data[key]["json"] = json.loads(stdout)
                    except json.JSONDecodeError:
                        pass
            except Exception as e:
                kubectl_data[cmd] = {"error": str(e)}
        
        return kubectl_data
    
    def collect_kubectl_smart_data(self) -> Dict:
        """Collect kubectl-smart analysis data"""
        smart_data = {}
        
        commands = [
            f"python3 kubectl-smart analyze namespace {self.namespace}",
            f"python3 kubectl-smart analyze cluster -n {self.namespace}",
            f"python3 kubectl-smart events -n {self.namespace} --critical-path",
            f"python3 kubectl-smart analyze namespace {self.namespace} --format=json",
        ]
        
        for cmd in commands:
            try:
                code, stdout, stderr = self.run_command(cmd, timeout=60)
                key = cmd.split()[-1] if not cmd.endswith("--format=json") else "namespace_json"
                smart_data[key] = {
                    "command": cmd,
                    "returncode": code,
                    "stdout": stdout,
                    "stderr": stderr
                }
                if code == 0 and cmd.endswith("--format=json"):
                    try:
                        smart_data[key]["json"] = json.loads(stdout)
                    except json.JSONDecodeError:
                        pass
            except Exception as e:
                smart_data[cmd] = {"error": str(e)}
        
        return smart_data
    
    def validate_scenario_expectations(self, scenario: ChaosScenario, 
                                     smart_data: Dict, kubectl_data: Dict) -> float:
        """Validate that kubectl-smart detected the chaos correctly"""
        score = 0.0
        total_checks = len(scenario.expected_kubectl_smart_behaviors)
        
        if total_checks == 0:
            return 1.0
        
        # Get the namespace analysis JSON if available
        namespace_analysis = smart_data.get("namespace_json", {}).get("json", {})
        
        for expectation in scenario.expected_kubectl_smart_behaviors:
            if self.check_expectation(expectation, smart_data, kubectl_data, namespace_analysis):
                score += 1.0
        
        return score / total_checks
    
    def check_expectation(self, expectation: str, smart_data: Dict, 
                         kubectl_data: Dict, namespace_analysis: Dict) -> bool:
        """Check if a specific expectation is met"""
        expectation_lower = expectation.lower()
        
        # Check in smart analysis output
        for key, data in smart_data.items():
            stdout = data.get("stdout", "").lower()
            
            # Check for various expectation patterns
            if "critical" in expectation_lower and "critical" in stdout:
                return True
            if "failed" in expectation_lower and ("failed" in stdout or "error" in stdout):
                return True
            if "imagepullbackoff" in expectation_lower and "imagepullbackoff" in stdout:
                return True
            if "pending" in expectation_lower and "pending" in stdout:
                return True
            if "schedule" in expectation_lower and "schedul" in stdout:
                return True
            if "restart" in expectation_lower and "restart" in stdout:
                return True
            if "memory" in expectation_lower and "memory" in stdout:
                return True
            if "storage" in expectation_lower and ("storage" in stdout or "pvc" in stdout):
                return True
            if "endpoint" in expectation_lower and "endpoint" in stdout:
                return True
            if "health" in expectation_lower and "health" in stdout:
                return True
            if "recommend" in expectation_lower and ("recommend" in stdout or "💡" in stdout):
                return True
        
        # Check namespace analysis JSON for specific metrics
        if namespace_analysis:
            summary = namespace_analysis.get("summary", {})
            if "health" in expectation_lower:
                health_pct = summary.get("health_percentage", 100)
                if health_pct < 100:  # Detected unhealthy state
                    return True
            if "critical" in expectation_lower:
                critical_events = summary.get("critical_events", 0)
                if critical_events > 0:  # Detected critical events
                    return True
        
        return False
    
    def generate_test_report(self, results: List[Dict]) -> str:
        """Generate comprehensive test report"""
        total_scenarios = len(results)
        successful_scenarios = len([r for r in results if r["success"]])
        
        report = f"""
🎯 KUBECTL-SMART CHAOS MONKEY TEST REPORT
==========================================

📊 SUMMARY
----------
Total Scenarios: {total_scenarios}
Successful: {successful_scenarios}
Failed: {total_scenarios - successful_scenarios}
Success Rate: {(successful_scenarios/total_scenarios)*100:.1f}%

Test Duration: {datetime.now() - self.test_start_time}

🌪️ CHAOS SCENARIOS TESTED
--------------------------
"""
        
        for result in results:
            status = "✅ PASS" if result["success"] else "❌ FAIL"
            score = result.get("validation_score", 0)
            report += f"{status} {result['scenario']} (Score: {score:.2f})\n"
            report += f"   Type: {result['chaos_type']}\n"
            report += f"   Description: {result['description']}\n"
            
            if result.get("errors"):
                report += f"   Errors: {'; '.join(result['errors'])}\n"
            report += "\n"
        
        report += """
🔍 DETAILED ANALYSIS
-------------------
"""
        
        for result in results:
            report += f"\n--- {result['scenario'].upper()} ---\n"
            
            # kubectl-smart output summary
            smart_data = result.get("kubectl_smart_output", {})
            for key, data in smart_data.items():
                if data.get("returncode") == 0:
                    stdout = data.get("stdout", "")
                    if stdout and len(stdout) < 500:  # Include short outputs
                        report += f"kubectl-smart {key}:\n{stdout}\n\n"
        
        return report
    
    def run_chaos_tests(self):
        """Main method to run all chaos tests"""
        print("🐒 KUBECTL-SMART CHAOS MONKEY TESTING")
        print("======================================")
        print("🎯 Testing kubectl-smart against Netflix Chaos Monkey-style scenarios")
        print("")
        
        try:
            # Setup test environment
            self.setup_test_environment()
            
            # Generate chaos scenarios
            scenarios = self.generate_chaos_scenarios()
            print(f"🧪 Generated {len(scenarios)} chaos scenarios")
            
            # Execute each scenario
            for i, scenario in enumerate(scenarios, 1):
                print(f"\n🔥 EXECUTING SCENARIO {i}/{len(scenarios)}")
                print("=" * 50)
                
                result = self.execute_chaos_scenario(scenario)
                self.results.append(result)
                
                # Brief pause between scenarios
                time.sleep(10)
            
            # Generate and save report
            report = self.generate_test_report(self.results)
            
            # Save to file
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            report_file = f"chaos_test_report_{timestamp}.txt"
            with open(report_file, "w") as f:
                f.write(report)
            
            print(f"\n📋 Full report saved to: {report_file}")
            print("\n" + "="*60)
            print(report)
            
        except KeyboardInterrupt:
            print("\n🛑 Test interrupted by user")
        except Exception as e:
            print(f"\n💥 Test framework error: {e}")
        finally:
            # Always cleanup
            self.cleanup_test_environment()

def main():
    """Main entry point"""
    if len(sys.argv) > 1 and sys.argv[1] == "--help":
        print(__doc__)
        return
    
    tester = ChaosMonkeyTester()
    tester.run_chaos_tests()

if __name__ == "__main__":
    main()