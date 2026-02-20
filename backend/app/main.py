import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select

from .auth import hash_password, verify_password
from .config import get_settings
from .database import async_session, init_db
from .models import Case, CaseProcessScore, User
from .routers import admin, auth, cases, chat, documents, statistics
from .routers import nn as nn_router_mod
from .routers.statistics import _build_historical_events, _build_seed_cases

settings = get_settings()
logger = logging.getLogger(__name__)

# Default admin credentials created on first startup when no admin exists
DEFAULT_ADMIN_EMAIL = "admin@portal.eu"
DEFAULT_ADMIN_PASSWORD = "admin1234"


async def _auto_seed() -> None:
    """Ensure a default admin user and demo seed data exist.

    Runs on every startup but is fully idempotent:
    - Always guarantees admin@portal.eu / admin1234 is a valid admin login.
    - Skips seeding if [HIST] cases are already present.
    """
    async with async_session() as db:
        try:
            # ── 1. Guarantee admin@portal.eu exists and is an admin ──
            # Look up by email so we never hit a unique-constraint collision.
            result = await db.execute(
                select(User).where(User.email == DEFAULT_ADMIN_EMAIL)
            )
            admin_user = result.scalar_one_or_none()

            if admin_user:
                # Row exists — make sure it has admin rights and the right password.
                if not admin_user.is_admin or not verify_password(
                    DEFAULT_ADMIN_PASSWORD, admin_user.hashed_password
                ):
                    admin_user.is_admin = True
                    admin_user.hashed_password = hash_password(DEFAULT_ADMIN_PASSWORD)
                    logger.info("Auto-seed: updated admin@portal.eu to admin + reset password.")
            else:
                # No such user yet — create from scratch.
                admin_user = User(
                    email=DEFAULT_ADMIN_EMAIL,
                    hashed_password=hash_password(DEFAULT_ADMIN_PASSWORD),
                    full_name="System Admin",
                    language="de",
                    is_admin=True,
                )
                db.add(admin_user)
                await db.flush()  # materialise UUID before FK inserts below
                logger.info(
                    "Auto-seed: created admin user  →  %s / %s",
                    DEFAULT_ADMIN_EMAIL,
                    DEFAULT_ADMIN_PASSWORD,
                )

            admin_id = admin_user.id
            logger.info("Auto-seed: admin login  →  %s / %s", DEFAULT_ADMIN_EMAIL, DEFAULT_ADMIN_PASSWORD)

            # ── 2. Check whether historical data is already present ──
            hist_count = await db.execute(
                select(func.count(Case.id)).where(Case.title.like("[HIST]%"))
            )
            if (hist_count.scalar() or 0) > 0:
                await db.commit()
                logger.info("Auto-seed: data already present, skipping.")
                return

            # ── 3. Insert 5 fictional completed cases ──
            seed_data = _build_seed_cases(admin_id)
            for item in seed_data:
                existing = await db.execute(
                    select(func.count(Case.id)).where(
                        Case.title == item["case"].title
                    )
                )
                if (existing.scalar() or 0) > 0:
                    continue

                db.add(item["case"])
                for event in item["events"]:
                    db.add(event)

                overrides = item["score_overrides"]
                score = CaseProcessScore(
                    case_id=item["case"].id,
                    evidence_score=overrides.get("evidence_score", 50.0),
                    evidence_breakdown={"source": "seed_data"},
                    ability_score=75.0,
                    ability_components={"source": "seed_data"},
                    willingness_score=50.0,
                    willingness_components={"source": "seed_data"},
                    p_served=overrides.get("p_served", 0.70),
                    p_default=overrides.get("p_default", 0.50),
                    p_win_contested=overrides.get("p_win_contested", 0.50),
                    p_settle=overrides.get("p_settle", 0.30),
                    p_collect=overrides.get("p_collect", 0.60),
                    p_cash_success=overrides.get("p_cash_success", 0.25),
                    priors_json={"source": "seed_data"},
                    posteriors_json={"source": "seed_data"},
                    observations_json={"source": "seed_data"},
                    drivers_json=[],
                    model_version="v2-seed",
                )
                db.add(score)

            # ── 4. Insert 100 historical observation cases ──
            hist_cases, hist_events = _build_historical_events(admin_id)
            for c in hist_cases:
                db.add(c)
            for e in hist_events:
                db.add(e)

            await db.commit()
            logger.info(
                "Auto-seed: inserted 5 fictional + 100 historical cases under admin %s.",
                DEFAULT_ADMIN_EMAIL,
            )

        except Exception:
            await db.rollback()
            logger.exception("Auto-seed failed — app continues without seed data.")


@asynccontextmanager
async def lifespan(app: FastAPI):
    os.makedirs(settings.generated_forms_dir, exist_ok=True)
    await init_db()
    await _auto_seed()
    yield


app = FastAPI(
    title="EU-Bagatellverfahren Portal",
    description="Portal für geringfügige Forderungen innerhalb der EU (VO 861/2007)",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(cases.router)
app.include_router(chat.router)
app.include_router(documents.router)
app.include_router(admin.router)
app.include_router(statistics.router)
app.include_router(statistics.ev_router)
app.include_router(nn_router_mod.router)


@app.get("/api/health")
async def health():
    return {"status": "ok"}


# ── Flutter Web PWA (served at /) ─────────────────────────────────────────────
# The Flutter web build is placed in  mobile_dist/  (produced by GitHub Actions
# or by running: cd mobile && flutter build web --release --base-href /
# then: cp -r build/web ../mobile_dist)
#
# All /api/* routes are already registered above, so they take priority.
# Everything else falls through to the Flutter SPA (index.html for deep links).

_WEB_DIST = Path(__file__).parent.parent.parent / "mobile_dist"

if _WEB_DIST.exists():
    # Serve Flutter static assets (JS, canvaskit, icons, fonts…)
    app.mount("/flutter_assets", StaticFiles(directory=str(_WEB_DIST / "flutter_assets")), name="flutter_assets")
    app.mount("/icons", StaticFiles(directory=str(_WEB_DIST / "icons")), name="icons")
    app.mount("/canvaskit", StaticFiles(directory=str(_WEB_DIST / "canvaskit")), name="canvaskit")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_flutter(full_path: str):
        """Serve the Flutter Web SPA — all non-API paths return index.html."""
        # Try exact file first (JS, CSS, assets…)
        candidate = _WEB_DIST / full_path
        if candidate.exists() and candidate.is_file():
            return FileResponse(str(candidate))
        # Fallback: return index.html for SPA routing (deep links work on iPhone)
        return FileResponse(str(_WEB_DIST / "index.html"))
