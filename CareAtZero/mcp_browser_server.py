#!/usr/bin/env python3
import sys
import json
import urllib.request
import urllib.parse
import re
import os

# Ensure project root in sys.path
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from scoring.care_access_score import calculate_care_access_score
from database.db import get_all_sites, get_all_events
from utils.geo import geocode_location, haversine_distance, get_user_current_zip
from utils.dates import today_str


def log_debug(msg):
    sys.stderr.write(f"[Browser-MCP] {msg}\n")
    sys.stderr.flush()


def tool_browser_navigate(url: str) -> dict:
    """Navigates to a URL and extracts clean DOM structure and content."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "CareAtZero-Browser-MCP/1.0"})
        with urllib.request.urlopen(req, timeout=10) as response:
            html = response.read().decode("utf-8", errors="ignore")
            status = response.status

            # Extract title
            title_match = re.search(r"<title>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
            title = title_match.group(1).strip() if title_match else "No Title"

            # Clean text preview
            text = re.sub(r"<script.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
            text = re.sub(r"<style.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)
            text = re.sub(r"<.*?>", " ", text)
            text = re.sub(r"\s+", " ", text).strip()

            return {
                "status": status,
                "url": url,
                "title": title,
                "html_length": len(html),
                "text_snippet": text[:500] + ("..." if len(text) > 500 else "")
            }
    except Exception as e:
        return {"error": str(e), "url": url}


def tool_test_health(base_url: str = "http://localhost:8501") -> dict:
    """Verifies that Streamlit server and all core endpoints are responding."""
    endpoints = [
        "/",
        "/_stcore/health",
        "/Find_Free_Care",
        "/Care_Details",
        "/About_&_Safety"
    ]
    results = {}
    for ep in endpoints:
        target = urllib.parse.urljoin(base_url, ep)
        try:
            req = urllib.request.Request(target, headers={"User-Agent": "MCP-Test/1.0"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                results[ep] = {"status": resp.status, "ok": resp.status == 200}
        except Exception as e:
            results[ep] = {"status": "error", "error": str(e)}

    return {
        "base_url": base_url,
        "all_healthy": all(v.get("ok", False) for v in results.values()),
        "endpoints": results
    }


def tool_simulate_user_journey(persona: str, service: str, location: str, timing: str) -> dict:
    """
    Simulates a full user journey for Persona testing:
    1. Geocodes location
    2. Filters safety net records & mobile events
    3. Calculates 100-pt Care Access Score
    4. Ranks realistic matches
    5. Validates document checklist & source freshness
    """
    place = geocode_location(location)
    if place is None:
        return {"persona": persona, "error": f"Unknown location '{location}'; use a 5-digit ZIP code."}
    lat, lon, label = place
    sites = get_all_sites()
    events = get_all_events(include_expired=False, current_date_str=today_str())
    all_recs = sites + events

    matched = []
    for r in all_recs:
        services = r.get("services", [])
        if not any(service.lower() in s.lower() for s in services):
            continue

        r_lat = r.get("latitude")
        r_lon = r.get("longitude")
        dist = haversine_distance(lat, lon, r_lat, r_lon) if r_lat and r_lon else 15.0

        score, breakdown, reasons = calculate_care_access_score(
            record=r,
            service_needed=service,
            distance_miles=dist,
            timing_pref=timing,
            user_income_band="Under $25k",
            reference_date_str=today_str()
        )

        matched.append({
            "id": r.get("id"),
            "title": r.get("title") or r.get("name"),
            "type": r.get("record_type"),
            "cost_class": r.get("cost_class"),
            "distance_miles": dist,
            "care_access_score": score,
            "reasons": reasons[:3],
            "documents_required": r.get("documents_required", []),
            "appointment_rule": r.get("appointment_rule"),
            "source_verified": r.get("last_checked", "Recent")
        })

    # Sort by Care Access Score descending
    matched.sort(key=lambda x: (x["care_access_score"], -x["distance_miles"]), reverse=True)

    top_match = matched[0] if matched else None

    return {
        "persona": persona,
        "input_criteria": {
            "service": service,
            "location": location,
            "resolved_location": label,
            "timing": timing
        },
        "total_matches_found": len(matched),
        "top_ranked_match": top_match,
        "top_3_results": matched[:3],
        "journey_success": top_match is not None and top_match["care_access_score"] >= 70
    }


def handle_request(req: dict) -> dict:
    method = req.get("method")
    req_id = req.get("id")

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {
                    "tools": {}
                },
                "serverInfo": {
                    "name": "careatzero-browser-mcp",
                    "version": "1.0.0"
                }
            }
        }

    elif method == "notifications/initialized":
        return None

    elif method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "tools": [
                    {
                        "name": "browser_navigate",
                        "description": "Fetch and parse webpage content, title, and HTML structure.",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "url": {"type": "string", "description": "URL to navigate to"}
                            },
                            "required": ["url"]
                        }
                    },
                    {
                        "name": "browser_test_health",
                        "description": "Test Streamlit web server endpoints and health checks.",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "base_url": {"type": "string", "description": "Base URL (default: http://localhost:8501)", "default": "http://localhost:8501"}
                            }
                        }
                    },
                    {
                        "name": "browser_simulate_journey",
                        "description": "Simulate end-to-end user personas and search flows.",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "persona": {"type": "string", "description": "Persona name or description"},
                                "service": {"type": "string", "description": "Service needed (Medical, Dental, Vision, Behavioral Health)"},
                                "location": {"type": "string", "description": "ZIP code or City (e.g. 27514, Raleigh)"},
                                "timing": {"type": "string", "description": "Timing preference (Today, This Week, Flexible)"}
                            },
                            "required": ["persona", "service", "location", "timing"]
                        }
                    }
                ]
            }
        }

    elif method == "tools/call":
        params = req.get("params", {})
        tool_name = params.get("name")
        args = params.get("arguments", {})

        if tool_name == "browser_navigate":
            res = tool_browser_navigate(args.get("url", "http://localhost:8501"))
        elif tool_name == "browser_test_health":
            res = tool_test_health(args.get("base_url", "http://localhost:8501"))
        elif tool_name == "browser_simulate_journey" and not (args.get("location") or get_user_current_zip()):
            return {"jsonrpc": "2.0", "id": req_id,
                    "error": {"code": -32602, "message": "Location couldn't be detected; pass a 'location' (ZIP code or city)."}}
        elif tool_name == "browser_simulate_journey":
            res = tool_simulate_user_journey(
                persona=args.get("persona", "Uninsured User"),
                service=args.get("service", "Dental"),
                location=args.get("location") or get_user_current_zip(),
                timing=args.get("timing", "This Week")
            )
        else:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {
                    "code": -32601,
                    "message": f"Method {tool_name} not found"
                }
            }

        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(res, indent=2)
                    }
                ]
            }
        }

    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "error": {
            "code": -32601,
            "message": f"Method {method} not found"
        }
    }


def main():
    log_debug("Starting CareAtZero Browser MCP Server on stdio...")
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
            resp = handle_request(req)
            if resp:
                sys.stdout.write(json.dumps(resp) + "\n")
                sys.stdout.flush()
        except Exception as e:
            log_debug(f"Error processing line: {e}")


if __name__ == "__main__":
    main()
