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
import re


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

    @app.get('/api/settings')
    async def get_settings_api(request: Request) -> JSONResponse:
        settings = request.app.state.settings
        return JSONResponse({
            'ai_provider': settings.ai_provider,
            'gemini_planner_model': settings.gemini_planner_model,
            'gemini_browser_model': settings.gemini_browser_model,
            'gemini_classifier_model': settings.gemini_classifier_model,
        })

    @app.post('/api/settings')
    async def set_settings_api(request: Request) -> JSONResponse:
        body = await request.json()
        settings = request.app.state.settings
        
        updates = {}
        if 'ai_provider' in body:
            settings.ai_provider = body['ai_provider']
            updates['AI_PROVIDER'] = settings.ai_provider
        if 'gemini_planner_model' in body:
            settings.gemini_planner_model = body['gemini_planner_model']
            updates['GEMINI_PLANNER_MODEL'] = settings.gemini_planner_model
        if 'gemini_browser_model' in body:
            settings.gemini_browser_model = body['gemini_browser_model']
            updates['GEMINI_BROWSER_MODEL'] = settings.gemini_browser_model
        if 'gemini_classifier_model' in body:
            settings.gemini_classifier_model = body['gemini_classifier_model']
            updates['GEMINI_CLASSIFIER_MODEL'] = settings.gemini_classifier_model

        env_file = Path('.env.local')
        if env_file.exists():
            content = env_file.read_text('utf-8')
            for k, v in updates.items():
                pattern = re.compile(rf'^{k}=.*$', re.MULTILINE)
                if pattern.search(content):
                    content = pattern.sub(f'{k}={v}', content)
                else:
                    content += f'\n{k}={v}'
            env_file.write_text(content, 'utf-8')
            
        return JSONResponse({'ok': True})

    return app
