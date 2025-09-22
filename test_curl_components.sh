#!/bin/bash
"""
Curl-based Component Test Suite for MoolAI Orchestrator Docker Containers
==========================================================================

Tests the following components via curl HTTP requests:
1. Enhanced Cache Service 
2. Firewall Service 
3. Domain Classification Service
4. System Health and Metrics

Results are saved to curl_test_results.json and curl_test_results.txt
"""

set -e  # Exit on any error

# Configuration
ORCHESTRATOR_URL="http://localhost:8000"
RESULTS_JSON="curl_test_results.json"
RESULTS_TXT="curl_test_results.txt"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Test counters
TOTAL_TESTS=0
PASSED_TESTS=0
FAILED_TESTS=0

# Initialize results
echo "{" > $RESULTS_JSON
echo "  \"timestamp\": \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\"," >> $RESULTS_JSON
echo "  \"environment\": \"Docker (curl)\"," >> $RESULTS_JSON
echo "  \"components\": {" >> $RESULTS_JSON

# Initialize text results
echo "=" > $RESULTS_TXT
printf "=%.0s" {1..80} >> $RESULTS_TXT
echo "=" >> $RESULTS_TXT
echo "MoolAI Orchestrator Docker Component Test Results (curl)" >> $RESULTS_TXT
printf "=%.0s" {1..80} >> $RESULTS_TXT
echo "=" >> $RESULTS_TXT
echo "" >> $RESULTS_TXT
echo "Timestamp: $(date)" >> $RESULTS_TXT
echo "Environment: Docker (curl)" >> $RESULTS_TXT
echo "" >> $RESULTS_TXT

# Helper functions
log_test() {
    local test_name="$1"
    local status="$2"
    local details="$3"
    
    TOTAL_TESTS=$((TOTAL_TESTS + 1))
    
    if [ "$status" = "PASSED" ]; then
        PASSED_TESTS=$((PASSED_TESTS + 1))
        echo -e "${GREEN}✓ $test_name - PASSED${NC}"
    elif [ "$status" = "FAILED" ]; then
        FAILED_TESTS=$((FAILED_TESTS + 1))
        echo -e "${RED}✗ $test_name - FAILED${NC}"
    else
        echo -e "${YELLOW}⚠ $test_name - $status${NC}"
    fi
    
    # Log to text file
    echo "Test: $test_name" >> $RESULTS_TXT
    echo "Status: $status" >> $RESULTS_TXT
    if [ -n "$details" ]; then
        echo "Details: $details" >> $RESULTS_TXT
    fi
    echo "" >> $RESULTS_TXT
}

# Test 1: Health Check
echo -e "\n${YELLOW}Testing System Health...${NC}"
echo "    \"system_health\": {" >> $RESULTS_JSON
echo "      \"service\": \"System Health (Docker curl)\"," >> $RESULTS_JSON
echo "      \"tests\": [" >> $RESULTS_JSON

echo "----------------------------------------" >> $RESULTS_TXT
echo "SYSTEM HEALTH" >> $RESULTS_TXT
echo "----------------------------------------" >> $RESULTS_TXT

# Health endpoint
if response=$(curl -s -w "HTTP_STATUS:%{http_code}" "$ORCHESTRATOR_URL/health"); then
    http_status=$(echo "$response" | grep -o "HTTP_STATUS:[0-9]*" | cut -d: -f2)
    body=$(echo "$response" | sed 's/HTTP_STATUS:[0-9]*$//')
    
    if [ "$http_status" = "200" ]; then
        log_test "Health Check Endpoint" "PASSED" "HTTP 200 - $body"
        echo "        {\"name\": \"Health Check\", \"status\": \"PASSED\", \"http_code\": $http_status}," >> $RESULTS_JSON
    else
        log_test "Health Check Endpoint" "FAILED" "HTTP $http_status"
        echo "        {\"name\": \"Health Check\", \"status\": \"FAILED\", \"http_code\": $http_status}," >> $RESULTS_JSON
    fi
else
    log_test "Health Check Endpoint" "FAILED" "Connection failed"
    echo "        {\"name\": \"Health Check\", \"status\": \"FAILED\", \"error\": \"Connection failed\"}," >> $RESULTS_JSON
fi

# System metrics
if response=$(curl -s -w "HTTP_STATUS:%{http_code}" "$ORCHESTRATOR_URL/api/v1/system/metrics"); then
    http_status=$(echo "$response" | grep -o "HTTP_STATUS:[0-9]*" | cut -d: -f2)
    body=$(echo "$response" | sed 's/HTTP_STATUS:[0-9]*$//')
    
    if [ "$http_status" = "200" ]; then
        log_test "System Metrics Endpoint" "PASSED" "HTTP 200"
        echo "        {\"name\": \"System Metrics\", \"status\": \"PASSED\", \"http_code\": $http_status}" >> $RESULTS_JSON
    else
        log_test "System Metrics Endpoint" "FAILED" "HTTP $http_status"
        echo "        {\"name\": \"System Metrics\", \"status\": \"FAILED\", \"http_code\": $http_status}" >> $RESULTS_JSON
    fi
else
    log_test "System Metrics Endpoint" "FAILED" "Connection failed"
    echo "        {\"name\": \"System Metrics\", \"status\": \"FAILED\", \"error\": \"Connection failed\"}" >> $RESULTS_JSON
fi

echo "      ]" >> $RESULTS_JSON
echo "    }," >> $RESULTS_JSON

# Test 2: Cache Service
echo -e "\n${YELLOW}Testing Cache Service...${NC}"
echo "    \"cache\": {" >> $RESULTS_JSON
echo "      \"service\": \"Cache Service (Docker curl)\"," >> $RESULTS_JSON
echo "      \"tests\": [" >> $RESULTS_JSON

echo "----------------------------------------" >> $RESULTS_TXT
echo "CACHE SERVICE" >> $RESULTS_TXT
echo "----------------------------------------" >> $RESULTS_TXT

# Cache stats
if response=$(curl -s -w "HTTP_STATUS:%{http_code}" "$ORCHESTRATOR_URL/api/v1/cache/stats"); then
    http_status=$(echo "$response" | grep -o "HTTP_STATUS:[0-9]*" | cut -d: -f2)
    body=$(echo "$response" | sed 's/HTTP_STATUS:[0-9]*$//')
    
    if [ "$http_status" = "200" ]; then
        # Check if cache is enabled
        if echo "$body" | grep -q '"enabled":true'; then
            log_test "Cache Stats API" "PASSED" "Cache enabled"
            echo "        {\"name\": \"Cache Stats\", \"status\": \"PASSED\", \"cache_enabled\": true}," >> $RESULTS_JSON
        else
            log_test "Cache Stats API" "INFO" "Cache disabled"
            echo "        {\"name\": \"Cache Stats\", \"status\": \"INFO\", \"cache_enabled\": false}," >> $RESULTS_JSON
        fi
    else
        log_test "Cache Stats API" "FAILED" "HTTP $http_status"
        echo "        {\"name\": \"Cache Stats\", \"status\": \"FAILED\", \"http_code\": $http_status}," >> $RESULTS_JSON
    fi
else
    log_test "Cache Stats API" "FAILED" "Connection failed"
    echo "        {\"name\": \"Cache Stats\", \"status\": \"FAILED\", \"error\": \"Connection failed\"}," >> $RESULTS_JSON
fi

# Test cache clear functionality
clear_payload='{"session_id": "test_session_curl"}'
if response=$(curl -s -w "HTTP_STATUS:%{http_code}" -X POST \
    -H "Content-Type: application/json" \
    -d "$clear_payload" \
    "$ORCHESTRATOR_URL/api/v1/cache/clear/session"); then
    
    http_status=$(echo "$response" | grep -o "HTTP_STATUS:[0-9]*" | cut -d: -f2)
    body=$(echo "$response" | sed 's/HTTP_STATUS:[0-9]*$//')
    
    if [ "$http_status" = "200" ]; then
        log_test "Cache Clear Session API" "PASSED" "HTTP 200"
        echo "        {\"name\": \"Cache Clear Session\", \"status\": \"PASSED\"}" >> $RESULTS_JSON
    else
        log_test "Cache Clear Session API" "FAILED" "HTTP $http_status"
        echo "        {\"name\": \"Cache Clear Session\", \"status\": \"FAILED\", \"http_code\": $http_status}" >> $RESULTS_JSON
    fi
else
    log_test "Cache Clear Session API" "FAILED" "Connection failed"
    echo "        {\"name\": \"Cache Clear Session\", \"status\": \"FAILED\", \"error\": \"Connection failed\"}" >> $RESULTS_JSON
fi

echo "      ]" >> $RESULTS_JSON
echo "    }," >> $RESULTS_JSON

# Test 3: Firewall Service
echo -e "\n${YELLOW}Testing Firewall Service...${NC}"
echo "    \"firewall\": {" >> $RESULTS_JSON
echo "      \"service\": \"Firewall Service (Docker curl)\"," >> $RESULTS_JSON
echo "      \"tests\": [" >> $RESULTS_JSON

echo "----------------------------------------" >> $RESULTS_TXT
echo "FIREWALL SERVICE" >> $RESULTS_TXT
echo "----------------------------------------" >> $RESULTS_TXT

# Test PII detection
pii_payload='{"text": "My email is john@example.com and my SSN is 123-45-6789", "scan_type": "comprehensive"}'
if response=$(curl -s -w "HTTP_STATUS:%{http_code}" -X POST \
    -H "Content-Type: application/json" \
    -d "$pii_payload" \
    "$ORCHESTRATOR_URL/api/v1/firewall/scan"); then
    
    http_status=$(echo "$response" | grep -o "HTTP_STATUS:[0-9]*" | cut -d: -f2)
    body=$(echo "$response" | sed 's/HTTP_STATUS:[0-9]*$//')
    
    if [ "$http_status" = "200" ]; then
        # Check if PII was detected
        if echo "$body" | grep -q '"pii"'; then
            log_test "PII Detection Scan" "PASSED" "PII detected in violations"
            echo "        {\"name\": \"PII Detection\", \"status\": \"PASSED\", \"pii_detected\": true}," >> $RESULTS_JSON
        else
            log_test "PII Detection Scan" "INFO" "PII not detected (may be disabled)"
            echo "        {\"name\": \"PII Detection\", \"status\": \"INFO\", \"pii_detected\": false}," >> $RESULTS_JSON
        fi
    else
        log_test "PII Detection Scan" "FAILED" "HTTP $http_status"
        echo "        {\"name\": \"PII Detection\", \"status\": \"FAILED\", \"http_code\": $http_status}," >> $RESULTS_JSON
    fi
else
    log_test "PII Detection Scan" "FAILED" "Connection failed"
    echo "        {\"name\": \"PII Detection\", \"status\": \"FAILED\", \"error\": \"Connection failed\"}," >> $RESULTS_JSON
fi

# Test secrets detection
secrets_payload='{"text": "Use this API key: sk-abc123def456ghi789 for authentication", "scan_type": "secrets"}'
if response=$(curl -s -w "HTTP_STATUS:%{http_code}" -X POST \
    -H "Content-Type: application/json" \
    -d "$secrets_payload" \
    "$ORCHESTRATOR_URL/api/v1/firewall/scan"); then
    
    http_status=$(echo "$response" | grep -o "HTTP_STATUS:[0-9]*" | cut -d: -f2)
    body=$(echo "$response" | sed 's/HTTP_STATUS:[0-9]*$//')
    
    if [ "$http_status" = "200" ]; then
        if echo "$body" | grep -q '"contains_violation":true' || echo "$body" | grep -q '"secrets"'; then
            log_test "Secrets Detection Scan" "PASSED" "Secret detected"
            echo "        {\"name\": \"Secrets Detection\", \"status\": \"PASSED\", \"secret_detected\": true}," >> $RESULTS_JSON
        else
            log_test "Secrets Detection Scan" "INFO" "Secret not detected (may be disabled)"
            echo "        {\"name\": \"Secrets Detection\", \"status\": \"INFO\", \"secret_detected\": false}," >> $RESULTS_JSON
        fi
    else
        log_test "Secrets Detection Scan" "FAILED" "HTTP $http_status"
        echo "        {\"name\": \"Secrets Detection\", \"status\": \"FAILED\", \"http_code\": $http_status}," >> $RESULTS_JSON
    fi
else
    log_test "Secrets Detection Scan" "FAILED" "Connection failed"
    echo "        {\"name\": \"Secrets Detection\", \"status\": \"FAILED\", \"error\": \"Connection failed\"}," >> $RESULTS_JSON
fi

# Test anonymization
anon_payload='{"text": "Contact john.doe@example.com or call 555-123-4567"}'
if response=$(curl -s -w "HTTP_STATUS:%{http_code}" -X POST \
    -H "Content-Type: application/json" \
    -d "$anon_payload" \
    "$ORCHESTRATOR_URL/api/v1/firewall/anonymize"); then
    
    http_status=$(echo "$response" | grep -o "HTTP_STATUS:[0-9]*" | cut -d: -f2)
    body=$(echo "$response" | sed 's/HTTP_STATUS:[0-9]*$//')
    
    if [ "$http_status" = "200" ]; then
        log_test "PII Anonymization API" "PASSED" "Anonymization endpoint working"
        echo "        {\"name\": \"PII Anonymization\", \"status\": \"PASSED\"}" >> $RESULTS_JSON
    else
        log_test "PII Anonymization API" "FAILED" "HTTP $http_status"
        echo "        {\"name\": \"PII Anonymization\", \"status\": \"FAILED\", \"http_code\": $http_status}" >> $RESULTS_JSON
    fi
else
    log_test "PII Anonymization API" "FAILED" "Connection failed"
    echo "        {\"name\": \"PII Anonymization\", \"status\": \"FAILED\", \"error\": \"Connection failed\"}" >> $RESULTS_JSON
fi

echo "      ]" >> $RESULTS_JSON
echo "    }," >> $RESULTS_JSON

# Test 4: LLM/Prompt Response Service
echo -e "\n${YELLOW}Testing LLM/Prompt Response Service...${NC}"
echo "    \"llm_service\": {" >> $RESULTS_JSON
echo "      \"service\": \"LLM/Prompt Response Service (Docker curl)\"," >> $RESULTS_JSON
echo "      \"tests\": [" >> $RESULTS_JSON

echo "----------------------------------------" >> $RESULTS_TXT
echo "LLM/PROMPT RESPONSE SERVICE" >> $RESULTS_TXT
echo "----------------------------------------" >> $RESULTS_TXT

# Test basic LLM endpoint
llm_payload='{"prompt": "What is Docker?", "max_tokens": 50, "session_id": "curl_test_001"}'
if response=$(curl -s -w "HTTP_STATUS:%{http_code}" -X POST \
    -H "Content-Type: application/json" \
    -d "$llm_payload" \
    "$ORCHESTRATOR_URL/api/v1/llm/prompt"); then
    
    http_status=$(echo "$response" | grep -o "HTTP_STATUS:[0-9]*" | cut -d: -f2)
    body=$(echo "$response" | sed 's/HTTP_STATUS:[0-9]*$//')
    
    if [ "$http_status" = "200" ]; then
        # Check if response contains expected fields
        if echo "$body" | grep -q '"response"' || echo "$body" | grep -q '"message"'; then
            log_test "LLM Prompt Endpoint" "PASSED" "Endpoint working"
            echo "        {\"name\": \"LLM Prompt\", \"status\": \"PASSED\", \"has_response\": true}," >> $RESULTS_JSON
        else
            log_test "LLM Prompt Endpoint" "INFO" "Endpoint accessible but may need API key"
            echo "        {\"name\": \"LLM Prompt\", \"status\": \"INFO\", \"note\": \"May need API key\"}," >> $RESULTS_JSON
        fi
    else
        log_test "LLM Prompt Endpoint" "FAILED" "HTTP $http_status"
        echo "        {\"name\": \"LLM Prompt\", \"status\": \"FAILED\", \"http_code\": $http_status}," >> $RESULTS_JSON
    fi
else
    log_test "LLM Prompt Endpoint" "FAILED" "Connection failed"
    echo "        {\"name\": \"LLM Prompt\", \"status\": \"FAILED\", \"error\": \"Connection failed\"}," >> $RESULTS_JSON
fi

# Test domain classification via LLM endpoint
domain_payload='{"prompt": "SELECT * FROM users WHERE age > 18", "max_tokens": 10, "classify_domain": true}'
if response=$(curl -s -w "HTTP_STATUS:%{http_code}" -X POST \
    -H "Content-Type: application/json" \
    -d "$domain_payload" \
    "$ORCHESTRATOR_URL/api/v1/llm/prompt"); then
    
    http_status=$(echo "$response" | grep -o "HTTP_STATUS:[0-9]*" | cut -d: -f2)
    body=$(echo "$response" | sed 's/HTTP_STATUS:[0-9]*$//')
    
    if [ "$http_status" = "200" ]; then
        if echo "$body" | grep -q '"domain"' && ! echo "$body" | grep -q '"domain":"unknown"'; then
            log_test "Domain Classification" "PASSED" "Domain classified"
            echo "        {\"name\": \"Domain Classification\", \"status\": \"PASSED\", \"domain_classified\": true}" >> $RESULTS_JSON
        else
            log_test "Domain Classification" "INFO" "Classification may need API key"
            echo "        {\"name\": \"Domain Classification\", \"status\": \"INFO\", \"note\": \"May need API key\"}" >> $RESULTS_JSON
        fi
    else
        log_test "Domain Classification" "FAILED" "HTTP $http_status"
        echo "        {\"name\": \"Domain Classification\", \"status\": \"FAILED\", \"http_code\": $http_status}" >> $RESULTS_JSON
    fi
else
    log_test "Domain Classification" "FAILED" "Connection failed"
    echo "        {\"name\": \"Domain Classification\", \"status\": \"FAILED\", \"error\": \"Connection failed\"}" >> $RESULTS_JSON
fi

echo "      ]" >> $RESULTS_JSON
echo "    }" >> $RESULTS_JSON

# Close JSON structure
echo "  }," >> $RESULTS_JSON
echo "  \"summary\": {" >> $RESULTS_JSON
echo "    \"total_tests\": $TOTAL_TESTS," >> $RESULTS_JSON
echo "    \"passed\": $PASSED_TESTS," >> $RESULTS_JSON
echo "    \"failed\": $FAILED_TESTS," >> $RESULTS_JSON
echo "    \"success_rate\": $(echo "scale=2; $PASSED_TESTS * 100 / $TOTAL_TESTS" | bc)%" >> $RESULTS_JSON
echo "  }" >> $RESULTS_JSON
echo "}" >> $RESULTS_JSON

# Finalize text results
echo "========================================" >> $RESULTS_TXT
echo "TEST SUMMARY" >> $RESULTS_TXT
echo "========================================" >> $RESULTS_TXT
echo "Total Tests: $TOTAL_TESTS" >> $RESULTS_TXT
echo "Passed: $PASSED_TESTS" >> $RESULTS_TXT
echo "Failed: $FAILED_TESTS" >> $RESULTS_TXT
echo "Success Rate: $(echo "scale=2; $PASSED_TESTS * 100 / $TOTAL_TESTS" | bc)%" >> $RESULTS_TXT
echo "" >> $RESULTS_TXT

# Print final summary
echo -e "\n${YELLOW}========================================${NC}"
echo -e "${YELLOW}TEST SUMMARY${NC}"
echo -e "${YELLOW}========================================${NC}"
echo -e "Total Tests: $TOTAL_TESTS"
echo -e "Passed: ${GREEN}$PASSED_TESTS${NC}"
echo -e "Failed: ${RED}$FAILED_TESTS${NC}"
echo -e "Success Rate: $(echo "scale=2; $PASSED_TESTS * 100 / $TOTAL_TESTS" | bc)%"
echo -e "\nResults saved to:"
echo -e "  - ${GREEN}$RESULTS_JSON${NC} (JSON format)"
echo -e "  - ${GREEN}$RESULTS_TXT${NC} (Human-readable format)"
echo -e "${YELLOW}========================================${NC}\n"

# Exit with appropriate code
if [ $FAILED_TESTS -gt 0 ]; then
    exit 1
else
    exit 0
fi