# Product Requirements: Truvix

## Product Vision
An AI-powered second-hand vehicle evaluation platform for the Turkish market, providing buyers with transparency, risk analysis, and peace of mind through advanced computer vision and LLM technologies.

## Target Audience
- Individual car buyers in Turkey looking for reliable second-hand vehicles.
- Users who want expert-level insights without necessarily paying for a full physical inspection immediately.

## Core Features (MVP)
- **Garage Management:** Users can add, edit, and track vehicles they are interested in buying.
- **AI Photo Analysis:** Users can upload photos of vehicles to get an AI-generated assessment of physical condition.
- **Trust Scoring:** A proprietary 0-100 score indicating the overall reliability and condition of the vehicle.
- **Risk Findings:** Detailed list of potential issues (low, medium, high severity) detected by AI.
- **Price Tracking:** Historical price trends for saved vehicles.
- **AI Copilot:** An intelligent chat interface to ask questions about the vehicle's condition, market value, and maintenance.

## Premium Features
- Higher quotas for AI analysis.
- Priority processing in the AI pipeline.
- Unlimited Copilot messages.
- Side-by-side vehicle comparison tools.

## User Stories
1. As a buyer, I want to add a vehicle to my garage so that I can track its details.
2. As a buyer, I want to upload photos of a car so that AI can find hidden damages.
3. As a buyer, I want to see a Trust Score so that I quickly know if the car is worth pursuing.
4. As a buyer, I want to chat with the AI Copilot so that I can ask specific questions about the analysis findings.
5. As a buyer, I want to see the price history of a vehicle so that I can negotiate better.
6. As a buyer, I want to receive notifications when a tracked vehicle's price drops.
7. As a buyer, I want to group vehicles into collections (e.g., "Favorites") for better organization.
8. As a premium user, I want unlimited AI analysis so that I can evaluate as many cars as I want.

## Quota Limits

| Feature | Free Tier | Premium Tier |
| :--- | :--- | :--- |
| Vehicles in Garage | 5 | Unlimited |
| Analyses per Day | 1 | 20 |
| Copilot Messages / Car | 5 | Unlimited |
| Price Tracking | Active | Active (Real-time updates) |

## Non-functional Requirements
- **Performance:** API response times must be <2s for standard endpoints.
- **Availability:** Target 99.9% uptime.
- **Compliance:** Must be fully compliant with KVKK (Turkish Data Protection Law).
- **Localization:** Turkish language first; all AI summaries and UI elements in Turkish.

## Competitive Landscape
- **AutoLens:** Focuses only on computer vision for damage detection. Truvix offers a conversational Copilot and trust scoring.
- **OtoBoss:** A traditional expert network. Truvix acts as the AI pre-screening step before engaging with physical experts.
