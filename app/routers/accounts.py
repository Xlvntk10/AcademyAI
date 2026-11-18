import re
import secrets
from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field
from app.accounts import COOKIE, SESSION_SECONDS, PKCE_COOKIE, PKCE_SECONDS

router = APIRouter(prefix="/api/auth", tags=["accounts"])


class CodeRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254, pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
    create_account: bool = Field(default=False, alias="register")


class VerifyRequest(CodeRequest):
    code: str = Field(pattern=r"^\d{6,10}$")


class LinkExchange(BaseModel):
    code: str = Field(min_length=1, max_length=2048, pattern=r"^[A-Za-z0-9_-]+$")


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
    return finish_login(manager, request, response, cookie, user)


def finish_login(manager, request, response, cookie, user):
    # Replacing the browser session also revokes the previous local handle.
    manager.logout(request.cookies.get(COOKIE))
    response.set_cookie(COOKIE, cookie, httponly=True, secure=manager.config.secure,
                        samesite="strict", max_age=SESSION_SECONDS, path="/")
    response.delete_cookie(PKCE_COOKIE, path="/api/auth", secure=manager.config.secure,
                           httponly=True, samesite="strict")
    return {"mode": "supabase", "user": user}


@router.post("/link")
def link(payload: CodeRequest, request: Request, response: Response):
    manager = accounts(request)
    email = payload.email.strip().lower()
    manager.rate_limit("code", request.client.host if request.client else "unknown", email)
    verifier = secrets.token_urlsafe(32)
    manager.provider.send_link(email, payload.create_account, verifier)
    response.set_cookie(PKCE_COOKIE, verifier, httponly=True, secure=manager.config.secure,
                        samesite="strict", max_age=PKCE_SECONDS, path="/api/auth")
    return {"message": "Если адрес доступен для этого действия, придёт письмо со ссылкой. Открой последнее письмо в этом же браузере в течение 10 минут."}


@router.post("/exchange")
def exchange(payload: LinkExchange, request: Request, response: Response):
    manager = accounts(request)
    verifier = request.cookies.get(PKCE_COOKIE, "")
    if not re.fullmatch(r"[A-Za-z0-9_-]{43}", verifier):
        raise HTTPException(401, "Запроси новую ссылку и открой её в том же браузере. Ожидание входа истекло или письмо открыто на другом устройстве.")
    manager.rate_limit("verify", request.client.host if request.client else "unknown", "link:" + manager.digest(verifier))
    tokens = manager.provider.exchange(payload.code, verifier)
    cookie, user = manager.session_from_tokens(tokens)
    return finish_login(manager, request, response, cookie, user)


@router.post("/logout")
def logout(request: Request, response: Response):
    manager = accounts(request)
    manager.logout(request.cookies.get(COOKIE), request.headers.get("x-academy-account", ""))
    response.delete_cookie(COOKIE, path="/", secure=manager.config.secure, httponly=True, samesite="strict")
    return {"signed_out": True}
