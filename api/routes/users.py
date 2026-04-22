from fastapi import APIRouter, HTTPException
from api.models import ProfileCreate
from api.database import (
    get_or_create_user, save_profile, get_active_profile,
    get_all_profiles, set_active_profile, delete_profile,
    get_search_history, save_comparison, get_saved_comparisons, delete_comparison,
    get_chat_sessions, get_chat_session,
)

router = APIRouter(prefix="/users", tags=["Users & Profiles"])


@router.post("/register")
def register_or_login(username: str):
    user_id = get_or_create_user(username)
    return {"user_id": user_id, "username": username}


@router.post("/profiles")
def create_profile(req: ProfileCreate):
    user_id = get_or_create_user(req.username)
    profile_id = save_profile(user_id, req.model_dump())
    return {"profile_id": profile_id, "user_id": user_id}


@router.get("/profiles/{user_id}")
def list_profiles(user_id: int):
    return get_all_profiles(user_id)


@router.get("/profiles/{user_id}/active")
def active_profile(user_id: int):
    p = get_active_profile(user_id)
    if not p:
        raise HTTPException(status_code=404, detail="No active profile")
    return p


@router.put("/profiles/{user_id}/activate/{profile_id}")
def activate_profile(user_id: int, profile_id: int):
    set_active_profile(user_id, profile_id)
    return {"status": "ok"}


@router.delete("/profiles/{user_id}/{profile_id}")
def remove_profile(user_id: int, profile_id: int):
    delete_profile(user_id, profile_id)
    return {"status": "deleted"}


@router.get("/history/{user_id}")
def search_history(user_id: int, limit: int = 20):
    return get_search_history(user_id, limit)


@router.get("/comparisons/{user_id}")
def list_comparisons(user_id: int):
    return get_saved_comparisons(user_id)


@router.delete("/comparisons/{user_id}/{comparison_id}")
def remove_comparison(user_id: int, comparison_id: int):
    delete_comparison(user_id, comparison_id)
    return {"status": "deleted"}


@router.get("/chats/{user_id}")
def list_chats(user_id: int):
    return get_chat_sessions(user_id)


@router.get("/chats/session/{session_id}")
def get_chat(session_id: int):
    s = get_chat_session(session_id)
    if not s:
        raise HTTPException(status_code=404, detail="Session not found")
    return s
