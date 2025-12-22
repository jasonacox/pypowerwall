#!/usr/bin/env python3
"""
Performance test script for pypowerwall proxy routes.
Tests response times for various endpoints to identify slow routes.
"""

import time
import requests
import json
import statistics
from typing import Dict, List, Tuple, Optional
import argparse
import sys

# Disable SSL warnings for self-signed certificates
try:
    from urllib3.exceptions import InsecureRequestWarning
    requests.packages.urllib3.disable_warnings(InsecureRequestWarning)
except ImportError:
    # Older urllib3 versions
    try:
        from urllib3.packages.urllib3.exceptions import InsecureRequestWarning
        requests.packages.urllib3.disable_warnings(InsecureRequestWarning)
    except ImportError:
        # If neither works, just skip the warning suppression
        pass

# Test routes with their usage counts from past 8 hours
TEST_ROUTES = {
    "/version": 461,
    "/api/sitemaster": 7990,
    "/api/powerwalls": 7992,
    "/api/troubleshooting/problems": 4049,
    "/api/auth/toggle/supported": 2071,
    "/api/system_status/grid_status": 7992,
    "/api/system_status/soe": 7992,
    "/api/meters/aggregates": 7992,
    "/csv/v2": 1923,
    "/freq": 3946,
    "/api/site_info": 651,
    "/csv": 2614,
    "/stats": 324,
    "/vitals": 3946,
    "/alerts/pw": 3881,
    "/fans/pw": 3880,
    "/soe": 3880,
    "/strings": 3945,
    "/temps/pw": 3880,
    "/pod": 3880,
    "/aggregates": 3880,
    # Additional minor routes found in production usage
    "/csv/v2?headers": 1,
    "/api/status": 2,
    "/api/customer/registration": 1,
    "/api/site_info/site_name": 1,
    "/api/networks": 1,
    "/api/system_status/grid_faults": 1
}


class RoutePerformanceTester:
    def __init__(self, host: str = "localhost", port: int = 8675, timeout: int = 10):
        self.host = host
        self.port = port
        self.base_url = f"http://{host}:{port}"
        self.timeout = timeout
        self.session = requests.Session()
        
    def test_route(self, route: str, num_requests: int = 5) -> Dict:
        """Test a single route and return timing statistics."""
        print(f"Testing {route}...", end=" ", flush=True)
        
        times = []
        errors = []
        response_sizes = []
        status_codes = []
        
        for i in range(num_requests):
            try:
                start_time = time.time()
                response = self.session.get(
                    f"{self.base_url}{route}",
                    timeout=self.timeout,
                    verify=False
                )
                end_time = time.time()
                
                response_time = (end_time - start_time) * 1000  # Convert to milliseconds
                times.append(response_time)
                status_codes.append(response.status_code)
                response_sizes.append(len(response.content))
                
            except requests.exceptions.Timeout:
                errors.append(f"Request {i+1}: Timeout")
            except requests.exceptions.ConnectionError:
                errors.append(f"Request {i+1}: Connection Error")
            except Exception as e:
                errors.append(f"Request {i+1}: {str(e)}")
        
        if not times:
            print("FAILED - All requests failed")
            return {
                "route": route,
                "status": "FAILED",
                "errors": errors,
                "times": [],
                "stats": {}
            }
        
        # Calculate statistics
        stats = {
            "min_ms": min(times),
            "max_ms": max(times),
            "avg_ms": statistics.mean(times),
            "median_ms": statistics.median(times),
            "std_dev_ms": statistics.stdev(times) if len(times) > 1 else 0,
            "success_rate": len(times) / num_requests * 100,
            "avg_response_size_bytes": statistics.mean(response_sizes) if response_sizes else 0,
            "status_codes": list(set(status_codes))
        }
        
        print(f"OK (avg: {stats['avg_ms']:.1f}ms)")
        
        return {
            "route": route,
            "status": "SUCCESS",
            "errors": errors,
            "times": times,
            "stats": stats,
            "usage_count": TEST_ROUTES.get(route, 0)
        }
    
    def run_all_tests(self, num_requests: int = 5, sort_by: str = "avg") -> List[Dict]:
        """Run performance tests on all routes."""
        print(f"Testing {len(TEST_ROUTES)} routes with {num_requests} requests each...")
        print(f"Target: {self.base_url}")
        print("-" * 60)
        
        results = []
        
        for route in TEST_ROUTES.keys():
            result = self.test_route(route, num_requests)
            results.append(result)
            time.sleep(0.1)  # Small delay between routes to avoid overwhelming server
        
        # Sort results
        if sort_by == "avg":
            results.sort(key=lambda x: x["stats"].get("avg_ms", float('inf')), reverse=True)
        elif sort_by == "usage":
            results.sort(key=lambda x: x["usage_count"], reverse=True)
        elif sort_by == "impact":
            # Sort by impact (avg_time * usage_count)
            results.sort(key=lambda x: x["stats"].get("avg_ms", 0) * x["usage_count"], reverse=True)
        
        return results
    
    def print_summary(self, results: List[Dict], show_errors: bool = False):
        """Print a formatted summary of test results."""
        print("\n" + "=" * 80)
        print("PERFORMANCE TEST SUMMARY")
        print("=" * 80)
        
        successful_results = [r for r in results if r["status"] == "SUCCESS"]
        failed_results = [r for r in results if r["status"] == "FAILED"]
        
        if failed_results:
            print(f"\n⚠️  {len(failed_results)} routes FAILED:")
            for result in failed_results:
                print(f"  - {result['route']}")
                if show_errors:
                    for error in result['errors']:
                        print(f"    {error}")
        
        if successful_results:
            print(f"\n✅ {len(successful_results)} routes tested successfully\n")
            
            # Header
            print(f"{'Route':<35} {'Avg (ms)':<10} {'Min (ms)':<10} {'Max (ms)':<10} {'Usage':<8} {'Impact':<10} {'Size (B)':<10}")
            print("-" * 100)
            
            for result in successful_results:
                stats = result["stats"]
                route = result["route"]
                usage = result["usage_count"]
                impact = stats["avg_ms"] * usage / 1000  # Impact score in seconds
                
                # Color coding for slow routes
                avg_ms = stats["avg_ms"]
                if avg_ms > 1000:
                    color = "🔴"  # Very slow
                elif avg_ms > 500:
                    color = "🟡"  # Slow
                else:
                    color = "🟢"  # Fast
                
                print(f"{color} {route:<33} {avg_ms:<9.1f} {stats['min_ms']:<9.1f} {stats['max_ms']:<9.1f} "
                      f"{usage:<7} {impact:<9.0f} {stats['avg_response_size_bytes']:<9.0f}")
        
        # Summary statistics
        if successful_results:
            all_avg_times = [r["stats"]["avg_ms"] for r in successful_results]
            all_usages = [r["usage_count"] for r in successful_results]
            
            print("\n" + "-" * 80)
            print("OVERALL STATISTICS:")
            print(f"  Fastest route: {min(all_avg_times):.1f}ms")
            print(f"  Slowest route: {max(all_avg_times):.1f}ms")
            print(f"  Average response time: {statistics.mean(all_avg_times):.1f}ms")
            print(f"  Total usage count: {sum(all_usages):,}")
            
            # Identify caching candidates
            print("\n🎯 TOP CANDIDATES (slow + high usage):")
            caching_candidates = [r for r in successful_results if r["stats"]["avg_ms"] > 100]
            caching_candidates.sort(key=lambda x: x["stats"]["avg_ms"] * x["usage_count"], reverse=True)
            
            for i, result in enumerate(caching_candidates[:10], 1):
                stats = result["stats"]
                impact = stats["avg_ms"] * result["usage_count"] / 1000
                print(f"  {i:2d}. {result['route']:<35} ({stats['avg_ms']:.1f}ms × {result['usage_count']} = {impact:.0f}s impact)")
    
    def export_json(self, results: List[Dict], filename: str):
        """Export results to JSON file."""
        export_data = {
            "test_timestamp": time.time(),
            "test_config": {
                "host": self.host,
                "port": self.port,
                "timeout": self.timeout
            },
            "results": results
        }
        
        with open(filename, 'w') as f:
            json.dump(export_data, f, indent=2)
        print(f"\n📁 Results exported to: {filename}")


def main():
    parser = argparse.ArgumentParser(description="Test pypowerwall proxy route performance")
    parser.add_argument("--host", default="localhost", help="Proxy host (default: localhost)")
    parser.add_argument("--port", type=int, default=8675, help="Proxy port (default: 8675)")
    parser.add_argument("--requests", type=int, default=5, help="Number of requests per route (default: 5)")
    parser.add_argument("--timeout", type=int, default=10, help="Request timeout in seconds (default: 10)")
    parser.add_argument("--sort", choices=["avg", "usage", "impact"], default="impact", 
                       help="Sort results by: avg (response time), usage (request count), impact (time×usage)")
    parser.add_argument("--export", help="Export results to JSON file")
    parser.add_argument("--errors", action="store_true", help="Show detailed error messages")
    
    args = parser.parse_args()
    
    # Test connection first
    tester = RoutePerformanceTester(args.host, args.port, args.timeout)
    print(f"Testing connection to {args.host}:{args.port}...")
    
    try:
        response = tester.session.get(f"{tester.base_url}/stats", timeout=5)
        print(f"✅ Connection successful (status: {response.status_code})")
    except Exception as e:
        print(f"❌ Connection failed: {e}")
        print("Please check that the proxy is running and accessible.")
        sys.exit(1)
    
    # Run tests
    results = tester.run_all_tests(args.requests, args.sort)
    
    # Print results
    tester.print_summary(results, args.errors)
    
    # Export if requested
    if args.export:
        tester.export_json(results, args.export)


if __name__ == "__main__":
    main()