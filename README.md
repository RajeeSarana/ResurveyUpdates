# ResurveyUpdates - Progress Monitoring Portal

A modern, mobile-responsive web application and data collection portal designed to track 100% completed villages under the **Cadastral & Non-Cadastral Resurvey** project across all 32 project districts (as on 04.09.2026).

---

## Key Features

- **Pre-populated Baseline Data**: Includes all 32 districts, targets (373 Non-Cadastral, 2,236 Cadastral), and exact baseline records with Telugu script support (`బాబాపూర్`, `రోజాపూర్`, etc.).
- **Role-Based Member Access**: Role switcher for State CSO Admin, District Nodal Officers (Asifabad, Nizamabad, Medak, Siddipet, etc.), and Guest Viewers.
- **Acres - Guntas Support**: Direct entry of standard survey notation (e.g. `1376-39`) with live automatic decimal acre conversion.
- **Shapefile Transmission Tracker**: Instant breakdown of Completed, Error, and In Progress shapefiles submitted to CSO.
- **Interactive Visualizations**: Real-time KPI summary cards, top districts bar chart, and shapefile health donut chart.
- **One-Click Official Excel Export**: Generates `.xlsx` matching the official department report format.
- **Cloud & Mobile Ready**: Tested for Vercel, Render, and Docker deployment with MongoDB Atlas.

---

## Quick Start (Local Run)

```bash
# 1. Clone or navigate to the project
cd ResurveyUpdates

# 2. Run the application
.\.venv\Scripts\python.exe run_local.py
```
Open **[http://127.0.0.1:8000](http://127.0.0.1:8000)** in your browser.

---

## Deploying to Public Cloud (Vercel & MongoDB Atlas)

See detailed step-by-step instructions in [DEPLOYMENT_VERCEL.md](DEPLOYMENT_VERCEL.md).
