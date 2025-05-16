# Meshflow API

Meshflow is a distributed telemetry collection system designed for Meshtastic radio networks. It provides a secure,
structured backend to ingest, store, and analyze public packets broadcast across geographically distributed mesh nodes.
The system is intended to be self-hosted, Dockerized, and built using Django REST Framework with PostgreSQL as the
backing store.

---

## 🔧 Project Structure

This repository will contain the backend API for Meshflow, organized as a modular Django project with the following
apps:

- **Nodes** – manages radios (Meshtastic nodes) and their API keys
- **Constellations** – groups of nodes managed collectively
- **Regions** – geographical groupings used to partition mesh data
- **Packets** – ingestion and processing of raw mesh packets
- **Users** – standard Django users, acting as SysOps in node context
- **Common** – shared utilities, permissions, middleware, etc.

Root layout:

```
Meshflow/
├── manage.py
├── Meshflow/                # Django settings, urls, wsgi
├── Nodes/
├── Packets/
├── Constellations/
├── Regions/
├── Users/
└── Common/
```

---

## 🚀 Components

- **Meshflow API** – the Django-based backend (this project)
- **Meshflow Relay** – lightweight local client running beside a Meshtastic node
- **Meshflow Dashboard** – React-based frontend for visualizing and managing mesh activity

---

## 🌐 API Overview (planned)

All endpoints will be namespaced under `/api/v1/`.

```
/api/v1/
├── auth/
├── packets/ingest/           # POST endpoint for Meshflow Relay
├── nodes/                    # Manage and list nodes
├── nodes/<id>/apikeys/       # Rotate/manage node API keys
├── constellations/           # Group nodes for SysOp management
├── regions/                  # List regions, get stats
├── stats/global/             # Public stats
├── stats/my-nodes/           # SysOp-specific metrics
```

---

## ⚙️ Tech Stack

- Python 3.x
- Django 4.x
- Django REST Framework
- PostgreSQL
- Docker / Docker Compose

---

## 🛠️ Setup Instructions

### Development Setup

```bash
# Clone and enter repo
cd Meshflow

# Install dependencies
pip install -r requirements.txt

# Run migrations
python manage.py migrate

# Start development server
python manage.py runserver
```

### Production Deployment

The application is designed to be deployed as Docker containers. For production deployment, follow these steps:

1. Create a `.env` file with the following variables:
   ```
   SECRET_KEY=your_secure_secret_key
   ```

2. Deploy using Docker Compose:
   ```bash
   docker-compose up -d
   ```

This will start three services:
- **PostgreSQL database** (port 5432)
- **Django API** (port 8000)
- **API Documentation** using Redocly (port 8080)

#### Production Configuration

The production deployment uses:
- Gunicorn as the WSGI server
- Whitenoise for static file serving
- Enhanced security settings
- Redocly for OpenAPI documentation

#### Accessing the API Documentation

There are two options for accessing the API documentation:

1. **Standalone Redocly Server**: Available at `http://your-server:8080`
2. **Integrated Documentation**: The Django application also serves documentation at:
   - Redoc UI: `http://your-server:8000/docs/`
   - Swagger UI: `http://your-server:8000/swagger/`
   - Raw OpenAPI JSON: `http://your-server:8000/openapi.json`

The integrated documentation is automatically generated from the API endpoints and is always up-to-date with the codebase.

#### Cloudflare Tunnel Configuration

When using Cloudflare Tunnels, ensure you configure the tunnel to route traffic to both services:
- Route API requests to `http://localhost:8000`
- Route documentation requests to `http://localhost:8080`

No additional CDN or cache configuration is needed for static files as they are efficiently served by Whitenoise.

---

## 🧭 Philosophy

Meshflow is designed to be:

- **Transparent** – SysOps and the public can see activity and trends
- **Modular** – easy to extend, replace, or separate components
- **Open** – friendly to community deployment and contribution

---

## 📌 Status

> 🧪 Currently pre-alpha. The core architecture and structure are being scaffolded.
