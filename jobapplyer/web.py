from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from jobapplyer.config import get_settings
from jobapplyer.db import Database
from jobapplyer.services.orchestrator import JobApplyerOrchestrator


def create_app() -> FastAPI:
    settings = get_settings()
    templates = Jinja2Templates(directory=str(Path(__file__).parent / 'templates'))

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        db = Database(settings.database_path)
        orchestrator = JobApplyerOrchestrator(settings, db)
        app.state.settings = settings
        app.state.db = db
        app.state.orchestrator = orchestrator
        if settings.auto_start_agent:
            await orchestrator.start()
        try:
            yield
        finally:
            await orchestrator.shutdown()
            db.close()

    app = FastAPI(title=settings.app_name, lifespan=lifespan)
    app.mount('/static', StaticFiles(directory=str(Path(__file__).parent / 'static')), name='static')

    @app.get('/', response_class=HTMLResponse)
    async def index(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(request=request, name='index.html', context={'request': request})

    @app.get('/api/summary')
    async def summary(request: Request) -> JSONResponse:
        return JSONResponse(request.app.state.db.summary())

    @app.get('/api/jobs')
    async def jobs(request: Request) -> JSONResponse:
        return JSONResponse({'items': request.app.state.db.list_jobs(limit=25)})

    @app.get('/api/applications')
    async def applications(request: Request) -> JSONResponse:
        return JSONResponse({'items': request.app.state.db.list_applications(limit=40)})

    @app.get('/api/events')
    async def events(request: Request) -> JSONResponse:
        return JSONResponse({'items': request.app.state.db.recent_events(limit=40)})

    @app.get('/api/agent')
    async def agent(request: Request) -> JSONResponse:
        return JSONResponse(request.app.state.orchestrator.snapshot())

    @app.post('/api/agent/start')
    async def agent_start(request: Request) -> JSONResponse:
        await request.app.state.orchestrator.start()
        return JSONResponse({'ok': True})

    @app.post('/api/agent/stop')
    async def agent_stop(request: Request) -> JSONResponse:
        await request.app.state.orchestrator.stop()
        return JSONResponse({'ok': True})

    @app.post('/api/agent/run-once')
    async def agent_run_once(request: Request) -> JSONResponse:
        result = await request.app.state.orchestrator.run_once()
        return JSONResponse({'ok': True, 'result': result})

    @app.get('/api/agent/thoughts')
    async def agent_thoughts(request: Request) -> JSONResponse:
        thoughts = request.app.state.orchestrator.get_agent_thoughts(limit=30)
        return JSONResponse({'items': thoughts})

    @app.get('/api/agent/prompt')
    async def agent_prompt_get(request: Request) -> JSONResponse:
        prompt = request.app.state.orchestrator.get_user_prompt()
        return JSONResponse({'prompt': prompt})

    @app.post('/api/agent/prompt')
    async def agent_prompt_set(request: Request) -> JSONResponse:
        body = await request.json()
        request.app.state.orchestrator.set_user_prompt(body.get('prompt', ''))
        return JSONResponse({'ok': True})

    return app
