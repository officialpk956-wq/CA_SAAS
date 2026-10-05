from fastapi import FastAPI, Depends
from .dependencies import get_db
from .routers import clients, import_batches, reconciliation, resolutions, exports, categories, sales, worksheet, board, assist, auth, firm, ims, requests

app = FastAPI(title="GST Helper API")

# No CORS: the browser reaches the API through the Next.js /api proxy (same origin), so the
# SameSite=Strict session cookie is sent and no cross-origin access needs to be allowed.

app.include_router(clients.router)
app.include_router(import_batches.router)
app.include_router(reconciliation.router)
app.include_router(resolutions.router)
app.include_router(exports.router)
app.include_router(categories.router)
app.include_router(sales.router)
app.include_router(worksheet.router)
app.include_router(board.router)
app.include_router(assist.router)
app.include_router(auth.router)
app.include_router(firm.router)
app.include_router(ims.router)
app.include_router(requests.router)

@app.get("/health/live")
async def live():
    return {"status": "ok"}

@app.get("/health/ready")
async def ready(db=Depends(get_db)):
    from sqlalchemy import text
    await db.execute(text("SELECT 1"))
    return {"status": "ready"}
