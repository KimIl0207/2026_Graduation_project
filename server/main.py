import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routes import correction, detection, health, kakao


app = FastAPI(
    title="AI Detection API",
    description="Image and text AI detection server",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(detection.router)
app.include_router(correction.router)
app.include_router(kakao.router)


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port)
