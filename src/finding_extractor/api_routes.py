"""API routers for report/extraction/correction endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response

from finding_extractor.api_dependencies import get_model_catalog_service, get_store
from finding_extractor.api_models import (
    CorrectionResponse,
    CreateCorrectionRequest,
    ExtractionDetailResponse,
    ExtractionSummaryResponse,
    JobResponse,
    ModelCatalogResponse,
    ReportDetailResponse,
    ReportResponse,
    SubmitReportRequest,
    TriggerExtractionRequest,
    TriggerExtractionResponse,
    map_correction,
    map_extraction_detail,
    map_extraction_summary,
    map_job,
    map_model_catalog,
    map_report,
    map_report_detail,
)
from finding_extractor.api_services import (
    enqueue_extraction_job,
    require_extraction,
    require_report,
)
from finding_extractor.model_catalog import ModelCatalogService
from finding_extractor.store import ExtractionStore

router = APIRouter(prefix="/api")


@router.get("/models", response_model=ModelCatalogResponse)
async def list_models(
    model_catalog: Annotated[ModelCatalogService, Depends(get_model_catalog_service)],
) -> ModelCatalogResponse:
    catalog = await model_catalog.get_catalog()
    return map_model_catalog(catalog)


@router.post("/reports", response_model=ReportResponse)
async def submit_report(
    body: SubmitReportRequest,
    store: Annotated[ExtractionStore, Depends(get_store)],
) -> ReportResponse:
    report = await store.upsert_report(body.report_text, source_ref=body.source_ref)
    return map_report(report)


@router.get("/reports", response_model=list[ReportResponse])
async def list_reports(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    *,
    store: Annotated[ExtractionStore, Depends(get_store)],
) -> list[ReportResponse]:
    reports = await store.list_reports(limit=limit, offset=offset)
    return [map_report(report) for report in reports]


@router.get("/reports/{report_id}", response_model=ReportDetailResponse)
async def get_report(
    report_id: str,
    *,
    store: Annotated[ExtractionStore, Depends(get_store)],
) -> ReportDetailResponse:
    report = await require_report(store, report_id)
    return map_report_detail(report)


@router.post(
    "/reports/{report_id}/extract",
    status_code=202,
    response_model=TriggerExtractionResponse,
)
async def trigger_extraction(
    report_id: str,
    body: TriggerExtractionRequest,
    request: Request,
    response: Response,
    *,
    store: Annotated[ExtractionStore, Depends(get_store)],
) -> TriggerExtractionResponse:
    job_id = await enqueue_extraction_job(
        store=store,
        run_extraction_task=request.app.state.run_extraction_task,
        report_id=report_id,
        body=body,
    )
    response.headers["Location"] = f"/api/jobs/{job_id}"
    response.headers["Retry-After"] = "2"
    return TriggerExtractionResponse(job_id=job_id, report_id=report_id, status="pending")


@router.get("/jobs/{job_id}", response_model=JobResponse)
async def get_job_status(
    job_id: str,
    *,
    store: Annotated[ExtractionStore, Depends(get_store)],
) -> JobResponse:
    job = await store.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return map_job(job)


@router.get("/reports/{report_id}/extractions", response_model=list[ExtractionSummaryResponse])
async def list_report_extractions(
    report_id: str,
    *,
    store: Annotated[ExtractionStore, Depends(get_store)],
) -> list[ExtractionSummaryResponse]:
    await require_report(store, report_id)
    extractions = await store.list_extractions(report_id)
    return [map_extraction_summary(extraction) for extraction in extractions]


@router.get("/extractions/{extraction_id}", response_model=ExtractionDetailResponse)
async def get_extraction(
    extraction_id: str,
    *,
    store: Annotated[ExtractionStore, Depends(get_store)],
) -> ExtractionDetailResponse:
    extraction = await require_extraction(store, extraction_id)
    return map_extraction_detail(extraction)


@router.post(
    "/extractions/{extraction_id}/corrections",
    status_code=201,
    response_model=CorrectionResponse,
)
async def create_correction(
    extraction_id: str,
    body: CreateCorrectionRequest,
    *,
    store: Annotated[ExtractionStore, Depends(get_store)],
) -> CorrectionResponse:
    await require_extraction(store, extraction_id)
    try:
        correction = await store.record_correction(
            extraction_id=extraction_id,
            correction_type=body.correction_type,
            target_finding_index=body.target_finding_index,
            target_json_path=body.target_json_path,
            proposed_finding=body.proposed_finding,
            attribute_overrides=body.attribute_overrides,
            comment=body.comment,
            created_by=body.created_by,
            status=body.status,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return map_correction(correction)


@router.get("/extractions/{extraction_id}/corrections", response_model=list[CorrectionResponse])
async def list_extraction_corrections(
    extraction_id: str,
    *,
    store: Annotated[ExtractionStore, Depends(get_store)],
) -> list[CorrectionResponse]:
    await require_extraction(store, extraction_id)
    corrections = await store.list_corrections(extraction_id)
    return [map_correction(correction) for correction in corrections]
