from fastapi import APIRouter, Depends, HTTPException, Request

from app.application.service import TroubleshootingService
from app.application.security_service import SecurityValidationService
from app.domain.models import ChatRequest, DiagnoseRequest, Review, ReviewRequest

router = APIRouter(prefix="/api")


def get_service(request: Request) -> TroubleshootingService:
    return request.app.state.service


def get_security_service() -> SecurityValidationService:
    return SecurityValidationService()


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "netsage-ai"}


@router.get("/cases")
def cases(service: TroubleshootingService = Depends(get_service)):
    return service.list_cases()


@router.post("/diagnose")
def diagnose(request: DiagnoseRequest, service: TroubleshootingService = Depends(get_service)):
    try:
        return service.diagnose(request.case_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Case not found")


@router.get("/cases/{case_id}/validate")
def validate(case_id: str, service: TroubleshootingService = Depends(get_service)):
    """HTTP view of the same read-only evidence checker exposed through MCP."""
    try:
        findings = service.validate(case_id)
        return {
            "tool": "validate_network_evidence",
            "transport_endpoint": "/mcp",
            "findings": [finding.model_dump() for finding in findings],
            "safety_note": "MCP findings are advisory. A named human must review any proposed fix.",
        }
    except KeyError:
        raise HTTPException(status_code=404, detail="Case not found")


@router.post("/cases/{case_id}/review")
def review(case_id: str, request: ReviewRequest, service: TroubleshootingService = Depends(get_service)):
    try:
        return service.review(case_id, Review(case_id=case_id, **request.model_dump()))
    except KeyError:
        raise HTTPException(status_code=404, detail="Case not found")
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error))


@router.post("/chat")
def chat(request: ChatRequest, service: TroubleshootingService = Depends(get_service)):
    try:
        return service.chat(
            request.message,
            request.history,
            case_id=request.case_id,
            include_case_context=request.include_case_context,
        )
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error))


@router.get("/ai/status")
def ai_status(request: Request):
    llm = getattr(request.app.state.service, "llm", None)
    if not llm:
        return {"active_backend": "fallback", "note": "Live model client not configured"}
    return llm.status()


@router.get("/dashboard")
def dashboard(service: TroubleshootingService = Depends(get_service)):
    return service.summary()


@router.get("/spreadsheet")
def spreadsheet(service: TroubleshootingService = Depends(get_service)):
    return service.get_spreadsheet()



@router.get("/security/validate/{case_id}")
def validate_case_security(
    case_id: str,
    service: TroubleshootingService = Depends(get_service),
    security_service: SecurityValidationService = Depends(get_security_service),
):
    """Validate a case for security issues against NIST/CIS standards"""
    try:
        cases = service.list_cases()
        case = next((c for c in cases if c.case_id == case_id), None)
        if not case:
            raise HTTPException(status_code=404, detail="Case not found")
        return security_service.validate_case(case)
    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error))


@router.post("/security/validate-diagnosis/{case_id}")
def validate_diagnosis_security(
    case_id: str,
    diagnosis: dict,
    service: TroubleshootingService = Depends(get_service),
    security_service: SecurityValidationService = Depends(get_security_service),
):
    """Validate a diagnosis for security implications"""
    try:
        cases = service.list_cases()
        case = next((c for c in cases if c.case_id == case_id), None)
        if not case:
            raise HTTPException(status_code=404, detail="Case not found")
        return security_service.validate_diagnosis(case, diagnosis)
    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error))
