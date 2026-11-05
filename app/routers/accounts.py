from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field
from app.accounts import COOKIE, SESSION_SECONDS

router = APIRouter(prefix="/api/auth", tags=["accounts"])


class CodeRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254, pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
    create_account: bool = Field(default=False, alias="register")


class VerifyRequest(CodeRequest):
    code: str = Field(pattern=r"^\d{6,10}$")


def accounts(request):
    result = request.app.state.accounts
    if result is None:
        raise HTTPException(409, "Supabase Auth ещё не настроен на сервере")
    return result


@router.get("/session")
def session(request: Request):
    manager = request.app.state.accounts
    if manager is None:
        return {"mode": "local", "user": None}
    cookie = request.cookies.get(COOKIE)
    if not cookie:
        return {"mode": "supabase", "user": None}
    return {"mode": "supabase", "user": manager.resolve(cookie)}


@router.post("/code")
def code(payload: CodeRequest, request: Request):
    manager = accounts(request)
    email = payload.email.strip().lower()
    manager.rate_limit("code", request.client.host if request.client else "unknown", email)
    manager.provider.send_code(email, payload.create_account)
    return {"message": "Если адрес доступен для этого действия, на него придёт код. Проверь почту."}


@router.post("/verify")
def verify(payload: VerifyRequest, request: Request, response: Response):
    manager = accounts(request)
    manager.rate_limit("verify", request.client.host if request.client else "unknown", payload.email.strip().lower())
    cookie, user = manager.create_session(payload.email.strip().lower(), payload.code)
    # Replacing the browser session also revokes the previous local handle.
    manager.logout(request.cookies.get(COOKIE))
    response.set_cookie(COOKIE, cookie, httponly=True, secure=manager.config.secure,
                        samesite="strict", max_age=SESSION_SECONDS, path="/")
    return {"mode": "supabase", "user": user}


@router.post("/logout")
def logout(request: Request, response: Response):
    manager = accounts(request)
    manager.logout(request.cookies.get(COOKIE), request.headers.get("x-academy-account", ""))
    response.delete_cookie(COOKIE, path="/", secure=manager.config.secure, httponly=True, samesite="strict")
    return {"signed_out": True}
