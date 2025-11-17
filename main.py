import os
from datetime import datetime, timedelta, timezone
import secrets
from typing import List, Optional

from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from bson import ObjectId

from database import db, create_document, get_documents

app = FastAPI(title="Astrology App API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# -------------------------------
# Utility helpers
# -------------------------------

def oid(id_str: str) -> ObjectId:
    try:
        return ObjectId(id_str)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid id format")


def now_utc():
    return datetime.now(timezone.utc)


# -------------------------------
# Request/Response models
# -------------------------------

class RegisterRequest(BaseModel):
    name: str
    email: str
    password: str
    role: str = Field("user", pattern="^(user|astrologer)$")
    rate_per_min: Optional[float] = Field(None, ge=0)
    bio: Optional[str] = None


class LoginRequest(BaseModel):
    email: str
    password: str


class SessionResponse(BaseModel):
    token: str
    user_id: str
    name: str
    role: str


class AstrologerPublic(BaseModel):
    id: str
    name: str
    bio: Optional[str] = None
    rate_per_min: Optional[float] = None
    rating: Optional[float] = None
    avatar_url: Optional[str] = None


class CreateChatRequest(BaseModel):
    astrologer_id: str
    min_fee: float = Field(0, ge=0)


class SendMessageRequest(BaseModel):
    chat_id: str
    sender_id: str
    content: str


# -------------------------------
# Auth helpers (very basic token store in DB session collection)
# -------------------------------

from hashlib import sha256


def hash_password(p: str) -> str:
    return sha256(p.encode()).hexdigest()


def create_session(user_id: str) -> str:
    token = secrets.token_urlsafe(32)
    session_doc = {
        "user_id": user_id,
        "token": token,
        "created_at": now_utc(),
        "expires_at": now_utc() + timedelta(days=7),
    }
    db["session"].insert_one(session_doc)
    return token


def get_user_by_token(token: str):
    sess = db["session"].find_one({"token": token})
    if not sess:
        return None
    return db["user"].find_one({"_id": sess["user_id"] if isinstance(sess["user_id"], ObjectId) else oid(sess["user_id"])})


# -------------------------------
# Basic routes
# -------------------------------

@app.get("/")
def root():
    return {"status": "ok", "service": "Astrology API"}


@app.get("/test")
def test_database():
    try:
        collections = db.list_collection_names()
        return {"backend": "running", "database": "connected", "collections": collections}
    except Exception as e:
        return {"backend": "running", "database": f"error: {str(e)[:80]}"}


# -------------------------------
# Auth endpoints
# -------------------------------

@app.post("/auth/register", response_model=SessionResponse)
def register(payload: RegisterRequest):
    if db["user"].find_one({"email": payload.email}):
        raise HTTPException(status_code=400, detail="Email already registered")
    user_doc = {
        "name": payload.name,
        "email": payload.email,
        "password_hash": hash_password(payload.password),
        "role": payload.role,
        "rate_per_min": payload.rate_per_min,
        "bio": payload.bio,
        "created_at": now_utc(),
        "updated_at": now_utc(),
    }
    res = db["user"].insert_one(user_doc)
    token = create_session(str(res.inserted_id))
    return SessionResponse(token=token, user_id=str(res.inserted_id), name=payload.name, role=payload.role)


@app.post("/auth/login", response_model=SessionResponse)
def login(payload: LoginRequest):
    user = db["user"].find_one({"email": payload.email})
    if not user or user.get("password_hash") != hash_password(payload.password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = create_session(str(user["_id"]))
    return SessionResponse(token=token, user_id=str(user["_id"]), name=user["name"], role=user["role"])


# -------------------------------
# Astrologers listing
# -------------------------------

@app.get("/astrologers", response_model=List[AstrologerPublic])
def list_astrologers():
    rows = db["user"].find({"role": "astrologer"}).limit(50)
    out: List[AstrologerPublic] = []
    for r in rows:
        out.append(
            AstrologerPublic(
                id=str(r["_id"]),
                name=r.get("name"),
                bio=r.get("bio"),
                rate_per_min=r.get("rate_per_min"),
                rating=r.get("rating"),
                avatar_url=r.get("avatar_url"),
            )
        )
    return out


# -------------------------------
# Chat & messages
# -------------------------------

@app.post("/chat/create")
def create_chat(payload: CreateChatRequest):
    # Ensure astrologer exists and is astrologer
    astro = db["user"].find_one({"_id": oid(payload.astrologer_id), "role": "astrologer"})
    if not astro:
        raise HTTPException(status_code=404, detail="Astrologer not found")

    chat_doc = {
        "user_id": None,  # set on first message via sender_id; can also be passed explicitly
        "astrologer_id": oid(payload.astrologer_id),
        "status": "active",
        "min_fee": float(payload.min_fee),
        "created_at": now_utc(),
        "updated_at": now_utc(),
    }
    res = db["chat"].insert_one(chat_doc)
    return {"chat_id": str(res.inserted_id)}


@app.post("/chat/send")
def send_message(payload: SendMessageRequest):
    chat = db["chat"].find_one({"_id": oid(payload.chat_id)})
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")

    # Set user_id if missing
    if chat.get("user_id") is None:
        db["chat"].update_one({"_id": chat["_id"]}, {"$set": {"user_id": oid(payload.sender_id), "updated_at": now_utc()}})

    msg_doc = {
        "chat_id": chat["_id"],
        "sender_id": oid(payload.sender_id),
        "content": payload.content,
        "msg_type": "text",
        "created_at": now_utc(),
    }
    db["message"].insert_one(msg_doc)
    return {"status": "sent"}


@app.get("/chat/{chat_id}/messages")
def get_messages(chat_id: str):
    rows = db["message"].find({"chat_id": oid(chat_id)}).sort("created_at", 1)
    out = []
    for r in rows:
        out.append(
            {
                "id": str(r["_id"]),
                "sender_id": str(r["sender_id"]),
                "content": r.get("content"),
                "created_at": r.get("created_at").isoformat() if r.get("created_at") else None,
            }
        )
    return out


# -------------------------------
# Simple signaling storage for calls (WebRTC out of scope here, we provide stub endpoints)
# -------------------------------

class CallInitRequest(BaseModel):
    callee_id: str
    call_type: str = Field("audio", pattern="^(audio|video)$")
    chat_id: Optional[str] = None


@app.post("/call/init")
def init_call(payload: CallInitRequest):
    doc = {
        "caller_id": None,  # set on first client use if needed
        "callee_id": oid(payload.callee_id),
        "call_type": payload.call_type,
        "status": "initiated",
        "chat_id": oid(payload.chat_id) if payload.chat_id else None,
        "created_at": now_utc(),
    }
    res = db["call"].insert_one(doc)
    return {"call_id": str(res.inserted_id)}


@app.post("/call/{call_id}/status")
def update_call_status(call_id: str, status: str):
    db["call"].update_one({"_id": oid(call_id)}, {"$set": {"status": status, "updated_at": now_utc()}})
    return {"status": status}


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
