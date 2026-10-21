# Bihar Live — Patna and Muzaffarpur

The Bihar Live entry opens the Patna and Muzaffarpur VarshaGuard project at [varshaguardoff.vercel.app](https://varshaguardoff.vercel.app).

The WIP switcher points to `/bihar-live.html`, which forwards visitors to this dashboard. The main VarshaGuard dashboard remains unchanged.

## Coverage

- Patna and Muzaffarpur, Bihar
- Location-aware grid cells

## Status and use

This dashboard is a prototype. Live public weather observations do not make flood predictions operationally validated. Treat any demonstration risk screen as informational only; follow official IMD, CWC, and local disaster-management alerts for safety decisions.

Browser location access is optional. The dashboard can use it to center the map on the user's current position.

## Source and setup

The application source and setup instructions are in [sarthak-shree/VarshaGuard](https://github.com/sarthak-shree/VarshaGuard). Keep API keys in local environment variables; do not commit `.env` files.
