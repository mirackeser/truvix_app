# Truvix API Reference

**Base URL:** `https://api.truvix.app/api/v1`

## Overview
The Truvix API is a RESTful service built with FastAPI. All endpoints (except public auth endpoints) require JWT authentication.

For the interactive Swagger UI and full OpenAPI schema, see:
- Path: `apps/backend/docs/openapi.json`
- URL (Local): `http://localhost:8000/docs`

## Authentication
Authentication uses the OAuth2 Password Bearer flow with JWTs.

1. **Login:** Submit email/password to `/auth/login` to receive an `access_token` and `refresh_token`.
2. **Authorize:** Include the token in the header: `Authorization: Bearer <your_token>`

## Error Format
Errors follow the RFC 9457 Problem Details standard:
```json
{
  "type": "https://api.truvix.app/errors/validation-error",
  "title": "Validation Error",
  "status": 400,
  "detail": "Price must be a positive number."
}
```

## Endpoint Groups

### Auth
- `POST /auth/register`: Create a new user account.
- `POST /auth/login`: Authenticate and get JWT.
- `POST /auth/refresh`: Get a new access token using a refresh token.

### Dashboard
- `GET /dashboard/summary`: Get overview of user's garage, recent analyses, and alerts.

### Vehicles
- `GET /vehicles`: List all vehicles in garage.
- `POST /vehicles`: Add a new vehicle.
- `GET /vehicles/{id}`: Get vehicle details.
- `GET /vehicles/{id}/price-history`: Get price trend data.

### Analyses
- `POST /analyses`: Start a new AI analysis (requires photo upload).
- `GET /analyses/{id}`: Get full analysis results and risk findings.

### Copilot
- `POST /copilot/conversations`: Start a new chat context for a vehicle.
- `POST /copilot/conversations/{id}/messages`: Send a message to the AI and receive a reply.

### Notifications
- `GET /notifications`: List recent notifications.
- `PUT /notifications/{id}/read`: Mark as read.

### Collections
- `GET /collections`: List user collections (e.g. Favorites).

## Rate Limiting
- Free users: 100 requests per minute.
- Premium users: 500 requests per minute.
- Status is returned in headers: `X-RateLimit-Limit`, `X-RateLimit-Remaining`.

## Example Usage

**Login:**
```bash
curl -X POST https://api.truvix.app/api/v1/auth/login \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=demo@truvix.app&password=Demo123!"
```

**Create Vehicle:**
```bash
curl -X POST https://api.truvix.app/api/v1/vehicles \
  -H "Authorization: Bearer <TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"brand": "BMW", "model": "320i", "price": 1850000}'
```
