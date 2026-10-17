# Truvix

**AI-Powered Vehicle Analysis Platform**

Truvix is a vehicle analysis platform designed to help users make more informed decisions when evaluating vehicles. It combines AI-powered analysis, backend services, and an iOS application within a modular software architecture.

## Key Features

- **AI Vehicle Analysis:** An AI service designed to support vehicle analysis using text and image inputs.
- **Vision-Based Analysis:** Image processing capabilities for analyzing vehicle-related visual information.
- **AI Copilot:** An assistant service designed to support users throughout the analysis process.
- **Backend Architecture:** Modular backend services and shared transaction handling.
- **iOS Application:** A dedicated iOS application structure with reusable design assets.
- **Infrastructure and Monitoring:** Docker configurations, Nginx, Prometheus, Grafana dashboards, and alerting rules.
- **Database Seeding:** SQL seed files to support development and testing workflows.

## Technology Stack

- **Languages:** Swift, Python, SQL
- **AI:** LLM integration, image analysis, embeddings
- **Backend:** API-oriented modular architecture
- **Infrastructure:** Docker, Nginx
- **Monitoring:** Prometheus, Grafana
- **Version Control:** Git and GitHub

## Project Structure

```text
Truvix_app/
├── apps/
│   ├── ai-service/
│   ├── backend/
│   └── ios/
├── database/
│   └── seeds/
├── docs/
│   ├── 01_product/
│   ├── 02_architecture/
│   └── api/
└── infra/
    ├── ci/
    ├── compose/
    └── monitoring/
```

## Engineering Focus

Truvix is organized around modularity, maintainability, API-based communication, AI service integration, and operational observability. The repository includes product requirements, architecture documentation, database resources, infrastructure configurations, and CI smoke-test scripts.

## Project Status

Under active development. Features and implementation details may evolve as the project progresses.

## Author

**Miraç Keser**

Software Engineering Student

GitHub: [@mirackeser](https://github.com/mirackeser)
