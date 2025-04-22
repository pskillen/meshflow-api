# Meshflow API Documentation

## Authentication Endpoints

| Endpoint              | POST | GET | PUT | DELETE | Description                   |
|-----------------------|------|-----|-----|--------|-------------------------------|
| `/api/token/`         | ✅    | ❌   | ❌   | ❌      | Obtain JWT token pair (login) |
| `/api/token/refresh/` | ✅    | ❌   | ❌   | ❌      | Refresh JWT token             |
| `/api/token/verify/`  | ✅    | ❌   | ❌   | ❌      | Verify JWT token              |

## Nodes API

Auth: `JWT, User API key, Django Session Auth`

| Endpoint           | POST | GET | PUT | DELETE | Description                            |
|--------------------|------|-----|-----|--------|----------------------------------------|
| `/api/nodes/`      | ✅    | ✅   | ❌   | ❌      | List all nodes or create a new node    |
| `/api/nodes/{id}/` | ❌    | ✅   | ✅   | ✅      | Get, update, or delete a specific node |

## API Keys Management

Auth: `JWT, User API key, Django Session Auth`

| Endpoint                    | POST | GET | PUT | DELETE | Description                               |
|-----------------------------|------|-----|-----|--------|-------------------------------------------|
| `/api/nodes/api-keys/`      | ✅    | ✅   | ❌   | ❌      | List all API keys or create a new API key |
| `/api/nodes/api-keys/{id}/` | ❌    | ✅   | ✅   | ✅      | Get, update, or delete a specific API key |

## Packets API

Auth: `Node API key`

| Endpoint               | POST | GET | PUT | DELETE | Description                                                             |
|------------------------|------|-----|-----|--------|-------------------------------------------------------------------------|
| `/api/packets/ingest/` | ✅    | ❌   | ❌   | ❌      | Ingest new packets into the system                                      |
| `/api/packets/nodes/`  | ✅    | ❌   | ❌   | ❌      | Allows posting node info from the listener node, via the node's API key |

## Constellations API

Auth: `JWT, User API key, Django Session Auth`

| Endpoint                    | POST | GET | PUT | DELETE | Description                                           |
|-----------------------------|------|-----|-----|--------|-------------------------------------------------------|
| `/api/constellations/`      | ✅    | ✅   | ❌   | ❌      | List all constellations or create a new constellation |
| `/api/constellations/{id}/` | ❌    | ✅   | ✅   | ✅      | Get, update, or delete a specific constellation       |

## Admin Interface

Auth: `Django Session Auth`

| Endpoint  | POST | GET | PUT | DELETE | Description            |
|-----------|------|-----|-----|--------|------------------------|
| `/admin/` | ❌    | ✅   | ❌   | ❌      | Django admin interface |

## Notes

- Replace `{id}` in URLs with the actual ID of the resource
- The API follows RESTful principles
