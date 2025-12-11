# Phase 7: Multi-Region Deployment

## Overview

This phase extends the AIOps system to support multi-region deployments with a **Hub-and-Spoke** architecture.

- **Central Region (Hub):** US East 1
  - Hosts the Multi-Agent Brain (Bedrock, Orchestrator)
  - Manages global state
  - Executes reasoning logic

- **Satellite Regions (Spokes):** US West 2, etc.
  - Host "dumb" forwarders (Regional Orchestrators)
  - Collect local events (CloudTrail, EC2 state)
  - Execute local remediation actions (via cross-region calls or local agents - *In Progress*)

## Architecture

```
┌─────────────────────────────┐        ┌─────────────────────────────┐
│   Satellite Region (West)    │        │     Central Region (East)    │
│                             │        │                             │
│  [Event Source]             │        │  [Central Event Bus]        │
│        │                    │        │             ▲               │
│        ▼                    │        │             │               │
│  [EventBridge]              │        │             │               │
│        │                    │        │             │               │
│        ▼                    │        │             │               │
│ [Regional Orchestrator] ────┼────────┼─────────────┘               │
│                             │        │                             │
└─────────────────────────────┘        └─────────────────────────────┘
```

## Deployment

1. **Initialize Terraform:**
   ```bash
   cd phase-7-multi-region
   terraform init
   ```

2. **Deploy Stack:**
   ```bash
   terraform apply
   ```

   This will deploy:
   - Central stack in `us-east-1`
   - Satellite stack in `us-west-2`

## Key Components

- **Regional Orchestrator (`lambda/regional_orchestrator.py`):**
  - Acts as a proxy.
  - Adds `regional_context` block to events.
  - Forwards satellite events to central event bus.
  - Invokes local orchestrator if running in central region.

- **Terraform Module (`modules/regional-stack`):**
  - Reusable module for deploying orchestrator and permissions to any region.
