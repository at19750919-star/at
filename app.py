"""Expose the FastAPI app for hosting platforms (e.g. Hugging Face Spaces)."""

from api.app import app  # re-export for uvicorn


if __name__ == "__main__":
    import os
    import uvicorn

    port = int(os.getenv("PORT", "7860"))
    uvicorn.run(app, host="0.0.0.0", port=port)
