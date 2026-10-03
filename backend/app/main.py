from fastapi import FastAPI

app = FastAPI(title="ChainSight API")


@app.get("/health")
def health():
    return {"status": "ok"}
