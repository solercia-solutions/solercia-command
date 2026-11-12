"""Disabled-by-default authenticated, transient checklist preview.

One upload/job per interpreter, without a queue. This is not deployment-wide
admission or an OS/RSS/CPU sandbox. A thread blocked in OS process creation cannot
be forcibly stopped: retain its Future and quarantine admission on cleanup
exhaustion. Later requests reclaim only completed jobs; no detached retry loop.
An indefinitely blocked OS operation requires operator intervention. Never turn
this flag on as a substitute for deployment resource isolation.
"""
import asyncio
import base64
import binascii

from concurrent.futures import Future, ThreadPoolExecutor
from threading import BoundedSemaphore, Event, Lock
from time import monotonic

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import ValidationError
from starlette.requests import ClientDisconnect

from app.config import settings
from app.dependencies import get_current_membership, get_db
from app.shared.exceptions import AppException
from app.shared.no_store_route import NoStoreRoute as SharedNoStoreRoute

from .contracts import ParseLimits
from .preview_runner import PreviewRunner, PreviewRunnerError, RunnerLimits
from .review_plan import TrustedContext, build_review_plan
from .schemas import (MAX_DECISIONS, MAX_ENCODED_SOURCE, PROFILE_VERSION, PreviewResponse,
                      ReviewRequest, ReviewResponse, project_preview, project_review,
                      OptionsQuery, OptionsReader, OptionsResponse)


class NoStoreRoute(SharedNoStoreRoute):
    """Compatibility export retaining the task-import error message."""

    error_detail = 'No se pudo completar la vista previa.'


router = APIRouter(prefix='/task-import', tags=['task-import'], route_class=NoStoreRoute)

# Server-owned limits. No request field can configure these or parser limits.
_PARSE_LIMITS = ParseLimits()
_RUNNER_LIMITS = RunnerLimits()
MAX_INPUT_BYTES = _PARSE_LIMITS.max_input_bytes
UPLOAD_SECONDS = 15.0
FACTS_SECONDS = 5.0
# Per-row metadata budget includes JSON syntax and escaped bounded strings.
# Bounded independently of the 5 MiB decoded source; not an upload parser option.
MAX_REVIEW_BODY_BYTES = MAX_ENCODED_SOURCE + MAX_DECISIONS * 4096 + 4096
RUN_SECONDS = (_RUNNER_LIMITS.timeout_seconds + _RUNNER_LIMITS.terminate_grace_seconds
               + _RUNNER_LIMITS.kill_grace_seconds + 1.0)
CLEANUP_SECONDS = (_RUNNER_LIMITS.terminate_grace_seconds
                   + _RUNNER_LIMITS.kill_grace_seconds + .5)
_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix='task-preview')
_ADMISSION = BoundedSemaphore(1)
_QUARANTINE_LOCK = Lock()
_QUARANTINED_JOB: Future | None = None


def get_preview_runner() -> PreviewRunner:
    return PreviewRunner(limits=_RUNNER_LIMITS, parse_limits=_PARSE_LIMITS)


def _error(status: int, code: str) -> AppException:
    return AppException(
        'No se pudo completar la vista previa.', code, status,
        headers={'Cache-Control': 'no-store'},
    )


def _acquire() -> None:
    global _QUARANTINED_JOB
    with _QUARANTINE_LOCK:
        if _QUARANTINED_JOB is not None:
            if not _QUARANTINED_JOB.done():
                raise _error(503, 'cleanup_failed')
            # Consume any failure, without logging source data or exceptions.
            _QUARANTINED_JOB.exception()
            _QUARANTINED_JOB = None
            _ADMISSION.release()
        if not _ADMISSION.acquire(blocking=False):
            raise _error(503, 'busy')


def _release_or_quarantine(job: Future | None) -> None:
    global _QUARANTINED_JOB
    with _QUARANTINE_LOCK:
        if job is not None and not job.done():
            _QUARANTINED_JOB = job
        else:
            if job is not None:
                job.exception()
            _ADMISSION.release()


def _options(request: Request) -> tuple[str, str]:
    params = request.query_params
    if (set(params) != {'format', 'profile'}
            or len(params.getlist('format')) != 1 or len(params.getlist('profile')) != 1
            or params['format'] not in ('csv', 'xlsx') or params['profile'] != 'checklist'):
        raise _error(422, 'unsupported_options')
    media_type = request.headers.get('content-type', '').split(';', 1)[0].strip().lower()
    allowed_media = {'application/octet-stream',
                     'text/csv' if params['format'] == 'csv' else
                     'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'}
    if media_type not in allowed_media:
        raise _error(415, 'unsupported_media_type')
    return params['format'], params['profile']


async def _upload(request: Request, max_bytes: int | None = None) -> bytes:
    data = bytearray()
    limit = MAX_INPUT_BYTES if max_bytes is None else max_bytes
    deadline = monotonic() + UPLOAD_SECONDS
    try:
        async with asyncio.timeout(UPLOAD_SECONDS):
            async for chunk in request.stream():
                if monotonic() >= deadline:
                    raise _error(408, 'upload_timeout')
                # Test cumulative size BEFORE retaining this chunk. Content-Length
                # is intentionally not trusted; chunked requests get the same cap.
                if len(chunk) > limit - len(data):
                    raise _error(413, 'input_limit')
                data.extend(chunk)
                # Buffered chunks must not starve cancellation/timer delivery.
                await asyncio.sleep(0)
    except TimeoutError:
        raise _error(408, 'upload_timeout') from None
    except ClientDisconnect:
        raise _error(499, 'client_disconnected') from None
    return bytes(data)


async def _wait_result(request: Request, job, seconds: float | None = None):
    deadline = monotonic() + (RUN_SECONDS if seconds is None else seconds)
    while not job.done():
        remaining = deadline - monotonic()
        if remaining <= 0:
            raise _error(504, 'timeout')
        # Upload is exhausted. Receive now observes disconnect only; wait_for
        # owns/cancels its receive coroutine on timeout or request cancellation.
        try:
            message = await asyncio.wait_for(request.receive(), min(.05, remaining))
        except TimeoutError:
            continue
        if message['type'] == 'http.disconnect':
            raise _error(499, 'client_disconnected')
        await asyncio.sleep(0)
    return job.result()


async def _cleanup(job: Future, cancel: Event) -> bool:
    """Signal cancellation and wait locally; repeated cancellation cannot detach it."""
    cancel.set()
    deadline = monotonic() + CLEANUP_SECONDS
    interrupted = False
    while not job.done():
        remaining = deadline - monotonic()
        if remaining <= 0:
            break
        try:
            await asyncio.sleep(min(.01, remaining))
        except asyncio.CancelledError:
            # Delay, never discard, cancellation arriving during cleanup.
            interrupted = True
    if interrupted:
        raise asyncio.CancelledError
    return job.done()


def _runner_error(error: PreviewRunnerError) -> AppException:
    status, code = {
        'busy': (503, 'busy'), 'timeout': (504, 'timeout'),
        'cleanup_failed': (503, 'cleanup_failed'),
        'input_limit': (413, 'input_limit'), 'response_limit': (413, 'response_limit'),
        'cancelled': (499, 'cancelled'),
    }.get(error.code, (502, 'preview_failed'))
    return _error(status, code)


@router.post('/preview', response_model=PreviewResponse)
async def preview_tasks(
    request: Request,
    response: Response,
    membership=Depends(get_current_membership),
    runner: PreviewRunner = Depends(get_preview_runner),
) -> PreviewResponse:
    """Previsualiza bytes CSV/XLSX del checklist sin guardar tareas ni archivos.

    Requiere membresía vigente antes de leer el cuerpo, incluso deshabilitado.
    Envía bytes sin multipart, con format=csv|xlsx y profile=checklist explícitos.
    El contenido solo se devuelve al solicitante autorizado; no crea tareas.
    """
    if not settings.TASK_IMPORT_PREVIEW_ENABLED:
        raise _error(404, 'preview_disabled')
    format, profile = _options(request)
    _acquire()
    job = None
    cancel = Event()
    try:
        data = await _upload(request)
        job = _EXECUTOR.submit(runner.run, data, format=format, profile=profile, cancel=cancel)
        try:
            result = await _wait_result(request, job)
        except asyncio.CancelledError:
            await _cleanup(job, cancel)
            raise
        except BaseException:
            if not await _cleanup(job, cancel):
                raise _error(503, 'cleanup_failed') from None
            # A reaping failure takes precedence over the original HTTP timeout
            # or disconnect; it must never be described as successful cleanup.
            failure = job.exception()
            if isinstance(failure, PreviewRunnerError) and failure.code == 'cleanup_failed':
                raise _runner_error(failure) from None
            raise
        response.headers['Cache-Control'] = 'no-store'
        return project_preview(result)
    except PreviewRunnerError as error:
        raise _runner_error(error) from None
    except (AppException, HTTPException, asyncio.CancelledError):
        raise
    except Exception:
        raise _error(502, 'preview_failed') from None
    finally:
        _release_or_quarantine(job)


def get_options_repository(db=Depends(get_db)) -> OptionsReader:
    # Same cached request session as trusted membership, no independent session.
    from .options_repository import OptionsRepository
    return OptionsRepository(db)


async def _load_options(request: Request, repository: OptionsReader, tenant_id: str,
                        options: OptionsQuery):
    async def load():
        try:
            return await repository.load(tenant_id, options)
        except Exception:
            # Safe failure value avoids propagating driver details through an
            # ExceptionGroup. CancelledError still belongs to TaskGroup.
            return _error(502, 'options_failed')

    failure = None
    result = None
    # Reuse the disconnect/deadline helper with structured query lifetime.
    # Cancellation is joined before the request-scoped session can exit.
    async with asyncio.TaskGroup() as group:
        query = group.create_task(load())
        try:
            result = await _wait_result(request, query, FACTS_SECONDS)
        except AppException as error:
            failure = error
        finally:
            if failure is not None and not query.done():
                query.cancel()
    if failure is not None:
        raise failure
    if isinstance(result, AppException):
        raise result
    if result is None:
        raise _error(403, 'organization_unavailable')
    return result


@router.get('/options', response_model=OptionsResponse)
async def task_import_options(
    request: Request,
    membership=Depends(get_current_membership),
    repository: OptionsReader = Depends(get_options_repository),
) -> OptionsResponse:
    """Consulta opciones paginadas sin analizar archivos ni guardar datos.

    Requiere membresía y la bandera de vista previa. Solo esta consulta verifica
    además que la organización esté activa y no eliminada antes de leer nombres;
    no cambia la autenticación compartida ni las comprobaciones de /review.
    No impone roles adicionales. Los miembros se identifican por ID de usuario.

    Parámetros independientes: projects_page/members_page (1–1000, defecto 1),
    projects_size/members_size (1–100, defecto 20), projects_q/members_q
    (vacíos por defecto; se recortan espacios, de 2 a 100 caracteres si no vacíos).
    Rechaza claves desconocidas y repetidas. El proyecto predeterminado canónico
    no depende de los filtros ni de las páginas y puede ser nulo; nunca se crea.
    """
    if not settings.TASK_IMPORT_PREVIEW_ENABLED:
        raise _error(404, 'preview_disabled')
    params = request.query_params
    if (set(params) - OptionsQuery.model_fields.keys()
            or any(len(params.getlist(key)) != 1 for key in params)):
        raise _error(422, 'validation_error')
    try:
        options = OptionsQuery.model_validate(dict(params))
    except (ValidationError, ValueError):
        # No errors(), exception text or raw validation input in public errors.
        raise _error(422, 'validation_error') from None
    data = await _load_options(request, repository, str(membership.organization_id), options)
    return OptionsResponse(data=data)


def get_review_facts_repository(db=Depends(get_db)):
    # Lazy construction keeps the offline HTTP contract independent of ORM setup.
    # Production uses the very same request-scoped session dependency as auth.
    from .review_facts_repository import ReviewFactsRepository
    return ReviewFactsRepository(db)


async def _review_facts(request: Request, repository, context, decisions):
    # Adapter limits apply before its own deduplication, so deduplicate here.
    projects = list(dict.fromkeys(d.project_id for d in decisions if d.action == 'include'))
    users = list(dict.fromkeys(d.assignee_id for d in decisions if d.action == 'include'))
    if len(projects) > 1000 or len(users) > 1000:
        raise _error(422, 'facts_limit')

    async def load():
        try:
            return await repository.load(context.tenant_id, projects, users)
        except Exception:
            # Do not retain database exception strings or send them to clients.
            return None

    failure = None
    result = None
    # Structured lifetime: query cancellation is joined before the session can
    # exit, including disconnect and repeated external cancellation. No detached
    # DB query, retry worker, or independent session/transaction is created.
    async with asyncio.TaskGroup() as group:
        query = group.create_task(load())
        try:
            result = await _wait_result(request, query, FACTS_SECONDS)
        except AppException as error:
            failure = error
        finally:
            # On external cancellation TaskGroup alone owns cancellation; a
            # second cancel here could interrupt the driver's cleanup handler.
            if failure is not None and not query.done():
                query.cancel()
    if failure is not None:
        raise failure
    if result is None:
        raise _error(502, 'facts_failed')
    return result


@router.post('/review', response_model=ReviewResponse)
async def review_tasks(
    request: Request,
    membership=Depends(get_current_membership),
    runner: PreviewRunner = Depends(get_preview_runner),
    repository=Depends(get_review_facts_repository),
) -> ReviewResponse:
    """Revisa decisiones explícitas sin guardar fuentes ni crear tareas.

    JSON acotado con source_base64 y claves source_hash/sheet/row; el servidor
    vuelve a analizar los bytes. checklist-v1 identifica el perfil actual, no
    una autorización ni un token de importación. No infiere proyectos ni usuarios.
    """
    if not settings.TASK_IMPORT_PREVIEW_ENABLED:
        raise _error(404, 'preview_disabled')
    if request.query_params:
        raise _error(422, 'unsupported_options')
    if request.headers.get('content-type', '').split(';', 1)[0].strip().lower() != 'application/json':
        raise _error(415, 'unsupported_media_type')
    _acquire()
    job = None
    cancel = Event()
    try:
        raw = await _upload(request, MAX_REVIEW_BODY_BYTES)
        try:
            body = ReviewRequest.model_validate_json(raw, strict=True)
        except (ValidationError, ValueError):
            # Never use errors(), str(error), or FastAPI's body validation path:
            # they can reflect the entire source_base64 or arbitrary metadata.
            raise _error(422, 'validation_error') from None
        del raw
        try:
            data = base64.b64decode(body.source_base64, validate=True)
        except (ValueError, binascii.Error):
            raise _error(422, 'invalid_base64') from None
        if len(data) > MAX_INPUT_BYTES:
            raise _error(413, 'input_limit')
        # Reject noncanonical padding/trailing pad bits as well as invalid chars.
        if base64.b64encode(data).decode('ascii') != body.source_base64:
            raise _error(422, 'invalid_base64')
        decisions = body.to_domain()
        format, profile = body.format, body.profile
        del body
        job = _EXECUTOR.submit(runner.run, data, format=format, profile=profile, cancel=cancel)
        try:
            parsed = await _wait_result(request, job)
        except asyncio.CancelledError:
            await _cleanup(job, cancel)
            raise
        except BaseException:
            if not await _cleanup(job, cancel):
                raise _error(503, 'cleanup_failed') from None
            failure = job.exception()
            if isinstance(failure, PreviewRunnerError) and failure.code == 'cleanup_failed':
                raise _runner_error(failure) from None
            raise
        context = TrustedContext(str(membership.organization_id), str(membership.user_id))
        facts = await _review_facts(request, repository, context, decisions.decisions)
        return project_review(build_review_plan(parsed, PROFILE_VERSION, decisions, context, facts))
    except PreviewRunnerError as error:
        raise _runner_error(error) from None
    except (AppException, HTTPException, asyncio.CancelledError):
        raise
    except Exception:
        raise _error(502, 'review_failed') from None
    finally:
        _release_or_quarantine(job)
