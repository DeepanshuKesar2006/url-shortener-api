from datetime import datetime, timedelta, timezone
from fastapi import FastAPI, Depends, HTTPException, status, Request
from fastapi.responses import RedirectResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from app.database import engine, get_db, Base
from app import models, schemas, auth, utils

# Create all tables on startup
Base.metadata.create_all(bind=engine)

# Rate limiter: keyed by client IP
limiter = Limiter(key_func=get_remote_address)

app = FastAPI(
    title="URL Shortener API",
    description="An advanced URL shortener with auth, analytics, QR codes, and rate limiting.",
    version="1.0.0",
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.mount("/static", StaticFiles(directory="app/static"), name="static")


@app.get("/", include_in_schema=False)
def serve_frontend():
    """Serves the demo frontend. Must be registered before the /{short_code} catch-all."""
    return FileResponse("app/static/index.html")


@app.get("/health", tags=["Health"])
def health():
    return {"status": "ok"}


# ======================= AUTH =======================

@app.post("/auth/register", response_model=schemas.UserOut, tags=["Auth"])
def register(user: schemas.UserCreate, db: Session = Depends(get_db)):
    existing = db.query(models.User).filter(models.User.username == user.username).first()
    if existing:
        raise HTTPException(status_code=400, detail="Username already taken")
    new_user = models.User(
        username=user.username,
        hashed_password=auth.hash_password(user.password),
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user


@app.post("/auth/login", response_model=schemas.Token, tags=["Auth"])
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.username == form_data.username).first()
    if not user or not auth.verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Incorrect username or password")
    token = auth.create_access_token({"sub": user.username})
    return {"access_token": token, "token_type": "bearer"}


# ======================= LINKS =======================

@app.post("/links", response_model=schemas.LinkOut, tags=["Links"])
@limiter.limit("10/minute")
def create_link(
    request: Request,
    link_in: schemas.LinkCreate,
    db: Session = Depends(get_db),
    current_user=Depends(auth.get_current_user_optional),
):
    # Determine the short code: custom alias or randomly generated
    if link_in.custom_alias:
        code = link_in.custom_alias
        if db.query(models.ShortLink).filter(models.ShortLink.short_code == code).first():
            raise HTTPException(status_code=400, detail="Alias already in use")
    else:
        code = utils.generate_short_code()
        # Guard against the rare random collision
        while db.query(models.ShortLink).filter(models.ShortLink.short_code == code).first():
            code = utils.generate_short_code()

    expires_at = None
    if link_in.expires_in_days:
        expires_at = datetime.now(timezone.utc) + timedelta(days=link_in.expires_in_days)

    new_link = models.ShortLink(
        short_code=code,
        original_url=str(link_in.original_url),
        owner_id=current_user.id if current_user else None,
        expires_at=expires_at,
    )
    db.add(new_link)
    db.commit()
    db.refresh(new_link)
    return new_link


@app.get("/links/mine", response_model=list[schemas.LinkOut], tags=["Links"])
def my_links(db: Session = Depends(get_db), current_user=Depends(auth.get_current_user_required)):
    return db.query(models.ShortLink).filter(models.ShortLink.owner_id == current_user.id).all()


@app.get("/links/{short_code}/stats", response_model=schemas.LinkStats, tags=["Links"])
def link_stats(short_code: str, db: Session = Depends(get_db)):
    link = db.query(models.ShortLink).filter(models.ShortLink.short_code == short_code).first()
    if not link:
        raise HTTPException(status_code=404, detail="Short link not found")
    recent = (
        db.query(models.ClickEvent)
        .filter(models.ClickEvent.link_id == link.id)
        .order_by(models.ClickEvent.clicked_at.desc())
        .limit(10)
        .all()
    )
    result = schemas.LinkStats.model_validate(link)
    result.recent_clicks = [
        {"clicked_at": c.clicked_at, "ip_address": c.ip_address, "referrer": c.referrer}
        for c in recent
    ]
    return result


@app.get("/links/{short_code}/qrcode", tags=["Links"])
def get_qr_code(short_code: str, request: Request, db: Session = Depends(get_db)):
    link = db.query(models.ShortLink).filter(models.ShortLink.short_code == short_code).first()
    if not link:
        raise HTTPException(status_code=404, detail="Short link not found")
    full_short_url = str(request.base_url) + short_code
    data_uri = utils.generate_qr_code_base64(full_short_url)
    return JSONResponse({"short_url": full_short_url, "qr_code_base64": data_uri})


@app.delete("/links/{short_code}", status_code=204, tags=["Links"])
def delete_link(
    short_code: str,
    db: Session = Depends(get_db),
    current_user=Depends(auth.get_current_user_required),
):
    link = db.query(models.ShortLink).filter(models.ShortLink.short_code == short_code).first()
    if not link:
        raise HTTPException(status_code=404, detail="Short link not found")
    if link.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not your link")
    db.delete(link)
    db.commit()
    utils.redirect_cache.pop(short_code, None)
    return None


# ======================= REDIRECT (the core feature) =======================

@app.get("/{short_code}", tags=["Redirect"])
def redirect_to_original(short_code: str, request: Request, db: Session = Depends(get_db)):
    # 1. Check cache first (fast path, avoids DB hit)
    cached_url = utils.redirect_cache.get(short_code)

    link = db.query(models.ShortLink).filter(models.ShortLink.short_code == short_code).first()
    if not link or not link.is_active:
        raise HTTPException(status_code=404, detail="Short link not found")

    if link.expires_at and link.expires_at < datetime.now(timezone.utc).replace(tzinfo=link.expires_at.tzinfo):
        raise HTTPException(status_code=410, detail="This link has expired")

    # 2. Log the click (analytics)
    click = models.ClickEvent(
        link_id=link.id,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        referrer=request.headers.get("referer"),
    )
    db.add(click)
    link.click_count += 1
    db.commit()

    # 3. Warm the cache for next time
    if not cached_url:
        utils.redirect_cache[short_code] = link.original_url

    return RedirectResponse(url=link.original_url, status_code=status.HTTP_302_FOUND)
