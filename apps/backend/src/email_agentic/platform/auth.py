import asyncio
from dataclasses import dataclass

import jwt
from fastapi import HTTPException, Request


@dataclass(frozen=True)
class Actor:
    owner: str
    role: str = "user"


async def authenticate(request: Request):
    settings = request.app.state.container.settings
    if settings.environment == "local":
        if request.client and request.client.host not in set(settings.local_client_hosts.split(",")):
            raise HTTPException(403, "Local mode only accepts loopback requests")
        owner = settings.owner_email
    else:
        token = request.headers.get("cf-access-jwt-assertion", "")
        if not token:
            raise HTTPException(401, "Authentication required")
        try:
            key = await asyncio.to_thread(request.app.state.jwt_client.get_signing_key_from_jwt, token)
            claims = jwt.decode(
                token,
                key.key,
                algorithms=["RS256"],
                audience=settings.cf_audience,
                issuer=settings.cf_team_domain.rstrip("/"),
                options={"require": ["exp", "iat", "sub", "email", "aud", "iss"]},
            )
            owner = claims["email"]
        except (jwt.PyJWTError, ValueError, KeyError):
            raise HTTPException(401, "Invalid identity") from None
    if not owner or owner.casefold() != settings.owner_email.casefold():
        raise HTTPException(403, "Owner access required")
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        if request.headers.get("origin") != settings.app_origin:
            raise HTTPException(403, "Origin check failed")
    return Actor(owner.casefold())
