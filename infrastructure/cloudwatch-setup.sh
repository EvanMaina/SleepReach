#!/bin/bash
# =============================================================================
# SleepReach — CloudWatch Dashboard & Alarms Setup
#
# Run with: AWS_PROFILE=sleepreach bash infrastructure/cloudwatch-setup.sh
#
# Prerequisites:
#   - AWS CLI configured with appropriate credentials
#   - SNS topic: sleepreach-production-alerts must exist
# =============================================================================

set -euo pipefail

AWS_REGION="us-east-2"
ACCOUNT_ID="131880217305"
ALB_SUFFIX="app/neuroreach-ai-alb/09820aa0f84e6f0b"
TG_PROD_BACKEND="targetgroup/sleepreach-prod-backend/ad4c08bb1ac8d351"
TG_PROD_FRONTEND="targetgroup/sleepreach-prod-frontend/c5ff88f7e32bd4ad"
SNS_TOPIC="arn:aws:sns:${AWS_REGION}:${ACCOUNT_ID}:sleepreach-production-alerts"
ECS_CLUSTER="sleepreach-cluster"

echo "🔧 Setting up CloudWatch Dashboard & Alarms for SleepReach..."
echo "   Region: ${AWS_REGION}"
echo "   SNS Topic: ${SNS_TOPIC}"
echo ""

# =============================================================================
# 1. Create CloudWatch Dashboard
# =============================================================================
echo "📊 Creating CloudWatch Dashboard..."

aws cloudwatch put-dashboard \
  --dashboard-name "SleepReach-Production" \
  --dashboard-body '{
    "widgets": [
      {
        "type": "text",
        "x": 0, "y": 0, "width": 24, "height": 1,
        "properties": {
          "markdown": "# SleepReach Production Dashboard\n**Cluster:** sleepreach-cluster | **ALB:** neuroreach-ai-alb | **Region:** us-east-2"
        }
      },
      {
        "type": "metric",
        "x": 0, "y": 1, "width": 12, "height": 6,
        "properties": {
          "title": "ECS Service - CPU Utilization",
          "metrics": [
            ["AWS/ECS", "CPUUtilization", "ClusterName", "sleepreach-cluster", "ServiceName", "sleepreach-prod-backend", {"label": "Prod Backend"}],
            ["...", "sleepreach-prod-celery", {"label": "Prod Celery"}],
            ["...", "sleepreach-prod-frontend", {"label": "Prod Frontend"}],
            ["...", "sleepreach-stg-backend", {"label": "Stg Backend", "stat": "Average"}],
            ["...", "sleepreach-stg-frontend", {"label": "Stg Frontend", "stat": "Average"}]
          ],
          "period": 300,
          "stat": "Average",
          "region": "us-east-2",
          "view": "timeSeries",
          "stacked": false
        }
      },
      {
        "type": "metric",
        "x": 12, "y": 1, "width": 12, "height": 6,
        "properties": {
          "title": "ECS Service - Memory Utilization",
          "metrics": [
            ["AWS/ECS", "MemoryUtilization", "ClusterName", "sleepreach-cluster", "ServiceName", "sleepreach-prod-backend", {"label": "Prod Backend"}],
            ["...", "sleepreach-prod-celery", {"label": "Prod Celery"}],
            ["...", "sleepreach-prod-frontend", {"label": "Prod Frontend"}],
            ["...", "sleepreach-stg-backend", {"label": "Stg Backend"}],
            ["...", "sleepreach-stg-frontend", {"label": "Stg Frontend"}]
          ],
          "period": 300,
          "stat": "Average",
          "region": "us-east-2",
          "view": "timeSeries",
          "stacked": false
        }
      },
      {
        "type": "metric",
        "x": 0, "y": 7, "width": 12, "height": 6,
        "properties": {
          "title": "ALB - Request Count & Errors",
          "metrics": [
            ["AWS/ApplicationELB", "RequestCount", "LoadBalancer", "app/neuroreach-ai-alb/09820aa0f84e6f0b", {"label": "Total Requests", "stat": "Sum"}],
            [".", "HTTPCode_Target_5XX_Count", ".", ".", {"label": "5XX Errors", "stat": "Sum", "color": "#d62728"}],
            [".", "HTTPCode_Target_4XX_Count", ".", ".", {"label": "4XX Errors", "stat": "Sum", "color": "#ff7f0e"}]
          ],
          "period": 300,
          "region": "us-east-2",
          "view": "timeSeries",
          "stacked": false
        }
      },
      {
        "type": "metric",
        "x": 12, "y": 7, "width": 12, "height": 6,
        "properties": {
          "title": "ALB - Response Time (p50, p95, p99)",
          "metrics": [
            ["AWS/ApplicationELB", "TargetResponseTime", "LoadBalancer", "app/neuroreach-ai-alb/09820aa0f84e6f0b", {"label": "p50", "stat": "p50"}],
            ["...", {"label": "p95", "stat": "p95", "color": "#ff7f0e"}],
            ["...", {"label": "p99", "stat": "p99", "color": "#d62728"}]
          ],
          "period": 300,
          "region": "us-east-2",
          "view": "timeSeries",
          "stacked": false
        }
      },
      {
        "type": "metric",
        "x": 0, "y": 13, "width": 12, "height": 6,
        "properties": {
          "title": "RDS - CPU Utilization",
          "metrics": [
            ["AWS/RDS", "CPUUtilization", "DBInstanceIdentifier", "sleepreach-prod-db", {"label": "Prod DB"}],
            ["...", "sleepreach-stg-db", {"label": "Staging DB"}]
          ],
          "period": 300,
          "stat": "Average",
          "region": "us-east-2",
          "view": "timeSeries",
          "stacked": false
        }
      },
      {
        "type": "metric",
        "x": 12, "y": 13, "width": 12, "height": 6,
        "properties": {
          "title": "RDS - Database Connections",
          "metrics": [
            ["AWS/RDS", "DatabaseConnections", "DBInstanceIdentifier", "sleepreach-prod-db", {"label": "Prod DB Connections"}],
            ["...", "sleepreach-stg-db", {"label": "Staging DB Connections"}]
          ],
          "period": 300,
          "stat": "Average",
          "region": "us-east-2",
          "view": "timeSeries",
          "stacked": false
        }
      },
      {
        "type": "metric",
        "x": 0, "y": 19, "width": 12, "height": 6,
        "properties": {
          "title": "RDS - Free Storage Space (GB)",
          "metrics": [
            ["AWS/RDS", "FreeStorageSpace", "DBInstanceIdentifier", "sleepreach-prod-db", {"label": "Prod DB Free Storage"}],
            ["...", "sleepreach-stg-db", {"label": "Staging DB Free Storage"}]
          ],
          "period": 300,
          "stat": "Average",
          "region": "us-east-2",
          "view": "timeSeries",
          "stacked": false,
          "yAxis": { "left": { "label": "Bytes" } }
        }
      },
      {
        "type": "metric",
        "x": 12, "y": 19, "width": 12, "height": 6,
        "properties": {
          "title": "RDS - Read/Write Latency",
          "metrics": [
            ["AWS/RDS", "ReadLatency", "DBInstanceIdentifier", "sleepreach-prod-db", {"label": "Prod Read Latency"}],
            [".", "WriteLatency", ".", ".", {"label": "Prod Write Latency", "color": "#d62728"}]
          ],
          "period": 300,
          "stat": "Average",
          "region": "us-east-2",
          "view": "timeSeries",
          "stacked": false
        }
      },
      {
        "type": "metric",
        "x": 0, "y": 25, "width": 12, "height": 6,
        "properties": {
          "title": "ElastiCache Redis - CPU",
          "metrics": [
            ["AWS/ElastiCache", "CPUUtilization", "CacheClusterId", "sleepreach-prod-redis-tls-001", {"label": "Prod Redis CPU"}],
            ["...", "sleepreach-stg-redis-tls-001", {"label": "Stg Redis CPU"}]
          ],
          "period": 300,
          "stat": "Average",
          "region": "us-east-2",
          "view": "timeSeries",
          "stacked": false
        }
      },
      {
        "type": "metric",
        "x": 12, "y": 25, "width": 12, "height": 6,
        "properties": {
          "title": "ElastiCache Redis - Memory",
          "metrics": [
            ["AWS/ElastiCache", "DatabaseMemoryUsagePercentage", "CacheClusterId", "sleepreach-prod-redis-tls-001", {"label": "Prod Redis Memory %"}],
            ["...", "sleepreach-stg-redis-tls-001", {"label": "Stg Redis Memory %"}]
          ],
          "period": 300,
          "stat": "Average",
          "region": "us-east-2",
          "view": "timeSeries",
          "stacked": false
        }
      },
      {
        "type": "metric",
        "x": 0, "y": 31, "width": 24, "height": 6,
        "properties": {
          "title": "ECS Running Task Count",
          "metrics": [
            ["ECS/ContainerInsights", "RunningTaskCount", "ClusterName", "sleepreach-cluster", "ServiceName", "sleepreach-prod-backend", {"label": "Prod Backend Tasks"}],
            ["...", "sleepreach-prod-celery", {"label": "Prod Celery Tasks"}],
            ["...", "sleepreach-prod-frontend", {"label": "Prod Frontend Tasks"}],
            ["...", "sleepreach-stg-backend", {"label": "Stg Backend Tasks"}],
            ["...", "sleepreach-stg-frontend", {"label": "Stg Frontend Tasks"}]
          ],
          "period": 60,
          "stat": "Average",
          "region": "us-east-2",
          "view": "timeSeries",
          "stacked": false
        }
      }
    ]
  }' \
  --region ${AWS_REGION} && echo "✅ Dashboard created: SleepReach-Production" || echo "⚠️ Dashboard creation failed"

echo ""

# =============================================================================
# 2. Create CloudWatch Alarms
# =============================================================================
echo "🔔 Creating CloudWatch Alarms..."

# --- ALB 5XX Spike ---
echo "  → Creating alarm: sleepreach-prod-5xx-high..."
aws cloudwatch put-metric-alarm \
  --alarm-name "sleepreach-prod-5xx-high" \
  --alarm-description "SleepReach Production: High 5XX error rate (>10 in 5 min)" \
  --metric-name "HTTPCode_Target_5XX_Count" \
  --namespace "AWS/ApplicationELB" \
  --statistic Sum \
  --period 300 \
  --threshold 10 \
  --comparison-operator GreaterThanThreshold \
  --evaluation-periods 1 \
  --dimensions "Name=LoadBalancer,Value=${ALB_SUFFIX}" \
  --alarm-actions "${SNS_TOPIC}" \
  --ok-actions "${SNS_TOPIC}" \
  --treat-missing-data notBreaching \
  --region ${AWS_REGION} && echo "  ✅ 5XX alarm created" || echo "  ⚠️ 5XX alarm failed"

# --- ALB p99 Latency ---
echo "  → Creating alarm: sleepreach-prod-latency-high..."
aws cloudwatch put-metric-alarm \
  --alarm-name "sleepreach-prod-latency-high" \
  --alarm-description "SleepReach Production: p99 latency > 5s for 5 min" \
  --metric-name "TargetResponseTime" \
  --namespace "AWS/ApplicationELB" \
  --extended-statistic p99 \
  --period 300 \
  --threshold 5 \
  --comparison-operator GreaterThanThreshold \
  --evaluation-periods 1 \
  --dimensions "Name=LoadBalancer,Value=${ALB_SUFFIX}" \
  --alarm-actions "${SNS_TOPIC}" \
  --ok-actions "${SNS_TOPIC}" \
  --treat-missing-data notBreaching \
  --region ${AWS_REGION} && echo "  ✅ Latency alarm created" || echo "  ⚠️ Latency alarm failed"

# --- RDS CPU High ---
echo "  → Creating alarm: sleepreach-prod-rds-cpu-high..."
aws cloudwatch put-metric-alarm \
  --alarm-name "sleepreach-prod-rds-cpu-high" \
  --alarm-description "SleepReach Production DB: CPU > 80% for 10 min" \
  --metric-name "CPUUtilization" \
  --namespace "AWS/RDS" \
  --statistic Average \
  --period 300 \
  --threshold 80 \
  --comparison-operator GreaterThanThreshold \
  --evaluation-periods 2 \
  --dimensions "Name=DBInstanceIdentifier,Value=sleepreach-prod-db" \
  --alarm-actions "${SNS_TOPIC}" \
  --ok-actions "${SNS_TOPIC}" \
  --treat-missing-data missing \
  --region ${AWS_REGION} && echo "  ✅ RDS CPU alarm created" || echo "  ⚠️ RDS CPU alarm failed"

# --- RDS Free Storage Low ---
echo "  → Creating alarm: sleepreach-prod-rds-storage-low..."
aws cloudwatch put-metric-alarm \
  --alarm-name "sleepreach-prod-rds-storage-low" \
  --alarm-description "SleepReach Production DB: Free storage < 1 GB" \
  --metric-name "FreeStorageSpace" \
  --namespace "AWS/RDS" \
  --statistic Average \
  --period 300 \
  --threshold 1073741824 \
  --comparison-operator LessThanThreshold \
  --evaluation-periods 1 \
  --dimensions "Name=DBInstanceIdentifier,Value=sleepreach-prod-db" \
  --alarm-actions "${SNS_TOPIC}" \
  --ok-actions "${SNS_TOPIC}" \
  --treat-missing-data missing \
  --region ${AWS_REGION} && echo "  ✅ RDS storage alarm created" || echo "  ⚠️ RDS storage alarm failed"

# --- Redis Memory High ---
echo "  → Creating alarm: sleepreach-prod-redis-memory-high..."
aws cloudwatch put-metric-alarm \
  --alarm-name "sleepreach-prod-redis-memory-high" \
  --alarm-description "SleepReach Production Redis: Memory > 80%" \
  --metric-name "DatabaseMemoryUsagePercentage" \
  --namespace "AWS/ElastiCache" \
  --statistic Average \
  --period 300 \
  --threshold 80 \
  --comparison-operator GreaterThanThreshold \
  --evaluation-periods 2 \
  --dimensions "Name=CacheClusterId,Value=sleepreach-prod-redis-tls-001" \
  --alarm-actions "${SNS_TOPIC}" \
  --ok-actions "${SNS_TOPIC}" \
  --treat-missing-data missing \
  --region ${AWS_REGION} && echo "  ✅ Redis memory alarm created" || echo "  ⚠️ Redis memory alarm failed"

# --- ECS Backend Task Count Low ---
echo "  → Creating alarm: sleepreach-prod-backend-task-low..."
aws cloudwatch put-metric-alarm \
  --alarm-name "sleepreach-prod-backend-task-low" \
  --alarm-description "SleepReach Production: Backend running task count < 1 for 2 min" \
  --metric-name "CPUUtilization" \
  --namespace "AWS/ECS" \
  --statistic SampleCount \
  --period 60 \
  --threshold 1 \
  --comparison-operator LessThanThreshold \
  --evaluation-periods 2 \
  --dimensions "Name=ClusterName,Value=sleepreach-cluster" "Name=ServiceName,Value=sleepreach-prod-backend" \
  --alarm-actions "${SNS_TOPIC}" \
  --ok-actions "${SNS_TOPIC}" \
  --treat-missing-data breaching \
  --region ${AWS_REGION} && echo "  ✅ Backend task alarm created" || echo "  ⚠️ Backend task alarm failed"

echo ""
echo "🎉 CloudWatch setup complete!"
echo ""
echo "📊 Dashboard URL: https://${AWS_REGION}.console.aws.amazon.com/cloudwatch/home?region=${AWS_REGION}#dashboards:name=SleepReach-Production"
echo "🔔 Alarms: https://${AWS_REGION}.console.aws.amazon.com/cloudwatch/home?region=${AWS_REGION}#alarmsV2:"
