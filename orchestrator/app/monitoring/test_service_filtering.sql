-- Test SQL queries to verify service filtering for dashboard vs internal analytics
-- Run these directly against PostgreSQL to verify the filtering logic works correctly
-- UPDATED FOR NEW PARENT-CHILD SPAN HIERARCHY

-- ==============================================================================
-- TEST 1: Count all API calls by service name (NEW HIERARCHY-AWARE)
-- This shows the breakdown of which services are making calls
-- ==============================================================================
WITH span_with_service AS (
    SELECT s.*,
        COALESCE(
            -- Check current span for service attribution (for parent spans)
            s.attributes->'moolai'->>'service_name',
            -- Check parent span for service attribution (for child spans)
            (SELECT p.attributes->'moolai'->>'service_name' 
             FROM phoenix.spans p 
             WHERE p.span_id = s.parent_id AND p.name = 'moolai.request.process'),
            -- Legacy service attribution fallbacks
            s.attributes->'openai'->>'service_name',
            CASE 
                WHEN s.attributes->'openai'->>'operation_name' = 'generate_llm_response' THEN 'main_response'
                ELSE 'unknown'
            END
        ) as service_name
    FROM phoenix.spans s
    WHERE s.start_time >= NOW() - INTERVAL '24 hours'
        AND (s.attributes ? 'gen_ai' OR s.attributes ? 'openai')
)
SELECT 
    service_name,
    COUNT(*) as call_count,
    ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (), 2) as percentage
FROM span_with_service
GROUP BY service_name
ORDER BY call_count DESC;

-- ==============================================================================
-- TEST 2: Verify dashboard filtering (main_response only)
-- This simulates what the dashboard will show
-- ==============================================================================
SELECT 
    'Dashboard View (User-Facing Only)' as view_type,
    COUNT(*) as total_calls,
    SUM(COALESCE(
        (s.attributes->'moolai'->>'cost')::FLOAT,
        (s.attributes->'moolai'->'llm'->>'cost')::FLOAT,
        0
    )) as total_cost,
    SUM(COALESCE(
        (s.attributes->'gen_ai'->'usage'->>'prompt_tokens')::INTEGER + 
        (s.attributes->'gen_ai'->'usage'->>'completion_tokens')::INTEGER,
        0
    )) as total_tokens
FROM phoenix.spans s
WHERE s.start_time >= NOW() - INTERVAL '24 hours'
    AND (s.attributes ? 'gen_ai' OR s.attributes ? 'openai')
    AND (
        -- Dashboard filter: NEW HIERARCHY STRUCTURE
        (s.name = 'moolai.request.process' AND s.attributes->'moolai'->>'service_name' = 'main_response') OR
        -- Legacy compatibility filters
        (s.name = 'moolai.user_interaction') OR
        (s.name = 'openai.chat' AND s.attributes->'moolai'->>'service_name' = 'main_response')
    );

-- ==============================================================================
-- TEST 3: Verify internal view (ALL services)
-- This simulates what the controller VM will see
-- ==============================================================================
SELECT 
    'Internal View (All Services)' as view_type,
    COUNT(*) as total_calls,
    SUM(COALESCE(
        (s.attributes->'moolai'->>'cost')::FLOAT,
        (s.attributes->'moolai'->'llm'->>'cost')::FLOAT,
        0
    )) as total_cost,
    SUM(COALESCE(
        (s.attributes->'gen_ai'->'usage'->>'prompt_tokens')::INTEGER + 
        (s.attributes->'gen_ai'->'usage'->>'completion_tokens')::INTEGER,
        0
    )) as total_tokens
FROM phoenix.spans s
WHERE s.start_time >= NOW() - INTERVAL '24 hours'
    AND (s.attributes ? 'gen_ai' OR s.attributes ? 'openai');
    -- No service filter - includes everything

-- ==============================================================================
-- TEST 4: Compare dashboard vs internal metrics
-- This shows the difference between what users see vs actual system load
-- ==============================================================================
WITH metrics AS (
    SELECT 
        COUNT(*) FILTER (WHERE 
            (s.attributes->'openai'->>'service_name' = 'main_response') OR
            (s.attributes->'moolai'->>'service_name' = 'main_response') OR
            (s.attributes->'openai'->>'operation_name' = 'generate_llm_response')
        ) as user_facing_calls,
        COUNT(*) FILTER (WHERE 
            (s.attributes->'openai'->>'service_name' LIKE '%_evaluation') OR
            (s.attributes->'moolai'->>'service_name' LIKE '%_evaluation')
        ) as evaluation_calls,
        COUNT(*) as total_calls
    FROM phoenix.spans s
    WHERE s.start_time >= NOW() - INTERVAL '24 hours'
        AND (s.attributes ? 'gen_ai' OR s.attributes ? 'openai')
)
SELECT 
    user_facing_calls as "Dashboard Shows",
    evaluation_calls as "Evaluation Services",
    total_calls as "Actual Total",
    CASE 
        WHEN user_facing_calls > 0 
        THEN ROUND(evaluation_calls::NUMERIC / user_facing_calls, 2)
        ELSE 0 
    END as "Eval/User Ratio",
    CASE 
        WHEN user_facing_calls > 0 
        THEN ROUND((total_calls - user_facing_calls)::NUMERIC * 100 / total_calls, 2)
        ELSE 0 
    END as "Hidden from Dashboard %"
FROM metrics;

-- ==============================================================================
-- TEST 5: Recent service activity (last 10 API calls with service names)
-- This helps verify that service attribution is working correctly
-- ==============================================================================
SELECT 
    s.start_time,
    COALESCE(
        s.attributes->'openai'->>'service_name',
        s.attributes->'moolai'->>'service_name',
        'not_set'
    ) as service_name,
    s.attributes->'gen_ai'->'request'->>'model' as model,
    COALESCE(
        (s.attributes->'moolai'->>'cost')::FLOAT,
        0
    ) as cost,
    EXTRACT(EPOCH FROM (s.end_time - s.start_time)) * 1000 as duration_ms
FROM phoenix.spans s
WHERE s.start_time >= NOW() - INTERVAL '24 hours'
    AND (s.attributes ? 'gen_ai' OR s.attributes ? 'openai')
ORDER BY s.start_time DESC
LIMIT 10;

-- ==============================================================================
-- TEST 6: Verify cost calculation filtering
-- Compare costs between dashboard view and internal view
-- ==============================================================================
WITH cost_comparison AS (
    SELECT 
        SUM(CASE 
            WHEN (s.attributes->'openai'->>'service_name' = 'main_response') OR
                 (s.attributes->'moolai'->>'service_name' = 'main_response') OR
                 (s.attributes->'openai'->>'operation_name' = 'generate_llm_response')
            THEN COALESCE((s.attributes->'moolai'->>'cost')::FLOAT, 0)
            ELSE 0
        END) as dashboard_cost,
        SUM(COALESCE((s.attributes->'moolai'->>'cost')::FLOAT, 0)) as total_cost
    FROM phoenix.spans s
    WHERE s.start_time >= NOW() - INTERVAL '24 hours'
        AND (s.attributes ? 'gen_ai' OR s.attributes ? 'openai')
)
SELECT 
    ROUND(dashboard_cost::NUMERIC, 4) as "User-Visible Cost ($)",
    ROUND(total_cost::NUMERIC, 4) as "Actual Total Cost ($)",
    ROUND((total_cost - dashboard_cost)::NUMERIC, 4) as "Hidden Evaluation Cost ($)",
    CASE 
        WHEN dashboard_cost > 0 
        THEN ROUND((total_cost / dashboard_cost)::NUMERIC, 2)
        ELSE 0 
    END as "Cost Multiplier"
FROM cost_comparison;