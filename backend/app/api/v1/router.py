from fastapi import APIRouter

from app.api.v1.endpoints import admin, auth, calc, health, live, maps, og, oauth, playlist, players, rankings, stars_bands, suggestions

api_router = APIRouter()
api_router.include_router(auth.router, tags=["auth"])
api_router.include_router(suggestions.router, tags=["suggestions"])
api_router.include_router(health.router, tags=["health"])
api_router.include_router(rankings.router, tags=["rankings"])
api_router.include_router(players.router, tags=["players"])
api_router.include_router(maps.router, tags=["maps"])
api_router.include_router(calc.router, tags=["calc"])
api_router.include_router(playlist.router, tags=["playlists"])
api_router.include_router(stars_bands.router, tags=["stars-bands"])
api_router.include_router(live.router, tags=["live"])
api_router.include_router(admin.router, tags=["admin"])
api_router.include_router(oauth.router, tags=["admin"])
api_router.include_router(og.router, tags=["opengraph"])
