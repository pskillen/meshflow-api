#!/bin/bash
set -e

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" <<-EOSQL
    CREATE USER meshflow WITH PASSWORD 'meshflow';
    CREATE DATABASE meshflow;
    GRANT ALL PRIVILEGES ON DATABASE meshflow TO meshflow;
    ALTER USER meshflow WITH SUPERUSER;
EOSQL
