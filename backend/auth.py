import httpx
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from clerk_backend_api import Clerk
from clerk_backend_api.security.types import AuthenticateRequestOptions

from config import settings
from database import get_db
from models import User


def _to_requestish(request: Request) -> httpx.Request:
    return httpx.Request(
        method=request.method,
        url=str(request.url),
        headers=dict(request.headers),
    )


def _get_clerk_client() -> Clerk:
    if not settings.clerk_secret_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="CLERK_SECRET_KEY is not configured on the backend.",
        )
    return Clerk(bearer_auth=settings.clerk_secret_key)


async def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    clerk = _get_clerk_client()
    auth_state = clerk.authenticate_request(
        _to_requestish(request),
        AuthenticateRequestOptions(
            authorized_parties=settings.clerk_authorized_parties or None,
        ),
    )

    if not auth_state.is_signed_in or not auth_state.payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
        )

    clerk_user_id = auth_state.payload.get("sub")
    if not clerk_user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Clerk session payload.",
        )

    user = db.scalar(select(User).where(User.clerk_user_id == clerk_user_id))
    if user is None:
        user = User(clerk_user_id=clerk_user_id)
        db.add(user)
        db.commit()
        db.refresh(user)

    return user
