# Contributing to Ragnetic

First off, thank you for considering contributing to Ragnetic! It's people like you that make Ragnetic a great tool for the open-source community.

## Development Setup

The project is structured as a monorepo consisting of a Next.js frontend and a FastAPI backend.

### Prerequisites

- You need Docker and Docker Compose installed.
- Node.js 20+ (for frontend development)
- Python 3.11+ (for backend development)

### Running Services for Development

Rather than running the full docker-compose which builds production images, you can run the infrastructure dependencies via Docker and run the Frontend and Backend locally:

1. **Start infrastructure (Postgres, Qdrant, Redis):**
   ```bash
   # We will provide a specific command for just infrastructure soon.
   # For now, running `docker-compose up` is the default way.
   ```

2. **Backend Development:**
   ```bash
   cd backend
   python -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   uvicorn app.main:app --reload
   ```

3. **Frontend Development:**
   ```bash
   cd frontend
   npm install
   npm run dev
   ```

## Pull Request Process

1. Fork the repository and create your branch from `main`.
2. Ensure you have tested your changes locally.
3. Update documentation if necessary (e.g., README, API docs).
4. Create a Pull Request with a clear description of the problem solved or feature added.

## Code Standards

- **Python**: We use `black` for formatting and `flake8` for linting. Please ensure your code is formatted before submitting. Use type hints extensively.
- **TypeScript**: We use Prettier and ESLint. Ensure no TypeScript errors or warnings exist.

## Good First Issues

Look for issues labeled `good first issue` to start contributing. We provide mentorship on these issues!

## Code of Conduct

Please note that we have a Code of Conduct, please follow it in all your interactions with the project.
