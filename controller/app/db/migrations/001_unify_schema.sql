-- Migration: Unify Organizations and Orchestrator Instances
-- Date: 2025-11-02
-- Description: 
--   1. Merge organizations + orchestrator_instances into single organizations table
--   2. Replace orchestrator_messages with org_statistics (counters only)
--   3. Remove is_independent columns (orchestrator-side concern)

-- ============================================================================
-- STEP 1: Create new unified organizations table
-- ============================================================================

CREATE TABLE IF NOT EXISTS organizations_new (
    -- Primary identifiers
    org_id VARCHAR(255) PRIMARY KEY,
    org_name VARCHAR(255) NOT NULL,
    
    -- Orchestrator connection info
    orchestrator_id VARCHAR(255) UNIQUE,
    
    -- Status tracking
    status VARCHAR(50) DEFAULT 'inactive',  -- active/inactive/error
    last_seen TIMESTAMP,
    connected_at TIMESTAMP,
    
    -- Keepalive tracking
    keepalive_enabled BOOLEAN DEFAULT true,  -- Does this org send keepalives?
    
    -- Metadata
    location VARCHAR(255),
    ip_address VARCHAR(50),
    features JSONB DEFAULT '{}'::jsonb,
    
    -- Contact information (optional)
    admin_email VARCHAR(255),
    support_email VARCHAR(255),
    website VARCHAR(255),
    
    -- Timestamps
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_organizations_new_status ON organizations_new(status);
CREATE INDEX IF NOT EXISTS idx_organizations_new_last_seen ON organizations_new(last_seen);
CREATE INDEX IF NOT EXISTS idx_organizations_new_orchestrator_id ON organizations_new(orchestrator_id);

-- ============================================================================
-- STEP 2: Create new org_statistics table (counters only)
-- ============================================================================

CREATE TABLE IF NOT EXISTS org_statistics (
    org_id VARCHAR(255) PRIMARY KEY REFERENCES organizations_new(org_id) ON DELETE CASCADE,
    
    -- Prompt counters by domain
    total_prompts INTEGER DEFAULT 0,
    prompts_by_domain JSONB DEFAULT '{}'::jsonb,  -- {"finance": 150, "legal": 200, ...}
    
    -- Message counters
    total_recommendations INTEGER DEFAULT 0,
    total_monitoring_messages INTEGER DEFAULT 0,
    
    -- Summary counters
    total_sessions INTEGER DEFAULT 0,
    total_errors INTEGER DEFAULT 0,
    
    -- Last activity timestamps
    last_prompt_at TIMESTAMP,
    last_recommendation_at TIMESTAMP,
    last_monitoring_at TIMESTAMP,
    
    -- Timestamps
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Create indexes
CREATE INDEX IF NOT EXISTS idx_org_statistics_updated_at ON org_statistics(updated_at);

-- ============================================================================
-- STEP 3: Migrate data from old tables to new tables
-- ============================================================================

-- Migrate from orchestrator_instances (primary source)
INSERT INTO organizations_new (
    org_id,
    org_name,
    orchestrator_id,
    status,
    last_seen,
    connected_at,
    keepalive_enabled,
    location,
    features,
    admin_email,
    support_email,
    website,
    created_at,
    updated_at
)
SELECT 
    orchestrator_id as org_id,  -- Use orchestrator_id as org_id
    organization_name as org_name,
    orchestrator_id,
    status,
    last_seen,
    created_at as connected_at,  -- Use created_at as initial connected_at
    true as keepalive_enabled,  -- Default to true
    location,
    features,
    admin_email,
    support_email,
    website,
    created_at,
    updated_at
FROM orchestrator_instances
ON CONFLICT (org_id) DO NOTHING;

-- Initialize statistics for all organizations
INSERT INTO org_statistics (org_id)
SELECT org_id FROM organizations_new
ON CONFLICT (org_id) DO NOTHING;

-- Migrate message counts from orchestrator_messages (if table exists)
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'orchestrator_messages') THEN
        -- Count recommendations per orchestrator
        UPDATE org_statistics
        SET total_recommendations = subquery.count,
            last_recommendation_at = subquery.last_at
        FROM (
            SELECT 
                orchestrator_id as org_id,
                COUNT(*) as count,
                MAX(created_at) as last_at
            FROM orchestrator_messages
            WHERE message_type = 'recommendation'
            GROUP BY orchestrator_id
        ) AS subquery
        WHERE org_statistics.org_id = subquery.org_id;
        
        -- Count monitoring messages per orchestrator
        UPDATE org_statistics
        SET total_monitoring_messages = subquery.count,
            last_monitoring_at = subquery.last_at
        FROM (
            SELECT 
                orchestrator_id as org_id,
                COUNT(*) as count,
                MAX(created_at) as last_at
            FROM orchestrator_messages
            WHERE message_type = 'monitoring'
            GROUP BY orchestrator_id
        ) AS subquery
        WHERE org_statistics.org_id = subquery.org_id;
    END IF;
END $$;

-- ============================================================================
-- STEP 4: Drop old tables and rename new table
-- ============================================================================

-- Drop old tables (backup first if needed!)
DROP TABLE IF EXISTS orchestrator_messages CASCADE;
DROP TABLE IF EXISTS orchestrator_instances CASCADE;
DROP TABLE IF EXISTS organizations CASCADE;

-- Rename new table to final name
ALTER TABLE organizations_new RENAME TO organizations;

-- ============================================================================
-- STEP 5: Create helper function for updating statistics
-- ============================================================================

-- Function to increment prompt counter by domain
CREATE OR REPLACE FUNCTION increment_prompt_counter(
    p_org_id VARCHAR(255),
    p_domain VARCHAR(255),
    p_count INTEGER DEFAULT 1
)
RETURNS void AS $$
BEGIN
    INSERT INTO org_statistics (org_id, total_prompts, prompts_by_domain, last_prompt_at, updated_at)
    VALUES (
        p_org_id,
        p_count,
        jsonb_build_object(p_domain, p_count),
        NOW(),
        NOW()
    )
    ON CONFLICT (org_id) DO UPDATE SET
        total_prompts = org_statistics.total_prompts + p_count,
        prompts_by_domain = jsonb_set(
            COALESCE(org_statistics.prompts_by_domain, '{}'::jsonb),
            ARRAY[p_domain],
            (COALESCE((org_statistics.prompts_by_domain->>p_domain)::int, 0) + p_count)::text::jsonb
        ),
        last_prompt_at = NOW(),
        updated_at = NOW();
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- STEP 6: Verify migration
-- ============================================================================

-- Check row counts
DO $$
DECLARE
    org_count INTEGER;
    stats_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO org_count FROM organizations;
    SELECT COUNT(*) INTO stats_count FROM org_statistics;
    
    RAISE NOTICE 'Migration complete:';
    RAISE NOTICE '  - Organizations: %', org_count;
    RAISE NOTICE '  - Statistics: %', stats_count;
END $$;

-- ============================================================================
-- ROLLBACK SCRIPT (if needed)
-- ============================================================================

-- To rollback this migration, you would need to:
-- 1. Restore from backup
-- 2. Or recreate old tables from organizations/org_statistics

-- Example rollback (commented out):
/*
CREATE TABLE orchestrator_instances AS 
SELECT 
    orchestrator_id,
    org_name as organization_name,
    status,
    last_seen,
    location,
    features,
    admin_email,
    support_email,
    website,
    created_at,
    updated_at
FROM organizations;

CREATE TABLE orchestrator_messages (
    id VARCHAR(255) PRIMARY KEY,
    orchestrator_id VARCHAR(255),
    message_type VARCHAR(50),
    content TEXT,
    message_metadata JSONB,
    status VARCHAR(50),
    created_at TIMESTAMP,
    updated_at TIMESTAMP
);
*/

