"""
Multi-Agent Framework for AIOps
Base classes and coordination logic for agent orchestration
"""

import json
import boto3
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any
from datetime import datetime
from enum import Enum


class AgentType(Enum):
    """Agent type enumeration"""
    TRIAGE = "triage"
    TELEMETRY = "telemetry"
    REMEDIATION = "remediation"
    RISK = "risk"
    COMMUNICATIONS = "comms"


class AgentPriority(Enum):
    """Agent execution priority"""
    CRITICAL = 1
    HIGH = 2
    MEDIUM = 3
    LOW = 4


class AgentStatus(Enum):
    """Agent execution status"""
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


class BaseAgent(ABC):
    """
    Abstract base class for all AIOps agents
    All agents must implement analyze() and execute() methods
    """
    
    def __init__(self, correlation_id: str, config: Dict[str, Any] = None):
        self.correlation_id = correlation_id
        self.config = config or {}
        self.status = AgentStatus.PENDING
        self.result = {}
        self.error = None
        self.start_time = None
        self.end_time = None
        
        # AWS clients
        self.bedrock = boto3.client('bedrock-runtime')
        self.dynamodb = boto3.client('dynamodb')
        self.cloudwatch = boto3.client('cloudwatch')
        self.logs = boto3.client('logs')
        
    @property
    @abstractmethod
    def agent_type(self) -> AgentType:
        """Return the agent type"""
        pass
    
    @property
    @abstractmethod
    def priority(self) -> AgentPriority:
        """Return the agent priority"""
        pass
    
    @abstractmethod
    def analyze(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analyze the incident and return insights
        
        Args:
            context: Incident context including event details, resource info, etc.
            
        Returns:
            Dict with analysis results
        """
        pass
    
    @abstractmethod
    def execute(self, context: Dict[str, Any], analysis: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute agent-specific actions based on analysis
        
        Args:
            context: Incident context
            analysis: Results from analyze() method
            
        Returns:
            Dict with execution results
        """
        pass
    
    def run(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Main execution method - orchestrates analyze and execute
        
        Args:
            context: Incident context
            
        Returns:
            Dict with complete agent results
        """
        self.start_time = datetime.utcnow()
        self.status = AgentStatus.RUNNING
        
        try:
            self.log("INFO", f"{self.agent_type.value} agent starting")
            
            # Analyze phase
            analysis = self.analyze(context)
            
            # Execute phase
            execution = self.execute(context, analysis)
            
            # Combine results
            self.result = {
                'agent_type': self.agent_type.value,
                'status': AgentStatus.SUCCESS.value,
                'analysis': analysis,
                'execution': execution,
                'duration_seconds': (datetime.utcnow() - self.start_time).total_seconds()
            }
            
            self.status = AgentStatus.SUCCESS
            self.log("INFO", f"{self.agent_type.value} agent completed successfully")
            
            return self.result
            
        except Exception as e:
            self.status = AgentStatus.FAILED
            self.error = str(e)
            self.result = {
                'agent_type': self.agent_type.value,
                'status': AgentStatus.FAILED.value,
                'error': str(e),
                'duration_seconds': (datetime.utcnow() - self.start_time).total_seconds()
            }
            
            self.log("ERROR", f"{self.agent_type.value} agent failed: {e}")
            
            return self.result
        
        finally:
            self.end_time = datetime.utcnow()
    
    def log(self, level: str, message: str, **kwargs):
        """Structured logging"""
        log_entry = {
            'timestamp': datetime.utcnow().isoformat(),
            'level': level,
            'agent_type': self.agent_type.value,
            'correlation_id': self.correlation_id,
            'message': message,
            **kwargs
        }
        print(json.dumps(log_entry))
    
    def invoke_bedrock(self, prompt: str, max_tokens: int = 1024, temperature: float = 0.1) -> str:
        """
        Helper method to invoke Bedrock (Claude 3 Haiku)
        
        Args:
            prompt: The prompt to send to Bedrock
            max_tokens: Maximum tokens in response
            temperature: Temperature for generation
            
        Returns:
            LLM response text
        """
        # Amazon Titan Express Configuration
        body = json.dumps({
            "inputText": prompt,
            "textGenerationConfig": {
                "maxTokenCount": max_tokens,
                "stopSequences": [],
                "temperature": temperature,
                "topP": 0.9
            }
        })
        
        try:
            response = self.bedrock.invoke_model(
                modelId="amazon.titan-text-express-v1",
                body=body,
                contentType="application/json",
                accept="application/json"
            )
            
            response_body = json.loads(response.get('body').read())
            return response_body.get('results')[0].get('outputText').strip()
            
        except Exception as e:
            self.log("ERROR", f"Error invoking Bedrock: {e}")
            return "Error generating response from AI model."


class AgentRegistry:
    """
    Registry for managing available agents
    """
    
    def __init__(self):
        self._agents = {}
    
    def register(self, agent_class):
        """Register an agent class"""
        # Create a temporary instance to get agent_type
        temp_instance = agent_class(correlation_id="temp", config={})
        self._agents[temp_instance.agent_type] = agent_class
        return agent_class
    
    def get_agent(self, agent_type: AgentType, correlation_id: str, config: Dict[str, Any] = None):
        """Get an agent instance by type"""
        agent_class = self._agents.get(agent_type)
        if not agent_class:
            raise ValueError(f"Agent type {agent_type} not registered")
        return agent_class(correlation_id=correlation_id, config=config)
    
    def list_agents(self) -> List[AgentType]:
        """List all registered agent types"""
        return list(self._agents.keys())


class AgentCoordinator:
    """
    Coordinates execution of multiple agents
    Manages dependencies, priorities, and workflow
    """
    
    def __init__(self, correlation_id: str, registry: AgentRegistry):
        self.correlation_id = correlation_id
        self.registry = registry
        self.results = {}
        self.execution_order = []
        
    def orchestrate(
        self,
        context: Dict[str, Any],
        agent_types: List[AgentType],
        config: Dict[AgentType, Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Orchestrate execution of multiple agents
        
        Args:
            context: Incident context
            agent_types: List of agent types to execute
            config: Per-agent configuration
            
        Returns:
            Dict with all agent results
        """
        config = config or {}
        
        # Sort agents by priority
        agents = []
        for agent_type in agent_types:
            agent_config = config.get(agent_type, {})
            agent = self.registry.get_agent(agent_type, self.correlation_id, agent_config)
            agents.append(agent)
        
        agents.sort(key=lambda a: a.priority.value)
        
        self.log("INFO", f"Orchestrating {len(agents)} agents")
        
        # Execute agents in priority order
        for agent in agents:
            self.log("INFO", f"Executing {agent.agent_type.value} agent")
            
            # Add previous results to context
            enhanced_context = {
                **context,
                'previous_agent_results': self.results
            }
            
            # Run agent
            result = agent.run(enhanced_context)
            
            # Store result
            self.results[agent.agent_type.value] = result
            self.execution_order.append(agent.agent_type.value)
            
            # Check if agent failed critically
            if result.get('status') == AgentStatus.FAILED.value:
                critical_failure = result.get('critical_failure', False)
                if critical_failure:
                    self.log("ERROR", f"Critical failure in {agent.agent_type.value} agent, stopping orchestration")
                    break
        
        return {
            'correlation_id': self.correlation_id,
            'execution_order': self.execution_order,
            'agent_results': self.results,
            'total_agents': len(agents),
            'successful_agents': sum(1 for r in self.results.values() if r.get('status') == AgentStatus.SUCCESS.value),
            'failed_agents': sum(1 for r in self.results.values() if r.get('status') == AgentStatus.FAILED.value)
        }
    
    def log(self, level: str, message: str, **kwargs):
        """Structured logging"""
        log_entry = {
            'timestamp': datetime.utcnow().isoformat(),
            'level': level,
            'component': 'AgentCoordinator',
            'correlation_id': self.correlation_id,
            'message': message,
            **kwargs
        }
        print(json.dumps(log_entry))


# Global registry instance
agent_registry = AgentRegistry()
