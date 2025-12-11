# Phase 8: Custom ML Models

## Overview

This phase implements custom ML models for pattern recognition, anomaly detection, and threshold optimization.

## Features

### 1. Anomaly Detection
- **Z-score based detection** for metric anomalies
- Configurable sensitivity (default: 2 standard deviations)
- Returns anomaly indices, values, and severity

### 2. Pattern Recognition
- **Resource type distribution** analysis
- **Time-of-day patterns** (hourly distribution)
- **Severity trend** analysis
- **Common error patterns** identification

### 3. Threshold Optimization
- **Percentile-based** threshold calculation (95th percentile)
- Optimizes CPU, error rate, and latency thresholds
- Adapts to historical data

## Deployment

```bash
cd phase-8-ml-models

# Note: You need to create numpy layer first
# Download from: https://github.com/keithrozario/Klayers
# Or build your own

terraform init
terraform apply
```

## Usage

### Detect Anomalies
```python
import boto3
lambda_client = boto3.client('lambda')

response = lambda_client.invoke(
    FunctionName='aiops-ml-models-agent',
    Payload=json.dumps({
        'action': 'detect_anomalies',
        'data': [10, 12, 11, 50, 13, 12],  # 50 is anomaly
        'sensitivity': 2.0
    })
)
```

### Find Patterns
```python
response = lambda_client.invoke(
    FunctionName='aiops-ml-models-agent',
    Payload=json.dumps({
        'action': 'find_patterns',
        'incident_table': 'aiops-incidents',
        'lookback_hours': 24
    })
)
```

### Optimize Thresholds
```python
response = lambda_client.invoke(
    FunctionName='aiops-ml-models-agent',
    Payload=json.dumps({
        'action': 'optimize_thresholds',
        'metric_history': {
            'cpu_utilization': [70, 75, 72, 80, 85],
            'error_rate': [2, 3, 2.5, 4, 3]
        }
    })
)
```

## Automated Pattern Analysis

The system automatically runs pattern analysis **daily** via EventBridge, analyzing:
- Incident distribution by resource type
- Time-of-day patterns
- Severity trends
- Common error patterns

## Future Enhancements

- **SageMaker Integration**: Train custom models on incident data
- **LSTM Models**: For time-series prediction
- **Clustering**: Group similar incidents automatically
- **Forecasting**: Predict future incidents based on patterns
