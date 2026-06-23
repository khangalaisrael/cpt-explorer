-- Run this in Supabase SQL editor before deploying n8n.
-- Creates a separate schema so n8n tables don't mix with our app tables.
CREATE SCHEMA IF NOT EXISTS n8n;
