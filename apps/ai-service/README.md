# Truvix AI Service

Brief project description: The AI microservice for the Truvix platform, responsible for handling LLM integrations, chat completions, image analysis, and vector embeddings.

## Setup

This project uses `uv` for dependency management. Requires Python >= 3.14.

```bash
uv venv
uv pip install -e .
uv pip install -e ".[vector]" # Optional vector dependencies
```

## Running

```bash
make run
```

## Environment Variables

See `.env.example` for a full list of configuration options.

## API Endpoints

- `/healthz`: Health check
- `/analysis`: Image and text analysis endpoints
- `/copilot`: Chat endpoints
- `/embeddings`: Vector embeddings endpoints

## Architecture

Built with FastAPI, using httpx for async API calls to LLM providers. Includes robust error handling and graceful degradation.
