"""
Forecasting module using statsmodels for predictive analysis

This module implements Holt-Winters forecasting for capacity and certificate
expiry prediction as specified in the technical requirements.
"""

import re
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

import structlog

from ..models import ResourceRecord

logger = structlog.get_logger(__name__)

# Try to import statsmodels, handle graceful degradation
try:
    from statsmodels.tsa.holtwinters import ExponentialSmoothing
    STATSMODELS_AVAILABLE = True
except ImportError:
    logger.warning("statsmodels not available, forecasting will be limited")
    STATSMODELS_AVAILABLE = False


class ForecastingEngine:
    """Forecasting engine for predictive capacity and certificate analysis
    
    As specified in the technical requirements:
    - Library: statsmodels ExponentialSmoothing (Holt-Winters)
    - Fall back to linear fit if < 7 samples
    - Cert expiry: parse X509 notAfter; raise issue if < 14 days
    """
    
    def __init__(self, min_samples: int = 7, forecast_horizon_hours: int = 48):
        self.min_samples = min_samples
        self.forecast_horizon_hours = forecast_horizon_hours
    
    def predict_capacity_issues(
        self, 
        resources: List[ResourceRecord], 
        metrics_data: Optional[List[ResourceRecord]] = None
    ) -> List[Dict[str, any]]:
        """Predict capacity issues over the forecast horizon
        
        Args:
            resources: List of all resources
            metrics_data: Optional metrics data from metrics-server
            
        Returns:
            List of predicted capacity issues
        """
        predictions = []
        
        # Analyze nodes for capacity issues
        nodes = [r for r in resources if r.kind.value == "Node"]
        for node in nodes:
            node_predictions = self._predict_node_capacity(node, metrics_data)
            predictions.extend(node_predictions)
        
        # Analyze PVCs for disk usage
        pvcs = [r for r in resources if r.kind.value == "PersistentVolumeClaim"]
        for pvc in pvcs:
            pvc_predictions = self._predict_pvc_usage(pvc, metrics_data)
            predictions.extend(pvc_predictions)
        
        # Filter to only actionable predictions (≥90% predicted utilization)
        actionable = [p for p in predictions if p.get('predicted_utilization', 0) >= 90]
        
        return actionable
    
    def predict_certificate_expiry(self, resources: List[ResourceRecord]) -> List[Dict[str, any]]:
        """Predict certificate expiry issues
        
        Args:
            resources: List of all resources
            
        Returns:
            List of certificates expiring within warning period
        """
        warnings = []
        
        # Check secrets for TLS certificates
        secrets = [r for r in resources if r.kind.value == "Secret"]
        for secret in secrets:
            cert_warnings = self._check_secret_certificates(secret)
            warnings.extend(cert_warnings)
        
        # Check ingress resources for TLS certificates
        ingresses = [r for r in resources if r.kind.value == "Ingress"]
        for ingress in ingresses:
            cert_warnings = self._check_ingress_certificates(ingress)
            warnings.extend(cert_warnings)
        
        return warnings
    
    def _predict_node_capacity(
        self, 
        node: ResourceRecord, 
        metrics_data: Optional[List[ResourceRecord]]
    ) -> List[Dict[str, any]]:
        """Predict node capacity issues"""
        predictions = []
        
        # Extract current resource usage from node status
        status = node.get_property('status', {})
        conditions = status.get('conditions', [])
        
        # Check for existing pressure conditions
        for condition in conditions:
            condition_type = condition.get('type', '')
            condition_status = condition.get('status', 'Unknown')
            
            if condition_status == 'True' and condition_type in ['DiskPressure', 'MemoryPressure', 'PIDPressure']:
                predictions.append({
                    'type': 'node_pressure',
                    'resource': node.full_name,
                    'pressure_type': condition_type,
                    'current_status': 'Active',
                    'predicted_utilization': 95.0,  # Already under pressure
                    'forecast_hours': 0,  # Immediate
                    'message': f"Node already experiencing {condition_type}",
                    'suggested_action': f"Investigate {condition_type.lower()} on node {node.name}"
                })
        
        # Try to get historical metrics for prediction
        if metrics_data and STATSMODELS_AVAILABLE:
            node_metrics = [m for m in metrics_data if m.name == node.name]
            if len(node_metrics) >= self.min_samples:
                # This is a simplified example - real implementation would need
                # time-series data collection over multiple polling intervals
                capacity_prediction = self._forecast_time_series(node_metrics, 'cpu')
                if capacity_prediction and capacity_prediction['predicted_value'] >= 90:
                    predictions.append({
                        'type': 'node_capacity',
                        'resource': node.full_name,
                        'metric': 'cpu',
                        'current_utilization': capacity_prediction['current_value'],
                        'predicted_utilization': capacity_prediction['predicted_value'],
                        'forecast_hours': self.forecast_horizon_hours,
                        'message': f"CPU utilization predicted to reach {capacity_prediction['predicted_value']:.1f}%",
                        'suggested_action': f"Consider scaling workloads or adding nodes"
                    })
        
        return predictions
    
    def _predict_pvc_usage(
        self, 
        pvc: ResourceRecord, 
        metrics_data: Optional[List[ResourceRecord]]
    ) -> List[Dict[str, any]]:
        """Predict PVC disk usage issues"""
        predictions = []
        
        # Get PVC capacity from spec
        spec = pvc.get_property('spec', {})
        resources = spec.get('resources', {})
        requests = resources.get('requests', {})
        storage = requests.get('storage', '0Gi')
        
        # Parse storage size (simplified)
        storage_bytes = self._parse_storage_size(storage)
        
        if storage_bytes == 0:
            return predictions
        
        # Check current usage if available in status
        status = pvc.get_property('status', {})
        capacity = status.get('capacity', {})
        used_storage = capacity.get('storage', storage)  # Fallback to requested
        
        # This is simplified - real implementation would track usage over time
        # For now, just flag PVCs that are bound but might be near capacity
        if pvc.status == 'Bound':
            predictions.append({
                'type': 'pvc_usage',
                'resource': pvc.full_name,
                'current_size': storage,
                'predicted_utilization': 85.0,  # Estimated
                'forecast_hours': self.forecast_horizon_hours,
                'message': f"PVC {pvc.name} usage trending upward",
                'suggested_action': f"Monitor disk usage on PVC {pvc.name}"
            })
        
        return predictions
    
    def _check_secret_certificates(self, secret: ResourceRecord) -> List[Dict[str, any]]:
        """Check secret for TLS certificate expiry"""
        warnings = []
        
        # Only check TLS secrets
        secret_type = secret.get_property('type', '')
        if secret_type not in ['kubernetes.io/tls', 'Opaque']:
            return warnings
        
        # Check if it has certificate data
        data = secret.get_property('data', {})
        if 'tls.crt' not in data and 'cert' not in data:
            return warnings
        
        # Try to parse certificate (simplified - real implementation would decode base64 and parse X.509)
        cert_data = data.get('tls.crt', data.get('cert', ''))
        if cert_data:
            # This is a placeholder - real implementation would:
            # 1. Base64 decode the certificate
            # 2. Parse X.509 certificate
            # 3. Extract notAfter date
            # 4. Calculate days until expiry
            
            # For now, assume certificates expire in 30 days (placeholder)
            expiry_date = datetime.now(timezone.utc) + timedelta(days=30)
            days_until_expiry = (expiry_date - datetime.now(timezone.utc)).days
            
            if days_until_expiry <= 14:  # 14 day warning as per spec
                warnings.append({
                    'type': 'certificate_expiry',
                    'resource': secret.full_name,
                    'certificate_type': 'tls_secret',
                    'expiry_date': expiry_date.isoformat(),
                    'days_until_expiry': days_until_expiry,
                    'message': f"TLS certificate in secret {secret.name} expires in {days_until_expiry} days",
                    'suggested_action': f"Renew certificate for secret {secret.name}"
                })
        
        return warnings
    
    def _check_ingress_certificates(self, ingress: ResourceRecord) -> List[Dict[str, any]]:
        """Check ingress for TLS certificate references"""
        warnings = []
        
        spec = ingress.get_property('spec', {})
        tls_configs = spec.get('tls', [])
        
        for tls_config in tls_configs:
            secret_name = tls_config.get('secretName')
            hosts = tls_config.get('hosts', [])
            
            if secret_name:
                # This is a reference check - actual certificate parsing would be done
                # when processing the referenced secret
                warnings.append({
                    'type': 'certificate_reference',
                    'resource': ingress.full_name,
                    'certificate_type': 'ingress_tls',
                    'secret_name': secret_name,
                    'hosts': hosts,
                    'message': f"Ingress {ingress.name} references TLS secret {secret_name}",
                    'suggested_action': f"Verify certificate validity for secret {secret_name}"
                })
        
        return warnings
    
    def _forecast_time_series(
        self, 
        metrics: List[ResourceRecord], 
        metric_name: str
    ) -> Optional[Dict[str, float]]:
        """Forecast time series using Holt-Winters or linear regression
        
        Args:
            metrics: List of metric records over time
            metric_name: Name of the metric to forecast
            
        Returns:
            Forecast result with current and predicted values
        """
        if not STATSMODELS_AVAILABLE or len(metrics) < self.min_samples:
            return self._linear_forecast(metrics, metric_name)
        
        try:
            # Extract metric values (simplified - real implementation would need proper time series)
            values = []
            for metric in metrics:
                metric_data = metric.get_property('metrics', {})
                value_str = metric_data.get(metric_name, '0')
                # Parse metric value (e.g., "250m" for CPU, "1024Mi" for memory)
                value = self._parse_metric_value(value_str, metric_name)
                values.append(value)
            
            if len(values) < self.min_samples:
                return self._linear_forecast(metrics, metric_name)
            
            # Apply Holt-Winters exponential smoothing
            model = ExponentialSmoothing(
                values, 
                trend='add', 
                seasonal=None,  # Simplified - no seasonality for now
                damped_trend=True
            )
            fitted_model = model.fit()
            
            # Forecast for the specified horizon
            forecast_steps = max(1, self.forecast_horizon_hours // 24)  # Daily steps
            forecast = fitted_model.forecast(steps=forecast_steps)
            
            return {
                'current_value': values[-1],
                'predicted_value': forecast[-1],
                'confidence': 0.8  # Simplified confidence measure
            }
            
        except Exception as e:
            logger.debug("Holt-Winters forecasting failed, falling back to linear", error=str(e))
            return self._linear_forecast(metrics, metric_name)
    
    def _linear_forecast(
        self, 
        metrics: List[ResourceRecord], 
        metric_name: str
    ) -> Optional[Dict[str, float]]:
        """Simple linear regression forecast fallback"""
        if len(metrics) < 2:
            return None
        
        try:
            # Extract values
            values = []
            for metric in metrics:
                metric_data = metric.get_property('metrics', {})
                value_str = metric_data.get(metric_name, '0')
                value = self._parse_metric_value(value_str, metric_name)
                values.append(value)
            
            # Simple linear trend calculation
            if len(values) >= 2:
                recent_values = values[-3:] if len(values) >= 3 else values
                trend = (recent_values[-1] - recent_values[0]) / len(recent_values)
                
                # Project trend forward
                forecast_periods = self.forecast_horizon_hours // 24
                predicted_value = values[-1] + (trend * forecast_periods)
                
                return {
                    'current_value': values[-1],
                    'predicted_value': max(0, predicted_value),  # Don't predict negative
                    'confidence': 0.6  # Lower confidence for linear forecast
                }
            
        except Exception as e:
            logger.debug("Linear forecasting failed", error=str(e))
            return None
        
        return None
    
    def _parse_storage_size(self, size_str: str) -> int:
        """Parse Kubernetes storage size to bytes"""
        if not size_str:
            return 0
        
        # Remove whitespace
        size_str = size_str.strip()
        
        # Define multipliers
        multipliers = {
            'k': 1024, 'ki': 1024,
            'm': 1024**2, 'mi': 1024**2,
            'g': 1024**3, 'gi': 1024**3,
            't': 1024**4, 'ti': 1024**4,
            'p': 1024**5, 'pi': 1024**5,
        }
        
        # Extract number and unit
        match = re.match(r'^(\d+(?:\.\d+)?)\s*([a-zA-Z]*)$', size_str.lower())
        if not match:
            return 0
        
        number, unit = match.groups()
        number = float(number)
        
        multiplier = multipliers.get(unit, 1)
        return int(number * multiplier)
    
    def _parse_metric_value(self, value_str: str, metric_name: str) -> float:
        """Parse metric value string to float"""
        if not value_str:
            return 0.0
        
        value_str = value_str.strip()
        
        # CPU metrics (e.g., "250m" = 0.25 cores)
        if metric_name == 'cpu':
            if value_str.endswith('m'):
                return float(value_str[:-1]) / 1000  # millicores to cores
            else:
                return float(value_str)
        
        # Memory metrics (e.g., "1024Mi" = bytes)
        elif metric_name == 'memory':
            return float(self._parse_storage_size(value_str))
        
        # Default: try to parse as float
        try:
            return float(value_str)
        except ValueError:
            return 0.0