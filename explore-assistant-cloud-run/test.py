import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from enum import Enum

# import the fastapi main code here
from main import app

client = TestClient(app)

# Enums
class PromptType(str, Enum):
    LOOKER = "looker"
    GENERAL = "general"

# Request Models
class BaseRequest(BaseModel):
    """Base model for requests that require token validation"""
    token: str = Field(..., description="Bearer token for authentication")

class LoginRequest(BaseModel):
    user_id: str = Field(..., description="User ID")
    name: str = Field(..., description="User name")
    email: str = Field(..., description="User email")

class ChatRequest(BaseModel):
    user_id: str = Field(..., description="User ID")
    explore_key: str = Field(..., description="Explore key")

class PromptRequest(BaseModel):
    contents: str = Field(..., description="The prompt contents")
    prompt_type: PromptType = Field(..., description="Type of prompt (looker or general)")
    current_explore_key: str = Field(..., description="Current explore key")
    user_id: str = Field(..., description="User ID")
    parameters: Optional[Dict[str, Any]] = Field(None, description="Optional parameters for the prompt")
    message: Optional[str] = Field("", description="Optional message")
    chat_id: Optional[int] = Field(None, description="Optional chat ID for existing conversations")

class FeedbackRequest(BaseModel):
    user_id: str = Field(..., description="User ID")
    message_id: int = Field(..., description="Message ID")
    feedback_text: str = Field(..., description="Feedback text")
    is_positive: bool = Field(..., description="Whether the feedback is positive")

# Response Models
class BaseResponse(BaseModel):
    """Base model for successful responses"""
    message: str
    data: Dict[str, Any]

class ErrorResponse(BaseModel):
    """Base model for error responses"""
    detail: str

class ChatHistoryResponse(BaseModel):
    data: List[Dict[str, Any]]

@pytest.mark.parametrize(
    "user_id, name, email, token, expected_status, expected_response",
    [
        # Valid looker user & is new user in cloudSQL
        (
            "1", 
            "Test User", 
            "test@example.com", 
            "valid_token",
            200, 
            BaseResponse(
                message="User created successfully",
                data={"user_id": "1", "name": "Test User", "email": "test@example.com"}
            ).model_dump()
        ),
        # Valid looker user & is existing user in cloudSQL
        (
            "2", 
            "Test User", 
            "test@example.com", 
            "valid_token",
            200, 
            BaseResponse(
                message="User already exists",
                data={"user_id": "2", "name": "Test User", "email": "test@example.com"}
            ).model_dump()
        ),
        # Invalid Looker user
        (
            "invalid", 
            "Test User", 
            "test@example.com", 
            "valid_token",
            403, 
            ErrorResponse(detail="User is not a validated Looker user").model_dump()
        ),
        # Invalid token
        (
            "1", 
            "Test User", 
            "test@example.com", 
            "invalid_token",
            403, 
            ErrorResponse(detail="Invalid token").model_dump()
        ),
    ]
)
def test_login_endpoint(user_id, name, email, token, expected_status, expected_response):
    login_request = LoginRequest(user_id=user_id, name=name, email=email)
    
    with \
        patch('main.validate_bearer_token') as mock_validate_bearer_token, \
        patch('main.verify_looker_user') as mock_verify_looker_user, \
        patch('main.get_user_from_db') as mock_get_user_from_db, \
        patch('main.create_new_user') as mock_create_new_user:

        mock_validate_bearer_token.return_value = token == "valid_token"
        mock_verify_looker_user.return_value = user_id != "invalid"

        if user_id == "1":
            mock_get_user_from_db.return_value = None
            mock_create_new_user.return_value = {
                "user_id": "1", "name": "Test User", "email": "test@example.com"
            }
        elif user_id == "2":
            mock_get_user_from_db.return_value = {
                "user_id": "2", "name": "Test User", "email": "test@example.com"
            }

        response = client.post(
            "/login",
            json=login_request.model_dump(),
            headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == expected_status
        assert response.json() == expected_response

@pytest.mark.parametrize(
    "user_id, explore_key, token, expected_status, expected_message",
    [
        # Valid request
        (
            "user1",
            "explore1",
            "valid_token",
            200,
            "Chat created successfully"
        ),
        # Missing parameters
        (
            None,
            "explore1",
            "valid_token",
            400,
            "Missing required parameters"
        ),
        # Invalid token
        (
            "user1",
            "explore1",
            "invalid_token",
            403,
            "Invalid token"
        ),
        # Database error
        (
            "error_user",
            "explore1",
            "valid_token",
            500,
            "Failed to create chat thread"
        ),
    ]
)
def test_create_chat_endpoint(user_id, explore_key, token, expected_status, expected_message):
    with \
        patch('main.validate_bearer_token') as mock_validate_bearer_token, \
        patch('main.create_chat_thread') as mock_create_chat_thread:

        mock_validate_bearer_token.return_value = token == "valid_token"
        
        if user_id == "error_user":
            mock_create_chat_thread.return_value = None
        else:
            mock_create_chat_thread.return_value = 1

        payload = {}
        if user_id:
            payload["user_id"] = user_id
        if explore_key:
            payload["explore_key"] = explore_key

        response = client.post(
            "/chat",
            json=payload,
            headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == expected_status
        if expected_status == 200:
            assert response.json()["message"] == expected_message
            assert "data" in response.json()
        else:
            assert response.json()["detail"] == expected_message

@pytest.mark.parametrize(
    "user_id, chat_id, token, mock_return, expected_status, expected_response",
    [
        # Valid request
        (
            "user1",
            "chat1",
            "valid_token",
            {"data": [{"message_id": 1, "content": "test message"}]},
            200,
            ChatHistoryResponse(data=[{"message_id": 1, "content": "test message"}]).model_dump()
        ),
        # Missing user_id
        (
            None,
            "chat1",
            "valid_token",
            None,
            400,
            {"detail": [{"loc": ["query", "user_id"], "msg": "field required", "type": "Missing required parameters"}]}
        ),
        # Missing chat_id
        (
            "user1",
            None,
            "valid_token",
            None,
            400,
            {"detail": [{"loc": ["query", "chat_id"], "msg": "field required", "type": "Missing required parameters"}]}
        ),
        # Invalid token
        (
            "user1",
            "chat1",
            "invalid_token",
            None,
            403,
            ErrorResponse(detail="Invalid token").model_dump()
        ),
        # Chat history not found
        (
            "user1",
            "nonexistent_chat",
            "valid_token",
            None,  # Simulating no data returned
            404,
            ErrorResponse(detail="Chat history not found").model_dump()
        ),
    ]
)
def test_chat_history_endpoint(user_id, chat_id, token, mock_return, expected_status, expected_response):
    with \
        patch('main.validate_bearer_token') as mock_validate_bearer_token, \
        patch('main.retrieve_chat_history') as mock_retrieve_chat_history:

        mock_validate_bearer_token.return_value = token == "valid_token"
        mock_retrieve_chat_history.return_value = mock_return

        # Only add parameters if they are not None
        params = {}
        if user_id is not None:
            params["user_id"] = user_id
        if chat_id is not None:
            params["chat_id"] = chat_id

        response = client.get(
            "/chat/history",
            params=params,
            headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == expected_status
        if expected_status == 400:
            # For validation errors, we check the error message
            assert response.json()["detail"] == "Missing required parameters"
        else:
            assert response.json() == expected_response

@pytest.mark.parametrize(
    "payload, token, mock_config, expected_status, expected_response",
    [
        # Valid request - looker type
        (
            PromptRequest(
                contents="test query",
                prompt_type=PromptType.LOOKER,
                current_explore_key="explore1",
                user_id="user1",
                parameters={"param": "value"}
            ),
            "valid_token",
            {
                "chat_thread_id": 1,
                "user_message_id": 1,
                "bot_message_id": 2,
                "generated_response": "generated looker response"
            },
            200,
            BaseResponse(
                message="Prompt handled successfully",
                data={
                    "chat_id": 1,
                    "response": "generated looker response"
                }
            ).model_dump()
        ),
        # Valid request - general type
        (
            PromptRequest(
                contents="test query",
                prompt_type=PromptType.GENERAL,
                current_explore_key="explore1",
                user_id="user1"
            ),
            "valid_token",
            {
                "chat_thread_id": 1,
                "user_message_id": 1,
                "bot_message_id": 2,
                "generated_response": "generated general response"
            },
            200,
            BaseResponse(
                message="Prompt handled successfully",
                data={
                    "chat_id": 1,
                    "response": "generated general response"
                }
            ).model_dump()
        ),
        # Valid request with existing chat_id
        (
            PromptRequest(
                contents="test query",
                prompt_type=PromptType.GENERAL,
                current_explore_key="explore1",
                user_id="user1",
                chat_id=123
            ),
            "valid_token",
            {
                "chat_thread_id": 123,
                "user_message_id": 1,
                "bot_message_id": 2,
                "generated_response": "generated response"
            },
            200,
            BaseResponse(
                message="Prompt handled successfully",
                data={
                    "chat_id": 123,
                    "response": "generated response"
                }
            ).model_dump()
        ),
        # Missing required fields
        (
            {"contents": "test query"},
            "valid_token",
            {},
            400,
            ErrorResponse(
                detail="Missing required parameters"
            ).model_dump()
        ),
        # Invalid token
        (
            PromptRequest(
                contents="test query",
                prompt_type=PromptType.LOOKER,
                current_explore_key="explore1",
                user_id="user1"
            ),
            "invalid_token",
            {},
            403,
            ErrorResponse(detail="Invalid token").model_dump()
        ),
    ]
)
def test_prompt_endpoint(payload, token, mock_config, expected_status, expected_response):
    with \
        patch('main.validate_bearer_token') as mock_validate_bearer_token, \
        patch('main.generate_looker_query') as mock_generate_looker_query, \
        patch('main.generate_response') as mock_generate_response, \
        patch('main.create_chat_thread') as mock_create_chat_thread, \
        patch('main.add_message') as mock_add_message:

        # Configure mock responses
        mock_validate_bearer_token.return_value = token == "valid_token"
        
        # Configure chat thread creation
        mock_create_chat_thread.return_value = mock_config.get("chat_thread_id")

        # Configure message creation
        mock_add_message.side_effect = [
            mock_config.get("user_message_id"),
            mock_config.get("bot_message_id")
        ]

        # Configure response generation
        if isinstance(payload, dict):
            request_payload = payload
        else:
            request_payload = payload.model_dump()

        if request_payload.get("prompt_type") == PromptType.LOOKER:
            mock_generate_looker_query.return_value = mock_config.get("generated_response")
        else:
            mock_generate_response.return_value = mock_config.get("generated_response")

        # Make the request
        response = client.post(
            "/prompt",
            json=request_payload,
            headers={"Authorization": f"Bearer {token}"}
        )

        # Verify response
        assert response.status_code == expected_status
        assert response.json() == expected_response

        # Verify mock calls for successful cases
        if expected_status == 200:
            if not request_payload.get("chat_id"):
                mock_create_chat_thread.assert_called_once()
            mock_add_message.assert_called()
            if request_payload.get("prompt_type") == PromptType.LOOKER:
                mock_generate_looker_query.assert_called_once()
            else:
                mock_generate_response.assert_called_once()

@pytest.mark.parametrize(
    "payload, token, expected_status, expected_response",
    [
        # Valid request
        (
            FeedbackRequest(
                user_id="user1",
                message_id=1,
                feedback_text="Great response!",
                is_positive=True
            ),
            "valid_token",
            200,
            {"message": "Feedback submitted successfully"}
        ),
        # Missing required fields
        (
            {"user_id": "user1", "message_id": 1},
            "valid_token",
            400,
            ErrorResponse(detail="Missing required parameters").model_dump()
        ),
        # Invalid token
        (
            FeedbackRequest(
                user_id="user1",
                message_id=1,
                feedback_text="Great response!",
                is_positive=True
            ),
            "invalid_token",
            403,
            ErrorResponse(detail="Invalid token").model_dump()
        ),
        # Database error
        (
            FeedbackRequest(
                user_id="error_user",
                message_id=1,
                feedback_text="Great response!",
                is_positive=True
            ),
            "valid_token",
            500,
            ErrorResponse(detail="Failed to submit feedback").model_dump()
        ),
    ]
)
def test_feedback_endpoint(payload, token, expected_status, expected_response):
    with \
        patch('main.validate_bearer_token') as mock_validate_bearer_token, \
        patch('main.add_feedback') as mock_add_feedback:

        mock_validate_bearer_token.return_value = token == "valid_token"
        
        # Fix: Use proper attribute access for Pydantic models
        if isinstance(payload, FeedbackRequest):
            mock_add_feedback.return_value = payload.user_id != "error_user"
        else:
            mock_add_feedback.return_value = payload.get("user_id") != "error_user"

        # Convert payload to dict if it's a Pydantic model
        request_payload = payload.model_dump() if isinstance(payload, BaseModel) else payload

        response = client.post(
            "/feedback",
            json=request_payload,
            headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == expected_status
        assert response.json() == expected_response

def test_timeout_handling():
    """Test that timeouts are handled gracefully"""
    with \
        patch('main.generate_looker_query', side_effect=TimeoutError), \
        patch('main.validate_bearer_token', return_value=True):
        
        response = client.post(
            "/",
            json={"contents": "test"},
            headers={"Authorization": "Bearer valid_token"}
        )
        
        # Check that we get a 504 status code and appropriate error message
        assert response.status_code == 504
        assert response.json() == {
            "detail": "Request timed out"
        }

@pytest.mark.parametrize(
    "payload, token, expected_status, expected_response",
    [
        # Valid request with results
        (
            {
                "user_id": "user1",
                "search_query": "sales",
                "limit": 10,
                "offset": 0
            },
            "valid_token",
            200,
            {
                "message": "Search completed successfully",
                "data": {
                    "total": 1,
                    "matches": [
                        {
                            "chat_id": 123,
                            "explore_key": "orders.explore",
                            "created_at": "2024-01-20T14:30:00",
                            "messages": [
                                {
                                    "message_id": 1,
                                    "content": "Show me sales data",
                                    "timestamp": "2024-01-20T14:30:00",
                                    "is_user": True,
                                    "matches_search": True
                                },
                                {
                                    "message_id": 2,
                                    "content": "Here's your sales data...",
                                    "timestamp": "2024-01-20T14:31:00",
                                    "is_user": False,
                                    "matches_search": True
                                }
                            ]
                        }
                    ]
                }
            }
        ),
        # No results found
        (
            {
                "user_id": "user1",
                "search_query": "nonexistent",
                "limit": 10,
                "offset": 0
            },
            "valid_token",
            200,
            {
                "message": "No results found",
                "data": {
                    "total": 0,
                    "matches": []
                }
            }
        ),
        # Missing required parameters
        (
            {
                "user_id": "user1"
            },
            "valid_token",
            400,
            {
                "detail": "Missing required parameters"
            }
        ),
        # Invalid token
        (
            {
                "user_id": "user1",
                "search_query": "sales",
                "limit": 10,
                "offset": 0
            },
            "invalid_token",
            403,
            {
                "detail": "Invalid token"
            }
        )
    ]
)
def test_search_chats(payload, token, expected_status, expected_response):
    """Test the chat search endpoint"""
    with \
        patch('main.validate_bearer_token') as mock_validate_bearer_token, \
        patch('main.search_chat_history') as mock_search:

        mock_validate_bearer_token.return_value = token == "valid_token"
        
        # Mock search results based on the payload
        if token == "valid_token" and "search_query" in payload:
            if payload["search_query"] == "sales":
                mock_search.return_value = {
                    "total": 1,
                    "matches": [
                        {
                            "chat_id": 123,
                            "explore_key": "orders.explore",
                            "created_at": "2024-01-20T14:30:00",
                            "messages": [
                                {
                                    "message_id": 1,
                                    "content": "Show me sales data",
                                    "timestamp": "2024-01-20T14:30:00",
                                    "is_user": True,
                                    "matches_search": True
                                },
                                {
                                    "message_id": 2,
                                    "content": "Here's your sales data...",
                                    "timestamp": "2024-01-20T14:31:00",
                                    "is_user": False,
                                    "matches_search": True
                                }
                            ]
                        }
                    ]
                }
            else:
                mock_search.return_value = {
                    "total": 0,
                    "matches": []
                }

        # Build query parameters
        query_params = "&".join([f"{k}={v}" for k, v in payload.items()])
        
        response = client.get(
            f"/chat/search?{query_params}",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == expected_status
        assert response.json() == expected_response