"""
Database Schemas for Astrology App

Each Pydantic model represents a collection in MongoDB. The collection name
is the lowercase of the class name.
"""

from pydantic import BaseModel, Field
from typing import Optional, List, Literal


class User(BaseModel):
    """
    Users of the platform. Role can be "user" or "astrologer".
    Collection: user
    """
    name: str = Field(..., description="Full name")
    email: str = Field(..., description="Email address")
    password_hash: str = Field(..., description="Hashed password")
    role: Literal["user", "astrologer"] = Field("user", description="User role")

    # Astrologer specific fields (optional for regular users)
    rate_per_min: Optional[float] = Field(None, ge=0, description="Rate per minute in your currency")
    bio: Optional[str] = Field(None, description="Short bio")
    skills: Optional[List[str]] = Field(default=None, description="List of skills or specialties")
    rating: Optional[float] = Field(default=None, ge=0, le=5, description="Average rating")
    avatar_url: Optional[str] = Field(default=None, description="Profile image URL")


class Chat(BaseModel):
    """
    A chat session between a user and an astrologer.
    Collection: chat
    """
    user_id: str = Field(..., description="User ID")
    astrologer_id: str = Field(..., description="Astrologer ID")
    status: Literal["active", "closed"] = Field("active", description="Chat status")
    min_fee: float = Field(0, ge=0, description="Minimum fee for the session")


class Message(BaseModel):
    """
    Messages inside a chat.
    Collection: message
    """
    chat_id: str = Field(..., description="Chat ID")
    sender_id: str = Field(..., description="Sender user ID")
    content: str = Field(..., description="Message text content")
    msg_type: Literal["text", "system"] = Field("text", description="Message type")


class Session(BaseModel):
    """
    Authentication session token for a user.
    Collection: session
    """
    user_id: str = Field(...)
    token: str = Field(...)
    expires_at: Optional[str] = Field(None, description="ISO datetime string for expiry")


class Call(BaseModel):
    """
    Audio/Video call session used for WebRTC signaling.
    Collection: call
    """
    chat_id: Optional[str] = Field(None, description="Related chat id if any")
    caller_id: str = Field(...)
    callee_id: str = Field(...)
    call_type: Literal["audio", "video"] = Field("audio")
    status: Literal["initiated", "connected", "ended"] = Field("initiated")
