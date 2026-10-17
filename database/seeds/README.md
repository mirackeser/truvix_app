# Truvix Demo Seeds

This directory contains the database seeds for the Truvix platform, providing realistic demo data for testing and development.

## Contents
The `seed.sql` script creates:
- 1 premium user account
- 5 vehicles with diverse attributes (brand, model, price, etc.) localized for Turkey
- 2 completed AI analyses with trust scores and summaries
- 4 risk findings of varying severities
- Realistic price histories spanning the last 5 months
- Notifications and collections

## How to Load

To apply these seeds to your local PostgreSQL database, use the `psql` command. Ensure your database container is running and migrations are applied before running this.

```bash
psql -h localhost -p 5432 -U truvix_user -d truvix_db -f database/seeds/seed.sql
```

## Demo Credentials

You can use the following credentials to log in to the iOS application or the API:

- **Email:** `demo@truvix.app`
- **Password:** `Demo123!`

> **Warning:** Do NOT use these seeds or credentials in a production environment. The password hash is publicly known.
