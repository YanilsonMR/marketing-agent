"""
Marketing Agent — FastAPI backend.

Exposes the same functionality as the CLI (main.py) through REST endpoints.
The CLI continues to work independently.
"""

import json
import queue
import threading
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from config.settings import load_settings, Settings
from services.llm_service import LLMService
from services.template_service import TemplateService
from services.excel_service import ExcelService
from services.email_service import EmailService
from services.validator import validate_content
from services.logger import log_event
from main import call_llm, generate_with_validation, generate_content_for_lead
from autopilot import run_autopilot


# ─────────────────────────────────────────────
# REQUEST / RESPONSE MODELS
# ─────────────────────────────────────────────

class GenerateRequest(BaseModel):
    lead_id: str

class RegenerateRequest(BaseModel):
    lead_id: str
    feedback: str

class ApproveRequest(BaseModel):
    lead_id: str
    approved: bool

class SendRequest(BaseModel):
    lead_id: str

class DeleteRequest(BaseModel):
    lead_id: str

class AutopilotRequest(BaseModel):
    tier: str | None = None
    icp_rank: str | None = None


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def _read_all_outputs(excel: ExcelService) -> list[dict]:
    """Read all rows from the output sheet."""
    wb = excel._get_workbook()
    ws = wb["output"]
    records = excel._rows_as_dicts(ws)
    wb.close()
    return records


def _find_lead_by_id(excel: ExcelService, lead_id: str) -> dict | None:
    """Find a lead by ID from the leads sheet."""
    leads = excel.read_leads()
    for lead in leads:
        if str(lead.get("id", "")) == str(lead_id):
            return lead
    return None


# ─────────────────────────────────────────────
# LIFESPAN
# ─────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize services on startup."""
    settings = load_settings()
    app.state.settings = settings
    app.state.llm = LLMService(settings)
    app.state.templates = TemplateService(settings)
    app.state.excel = ExcelService(settings)
    app.state.email = EmailService(settings)
    app.state.pending_content = {}  # lead_id -> {lead, content, method}
    app.state.session = {
        "generated_ai": 0,
        "generated_template": 0,
        "approved": 0,
        "rejected": 0,
        "regenerated": 0,
        "sent": 0,
        "failed_send": 0,
    }
    yield


# ─────────────────────────────────────────────
# APP
# ─────────────────────────────────────────────

app = FastAPI(title="Marketing Agent API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─────────────────────────────────────────────
# SERVE FRONTEND
# ─────────────────────────────────────────────

FRONTEND_DIR = Path(__file__).parent / "frontend"

@app.get("/")
async def serve_frontend():
    """Serve the SPA."""
    index = FRONTEND_DIR / "index.html"
    if not index.exists():
        raise HTTPException(status_code=404, detail="frontend/index.html not found")
    return FileResponse(index, media_type="text/html")


# ─────────────────────────────────────────────
# ENDPOINTS
# ─────────────────────────────────────────────

@app.get("/api/stats")
async def get_stats():
    """Dashboard statistics."""
    excel: ExcelService = app.state.excel
    stats = excel.get_stats()
    stats["session"] = app.state.session
    return stats


@app.get("/api/leads")
async def get_leads(
    tier: str | None = Query(None, description="Filter by tier (1/2/3)"),
    icp_rank: str | None = Query(None, description="Filter by ICP rank (1/2/3)"),
):
    """List leads with optional filters."""
    excel: ExcelService = app.state.excel
    leads = excel.read_leads(tier=tier, icp_rank=icp_rank)
    existing_ids = excel.get_output_ids()

    result = []
    for lead in leads:
        lead_copy = dict(lead)
        lead_copy["has_output"] = str(lead.get("id", "")) in existing_ids
        result.append(lead_copy)

    return result


@app.get("/api/pending")
async def get_pending():
    """Outputs pending approval."""
    excel: ExcelService = app.state.excel
    return excel.get_pending_outputs()


@app.get("/api/unsent")
async def get_unsent():
    """Approved but unsent outputs."""
    excel: ExcelService = app.state.excel
    return excel.get_approved_unsent()


@app.get("/api/outputs")
async def get_outputs():
    """All output rows."""
    excel: ExcelService = app.state.excel
    return _read_all_outputs(excel)


@app.post("/api/generate")
async def generate(req: GenerateRequest):
    """Generate content for a lead. Stores in pending_content (memory), not Excel."""
    excel: ExcelService = app.state.excel
    settings: Settings = app.state.settings
    llm: LLMService = app.state.llm
    templates: TemplateService = app.state.templates

    lead = _find_lead_by_id(excel, req.lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail=f"Lead {req.lead_id} no encontrado")

    existing_ids = excel.get_output_ids()
    if str(lead["id"]) in existing_ids:
        raise HTTPException(status_code=409, detail="Este lead ya tiene contenido generado")

    content, attempts, failures, method = generate_content_for_lead(
        lead, llm, templates, settings,
    )

    if content is None:
        raise HTTPException(status_code=500, detail="Fallo la generacion de contenido")

    # Track in session
    if method == "ai":
        app.state.session["generated_ai"] += 1
    else:
        app.state.session["generated_template"] += 1

    # Log event
    tier = str(lead.get("tier", "3")).strip()
    log_event(
        lead_id=str(lead.get("id", "")),
        contact_name=lead.get("contact_name", ""),
        company=lead.get("company_name", ""),
        tier=tier,
        icp_rank=str(lead.get("icp_rank", "")),
        word_count_email=len(content.get("email_body", "").split()),
        action="generated",
        validation_passed="yes" if not failures else "no",
        validation_failures=", ".join(failures),
        attempts=attempts,
    )

    # Store in pending (memory) — not yet in Excel
    pending_id = str(uuid.uuid4())[:8]
    app.state.pending_content[req.lead_id] = {
        "pending_id": pending_id,
        "lead": lead,
        "content": content,
        "method": method,
        "attempts": attempts,
        "failures": failures,
    }

    return {
        "pending_id": pending_id,
        "lead_id": req.lead_id,
        "content": content,
        "method": method,
        "tier": tier,
        "attempts": attempts,
        "failures": failures,
        "validation_passed": len(failures) == 0,
    }


@app.post("/api/regenerate")
async def regenerate(req: RegenerateRequest):
    """Regenerate Tier 3 content with feedback. Updates pending_content."""
    settings: Settings = app.state.settings
    llm: LLMService = app.state.llm
    excel: ExcelService = app.state.excel

    lead = _find_lead_by_id(excel, req.lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail=f"Lead {req.lead_id} no encontrado")

    tier = str(lead.get("tier", "3")).strip()
    if tier != "3":
        raise HTTPException(status_code=400, detail="Solo se puede regenerar contenido Tier 3")

    new_content = call_llm(lead, llm, settings, feedback=req.feedback)
    if new_content is None:
        raise HTTPException(status_code=500, detail="Fallo la regeneracion")

    app.state.session["regenerated"] = app.state.session.get("regenerated", 0) + 1

    log_event(
        lead_id=str(lead.get("id", "")),
        contact_name=lead.get("contact_name", ""),
        company=lead.get("company_name", ""),
        tier=tier,
        icp_rank=str(lead.get("icp_rank", "")),
        word_count_email=len(new_content.get("email_body", "").split()),
        action="regenerated",
        regenerated="yes",
        feedback=req.feedback,
    )

    failures = validate_content(new_content, settings)

    # Update pending
    pending_id = str(uuid.uuid4())[:8]
    app.state.pending_content[req.lead_id] = {
        "pending_id": pending_id,
        "lead": lead,
        "content": new_content,
        "method": "ai",
        "attempts": 1,
        "failures": failures,
    }

    return {
        "pending_id": pending_id,
        "lead_id": req.lead_id,
        "content": new_content,
        "method": "ai",
        "tier": tier,
        "failures": failures,
        "validation_passed": len(failures) == 0,
    }


@app.post("/api/approve")
async def approve(req: ApproveRequest):
    """Approve or reject generated content. Writes to Excel."""
    excel: ExcelService = app.state.excel

    pending = app.state.pending_content.get(req.lead_id)
    if not pending:
        raise HTTPException(
            status_code=404,
            detail=f"No hay contenido pendiente para lead {req.lead_id}",
        )

    lead = pending["lead"]
    content = pending["content"]

    # Write to Excel
    excel.write_output(lead, content)
    excel.update_approval(str(lead["id"]), approved=req.approved)

    if req.approved:
        app.state.session["approved"] += 1
        action = "approved"
    else:
        app.state.session["rejected"] += 1
        action = "rejected"

    log_event(
        lead_id=str(lead.get("id", "")),
        contact_name=lead.get("contact_name", ""),
        company=lead.get("company_name", ""),
        tier=str(lead.get("tier", "")),
        icp_rank=str(lead.get("icp_rank", "")),
        action=action,
    )

    # Remove from pending
    del app.state.pending_content[req.lead_id]

    return {"status": action, "lead_id": req.lead_id}


@app.post("/api/review-approve")
async def review_approve(req: ApproveRequest):
    """Approve or reject content already in Excel (pending review items)."""
    excel: ExcelService = app.state.excel

    excel.update_approval(str(req.lead_id), approved=req.approved)

    if req.approved:
        app.state.session["approved"] += 1
        action = "approved"
    else:
        app.state.session["rejected"] += 1
        action = "rejected"

    log_event(
        lead_id=str(req.lead_id),
        action=action,
    )

    return {"status": action, "lead_id": req.lead_id}


@app.post("/api/discard")
async def discard_pending(req: DeleteRequest):
    """Discard pending content from memory (before approve/reject)."""
    pending = app.state.pending_content.pop(req.lead_id, None)
    if not pending:
        raise HTTPException(
            status_code=404,
            detail=f"No hay contenido pendiente en memoria para lead {req.lead_id}",
        )
    return {"status": "discarded", "lead_id": req.lead_id}


@app.post("/api/delete")
async def delete_output(req: DeleteRequest):
    """Delete generated content from Excel output sheet."""
    excel: ExcelService = app.state.excel

    deleted = excel.delete_output(str(req.lead_id))
    if not deleted:
        raise HTTPException(
            status_code=404,
            detail=f"No se encontro contenido para lead {req.lead_id}",
        )

    log_event(
        lead_id=str(req.lead_id),
        action="deleted",
    )

    return {"status": "deleted", "lead_id": req.lead_id}


@app.post("/api/send")
async def send_email(req: SendRequest):
    """Send email for one approved output."""
    excel: ExcelService = app.state.excel
    email_svc: EmailService = app.state.email

    unsent = excel.get_approved_unsent()
    target = None
    for row in unsent:
        if str(row.get("ID", "")) == str(req.lead_id):
            target = row
            break

    if not target:
        raise HTTPException(
            status_code=404,
            detail=f"No se encontro correo aprobado sin enviar para ID {req.lead_id}",
        )

    lead = _find_lead_by_id(excel, req.lead_id)
    lead_email = lead.get("email", "") if lead else ""

    if not lead_email:
        raise HTTPException(status_code=400, detail="El lead no tiene email registrado")

    success = email_svc.send(
        to_email=lead_email,
        subject=str(target["Email Subject"]),
        body=str(target["Email Body"]),
    )

    if success:
        excel.update_sent(str(req.lead_id))
        app.state.session["sent"] += 1
        log_event(
            lead_id=str(req.lead_id),
            contact_name=str(target.get("Contact Name", "")),
            action="sent",
        )
        return {"status": "sent", "lead_id": req.lead_id, "to": lead_email}

    app.state.session["failed_send"] += 1
    log_event(
        lead_id=str(req.lead_id),
        contact_name=str(target.get("Contact Name", "")),
        action="failed_send",
    )
    raise HTTPException(status_code=500, detail="Fallo el envio del email")


@app.post("/api/send-batch")
async def send_batch():
    """Send all approved but unsent emails."""
    excel: ExcelService = app.state.excel
    email_svc: EmailService = app.state.email
    settings: Settings = app.state.settings

    unsent = excel.get_approved_unsent()
    if not unsent:
        return {"sent": 0, "failed": 0, "message": "No hay correos pendientes de envio"}

    if len(unsent) > settings.max_daily_sends:
        unsent = unsent[:settings.max_daily_sends]

    leads = excel.read_leads()
    id_to_email = {str(l.get("id", "")): l.get("email", "") for l in leads}

    sent_count = 0
    failed_count = 0
    results = []

    for i, row in enumerate(unsent):
        lead_id = str(row.get("ID", ""))
        lead_email = id_to_email.get(lead_id, "")

        if not lead_email:
            failed_count += 1
            results.append({"lead_id": lead_id, "status": "no_email"})
            continue

        success = email_svc.send(
            to_email=lead_email,
            subject=str(row["Email Subject"]),
            body=str(row["Email Body"]),
        )

        if success:
            excel.update_sent(lead_id)
            app.state.session["sent"] += 1
            sent_count += 1
            log_event(
                lead_id=lead_id,
                contact_name=str(row.get("Contact Name", "")),
                action="sent",
            )
            results.append({"lead_id": lead_id, "status": "sent", "to": lead_email})
        else:
            app.state.session["failed_send"] += 1
            failed_count += 1
            log_event(
                lead_id=lead_id,
                contact_name=str(row.get("Contact Name", "")),
                action="failed_send",
            )
            results.append({"lead_id": lead_id, "status": "failed"})

        if i < len(unsent) - 1:
            time.sleep(settings.send_delay)

    return {"sent": sent_count, "failed": failed_count, "results": results}


@app.get("/api/autopilot/stream")
async def autopilot_stream(
    request: Request,
    tier: str | None = Query(None),
    icp_rank: str | None = Query(None),
):
    """Run autopilot with SSE progress stream."""
    progress_queue: queue.Queue = queue.Queue()

    def on_progress(current, total, lead_name, status):
        progress_queue.put({
            "event": "progress",
            "current": current,
            "total": total,
            "lead_name": lead_name,
            "status": status,
        })

    def run_in_thread():
        try:
            summary = run_autopilot(
                tier=tier,
                icp_rank=icp_rank,
                dry_run=False,
                on_progress=on_progress,
            )
            progress_queue.put({"event": "done", **summary})
        except Exception as e:
            progress_queue.put({"event": "error", "detail": str(e)})

    thread = threading.Thread(target=run_in_thread, daemon=True)
    thread.start()

    async def event_generator():
        while True:
            if await request.is_disconnected():
                break
            try:
                msg = progress_queue.get(timeout=0.5)
            except queue.Empty:
                # Send keep-alive comment to prevent timeout
                yield ": keep-alive\n\n"
                continue

            yield f"data: {json.dumps(msg)}\n\n"

            if msg.get("event") in ("done", "error"):
                break

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/autopilot")
async def autopilot(req: AutopilotRequest = AutopilotRequest()):
    """Run autopilot (non-streaming). Returns summary JSON."""
    try:
        summary = run_autopilot(
            tier=req.tier,
            icp_rank=req.icp_rank,
            dry_run=False,
        )
        return summary
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────────
# RUN
# ─────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=True)
