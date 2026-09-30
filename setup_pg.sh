#!/bin/bash
service postgresql start
su - postgres -c "psql -c \"ALTER USER postgres WITH PASSWORD 'postgres';\""
su - postgres -c "createdb gst_copilot_dev"
su - postgres -c "createdb gst_copilot_test"
