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

## 🛠️ Setup Instructions (TBD)

This project is under initial development. Once bootstrapped, the following will apply:

```bash
# Clone and enter repo
cd Meshflow

# Install dependencies
pip install -r requirements/dev.txt

# Run migrations
python manage.py migrate

# Start development server
python manage.py runserver
```

Docker setup will be included via `docker-compose.yml`.

---

## 🧭 Philosophy

Meshflow is designed to be:

- **Transparent** – SysOps and the public can see activity and trends
- **Modular** – easy to extend, replace, or separate components
- **Open** – friendly to community deployment and contribution

---

## 📌 Status

> 🧪 Currently pre-alpha. The core architecture and structure are being scaffolded.

