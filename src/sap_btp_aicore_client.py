"""
SAP BTP AICore client for embeddings and chat completions.

This module provides a Python client for SAP BTP AICore services,
replacing OpenAI dependencies with SAP BTP AICore integration.
"""
import os
import json
import time
import requests
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)

@dataclass
class AICoreChatResponse:
    """Response from SAP BTP AICore chat completion."""
    content: str
    usage: Dict[str, Any]
    model: str

@dataclass
class AICoreEmbeddingResponse:
    """Response from SAP BTP AICore embedding."""
    embeddings: List[List[float]]
    usage: Dict[str, Any]
    model: str

class SAPBTPAICoreClient:
    """
    SAP BTP AICore client for embeddings and chat completions.
    
    This client handles authentication and API calls to SAP BTP AICore services,
    providing embeddings and chat completion functionality.
    """
    
    def __init__(self):
        """Initialize the SAP BTP AICore client."""
        self.base_url = os.getenv("SAP_BTP_AICORE_BASE_URL")
        self.resource_group = os.getenv("SAP_BTP_AICORE_RESOURCE_GROUP", "default")
        self.auth_url = os.getenv("SAP_BTP_AICORE_AUTH_URL")
        self.client_id = os.getenv("SAP_BTP_AICORE_CLIENT_ID")
        self.client_secret = os.getenv("SAP_BTP_AICORE_CLIENT_SECRET")
        
        # Deployment IDs for different services
        self.embedding_deployment_id = os.getenv("SAP_BTP_AICORE_EMBEDDING_DEPLOYMENT_ID")
        self.chat_deployment_id = os.getenv("SAP_BTP_AICORE_CHAT_DEPLOYMENT_ID")
        self.orchestration_deployment_id = os.getenv("SAP_BTP_AICORE_ORCHESTRATION_DEPLOYMENT_ID")
        
        # Model configurations
        self.embedding_model = os.getenv("SAP_BTP_AICORE_EMBEDDING_MODEL", "text-embedding-3-large")
        self.chat_model = os.getenv("SAP_BTP_AICORE_CHAT_MODEL", "gpt-4o")
        
        # Authentication token cache
        self._access_token = None
        self._token_expires_at = 0
        
        self._validate_config()
    
    def _validate_config(self):
        """Validate required configuration."""
        required_vars = [
            "SAP_BTP_AICORE_BASE_URL",
            "SAP_BTP_AICORE_AUTH_URL", 
            "SAP_BTP_AICORE_CLIENT_ID",
            "SAP_BTP_AICORE_CLIENT_SECRET"
        ]
        
        missing_vars = [var for var in required_vars if not os.getenv(var)]
        if missing_vars:
            raise ValueError(f"Missing required environment variables: {', '.join(missing_vars)}")
    
    def _get_access_token(self) -> str:
        """Get or refresh the access token."""
        current_time = time.time()
        
        # Return cached token if still valid (with 5 minute buffer)
        if self._access_token and current_time < (self._token_expires_at - 300):
            return self._access_token
        
        # Request new token
        token_data = {
            "grant_type": "client_credentials",
            "client_id": self.client_id,
            "client_secret": self.client_secret
        }
        
        try:
            response = requests.post(
                f"{self.auth_url}/oauth/token",
                data=token_data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=30
            )
            response.raise_for_status()
            
            token_response = response.json()
            self._access_token = token_response["access_token"]
            expires_in = token_response.get("expires_in", 3600)
            self._token_expires_at = current_time + expires_in
            
            logger.info("Successfully obtained new access token")
            return self._access_token
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to obtain access token: {e}")
            raise Exception(f"Authentication failed: {e}")
    
    def _make_request(self, method: str, endpoint: str, data: Dict[str, Any] = None, max_retries: int = 3) -> Dict[str, Any]:
        """Make authenticated request to SAP BTP AICore."""
        access_token = self._get_access_token()
        
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "AI-Resource-Group": self.resource_group
        }
        
        url = f"{self.base_url}{endpoint}"
        
        for attempt in range(max_retries):
            try:
                if method.upper() == "POST":
                    response = requests.post(url, json=data, headers=headers, timeout=60)
                else:
                    response = requests.get(url, headers=headers, timeout=60)
                
                response.raise_for_status()
                return response.json()
                
            except requests.exceptions.RequestException as e:
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt  # Exponential backoff
                    logger.warning(f"Request failed (attempt {attempt + 1}/{max_retries}): {e}. Retrying in {wait_time}s...")
                    time.sleep(wait_time)
                    
                    # Refresh token on 401 errors
                    if hasattr(e, 'response') and e.response.status_code == 401:
                        self._access_token = None
                        access_token = self._get_access_token()
                        headers["Authorization"] = f"Bearer {access_token}"
                else:
                    logger.error(f"Request failed after {max_retries} attempts: {e}")
                    raise Exception(f"API request failed: {e}")
    
    def create_embeddings(self, texts: List[str], model: str = None) -> AICoreEmbeddingResponse:
        """
        Create embeddings for a list of texts using SAP BTP AICore.
        
        Args:
            texts: List of texts to embed
            model: Model name (optional, uses default if not provided)
            
        Returns:
            AICoreEmbeddingResponse with embeddings and metadata
        """
        if not texts:
            return AICoreEmbeddingResponse(embeddings=[], usage={}, model=model or self.embedding_model)
        
        # Use orchestration service if available, otherwise direct embedding service
        if self.orchestration_deployment_id:
            return self._create_embeddings_orchestration(texts, model)
        elif self.embedding_deployment_id:
            return self._create_embeddings_direct(texts, model)
        else:
            raise ValueError("No embedding deployment configured. Set SAP_BTP_AICORE_EMBEDDING_DEPLOYMENT_ID or SAP_BTP_AICORE_ORCHESTRATION_DEPLOYMENT_ID")
    
    def _create_embeddings_orchestration(self, texts: List[str], model: str = None) -> AICoreEmbeddingResponse:
        """Create embeddings using orchestration service."""
        model_name = model or self.embedding_model
        
        # Handle single text vs batch
        if isinstance(texts, str):
            input_text = texts
        else:
            input_text = texts
        
        payload = {
            "input": {
                "text": input_text
            },
            "config": {
                "modules": {
                    "embeddings": {
                        "model": {
                            "name": model_name,
                            "params": {
                                "dimensions": 1536 if "3-large" in model_name else 1536
                            }
                        }
                    }
                }
            }
        }
        
        # Use the orchestration deployment URL directly
        orchestration_url = f"https://api.ai.internalprod.eu-central-1.aws.ml.hana.ondemand.com/v2/inference/deployments/{self.orchestration_deployment_id}"
        endpoint = f"{orchestration_url}/v2/embeddings"
        
        # Make request directly to orchestration URL
        access_token = self._get_access_token()
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "AI-Resource-Group": self.resource_group
        }
        
        response = requests.post(endpoint, json=payload, headers=headers, timeout=60)
        response.raise_for_status()
        response = response.json()
        
        # Extract embeddings from orchestration response
        if "final_result" in response:
            embeddings_data = response["final_result"]
        else:
            embeddings_data = response
        
        # Handle different response formats
        if "data" in embeddings_data:
            embeddings = [item["embedding"] for item in embeddings_data["data"]]
        elif "embeddings" in embeddings_data:
            embeddings = embeddings_data["embeddings"]
        else:
            # Fallback: assume direct embedding array
            embeddings = [embeddings_data] if not isinstance(embeddings_data[0], list) else embeddings_data
        
        return AICoreEmbeddingResponse(
            embeddings=embeddings,
            usage=embeddings_data.get("usage", {}),
            model=model_name
        )
    
    def _create_embeddings_direct(self, texts: List[str], model: str = None) -> AICoreEmbeddingResponse:
        """Create embeddings using direct embedding service."""
        model_name = model or self.embedding_model
        
        payload = {
            "input": texts,
            "model": model_name
        }
        
        endpoint = f"/v2/inference/deployments/{self.embedding_deployment_id}"
        response = self._make_request("POST", endpoint, payload)
        
        embeddings = [item["embedding"] for item in response["data"]]
        
        return AICoreEmbeddingResponse(
            embeddings=embeddings,
            usage=response.get("usage", {}),
            model=model_name
        )
    
    def create_chat_completion(self, messages: List[Dict[str, str]], model: str = None, temperature: float = 0.3, max_tokens: int = 200) -> AICoreChatResponse:
        """
        Create chat completion using SAP BTP AICore.
        
        Args:
            messages: List of message dictionaries with 'role' and 'content'
            model: Model name (optional, uses default if not provided)
            temperature: Sampling temperature
            max_tokens: Maximum tokens in response
            
        Returns:
            AICoreChatResponse with completion and metadata
        """
        model_name = model or self.chat_model
        
        # Use orchestration service if available, otherwise direct chat service
        if self.orchestration_deployment_id:
            return self._create_chat_completion_orchestration(messages, model_name, temperature, max_tokens)
        elif self.chat_deployment_id:
            return self._create_chat_completion_direct(messages, model_name, temperature, max_tokens)
        else:
            raise ValueError("No chat deployment configured. Set SAP_BTP_AICORE_CHAT_DEPLOYMENT_ID or SAP_BTP_AICORE_ORCHESTRATION_DEPLOYMENT_ID")
    
    def _create_chat_completion_orchestration(self, messages: List[Dict[str, str]], model: str, temperature: float, max_tokens: int) -> AICoreChatResponse:
        """Create chat completion using orchestration service."""
        payload = {
            "messages": messages,
            "config": {
                "modules": {
                    "llm": {
                        "model": {
                            "name": model,
                            "params": {
                                "temperature": temperature,
                                "max_tokens": max_tokens
                            }
                        }
                    }
                }
            }
        }
        
        endpoint = f"/inference/deployments/{self.orchestration_deployment_id}/v2/chat/completions"
        response = self._make_request("POST", endpoint, payload)
        
        # Extract content from orchestration response
        if "final_result" in response:
            chat_data = response["final_result"]
        else:
            chat_data = response
        
        if "choices" in chat_data and len(chat_data["choices"]) > 0:
            content = chat_data["choices"][0]["message"]["content"]
        else:
            content = str(chat_data)
        
        return AICoreChatResponse(
            content=content,
            usage=chat_data.get("usage", {}),
            model=model
        )
    
    def _create_chat_completion_direct(self, messages: List[Dict[str, str]], model: str, temperature: float, max_tokens: int) -> AICoreChatResponse:
        """Create chat completion using direct chat service."""
        payload = {
            "messages": messages,
            "model": model,
            "temperature": temperature,
            "max_tokens": max_tokens
        }
        
        endpoint = f"/v2/inference/deployments/{self.chat_deployment_id}/chat/completions"
        response = self._make_request("POST", endpoint, payload)
        
        content = response["choices"][0]["message"]["content"]
        
        return AICoreChatResponse(
            content=content,
            usage=response.get("usage", {}),
            model=model
        )

# Global client instance
_aicore_client = None

def get_aicore_client() -> SAPBTPAICoreClient:
    """Get or create the global SAP BTP AICore client instance."""
    global _aicore_client
    if _aicore_client is None:
        _aicore_client = SAPBTPAICoreClient()
    return _aicore_client
