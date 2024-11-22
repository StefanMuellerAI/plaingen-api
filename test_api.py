import asyncio
import aiohttp
import time
from datetime import datetime
import json
import argparse
from rich.console import Console
from rich.table import Table
from rich.progress import Progress
from dotenv import load_dotenv
import os

# Lade .env Datei
load_dotenv()

console = Console()

class APITester:
    def __init__(self, base_url):
        self.base_url = base_url
        self.api_key = os.getenv('API_KEY')
        if not self.api_key:
            raise ValueError("API_KEY nicht in .env gefunden")
            
        self.headers = {
            "X-API-Key": self.api_key,
            "Content-Type": "application/json"
        }
        self.results = {
            "success": 0,
            "failed": 0,
            "total_time": 0,
            "errors": []
        }

    async def make_request(self, session, request_id):
        start_time = time.time()
        try:
            payload = {
                "topic": "Künstliche Intelligenz im Marketing",
                "language": "DE",
                "address": "Informally",
                "mood": "inspiring",
                "perspective": "Me"
            }
            
            async with session.post(
                f"{self.base_url}/task/research_task",
                headers=self.headers,
                json=payload,
                timeout=300
            ) as response:
                duration = time.time() - start_time
                status = response.status
                
                if status == 200:
                    self.results["success"] += 1
                else:
                    self.results["failed"] += 1
                    error_text = await response.text()
                    self.results["errors"].append({
                        "request_id": request_id,
                        "status": status,
                        "error": error_text,
                        "duration": duration
                    })
                
                return {
                    "request_id": request_id,
                    "status": status,
                    "duration": duration
                }

        except Exception as e:
            duration = time.time() - start_time
            self.results["failed"] += 1
            self.results["errors"].append({
                "request_id": request_id,
                "status": "Exception",
                "error": str(e),
                "duration": duration
            })
            return {
                "request_id": request_id,
                "status": "Exception",
                "duration": duration
            }

    async def run_tests(self, num_requests, concurrent_requests):
        async with aiohttp.ClientSession() as session:
            with Progress() as progress:
                task = progress.add_task("[cyan]Running tests...", total=num_requests)
                
                # Erstelle Chunks von Anfragen für kontrollierte Parallelität
                chunks = [list(range(num_requests))[i:i + concurrent_requests] 
                         for i in range(0, num_requests, concurrent_requests)]
                
                start_time = time.time()
                
                for chunk in chunks:
                    tasks = [self.make_request(session, i) for i in chunk]
                    results = await asyncio.gather(*tasks)
                    
                    for result in results:
                        progress.update(task, advance=1)
                        self.results["total_time"] = time.time() - start_time

    def print_results(self):
        console.print("\n[bold green]Test Results:[/bold green]")
        
        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("Metric", style="dim")
        table.add_column("Value")
        
        total_requests = self.results["success"] + self.results["failed"]
        success_rate = (self.results["success"] / total_requests) * 100 if total_requests > 0 else 0
        
        table.add_row("Total Requests", str(total_requests))
        table.add_row("Successful Requests", str(self.results["success"]))
        table.add_row("Failed Requests", str(self.results["failed"]))
        table.add_row("Success Rate", f"{success_rate:.2f}%")
        table.add_row("Total Time", f"{self.results['total_time']:.2f}s")
        table.add_row("Average Time per Request", 
                     f"{(self.results['total_time'] / total_requests):.2f}s" if total_requests > 0 else "N/A")
        
        console.print(table)
        
        if self.results["errors"]:
            console.print("\n[bold red]Errors:[/bold red]")
            error_table = Table(show_header=True, header_style="bold red")
            error_table.add_column("Request ID")
            error_table.add_column("Status")
            error_table.add_column("Error")
            error_table.add_column("Duration (s)")
            
            for error in self.results["errors"]:
                error_table.add_row(
                    str(error["request_id"]),
                    str(error["status"]),
                    str(error["error"])[:100] + "..." if len(str(error["error"])) > 100 else str(error["error"]),
                    f"{error['duration']:.2f}"
                )
            
            console.print(error_table)

def main():
    parser = argparse.ArgumentParser(description='API Load Tester')
    parser.add_argument('--url', default='https://api.easiergen.com', help='Base URL of the API')
    parser.add_argument('--requests', type=int, default=10, help='Number of requests to send')
    parser.add_argument('--concurrent', type=int, default=2, help='Number of concurrent requests')
    
    args = parser.parse_args()
    
    tester = APITester(args.url)
    
    console.print(f"[bold]Starting API Test[/bold]")
    console.print(f"URL: {args.url}")
    console.print(f"Total Requests: {args.requests}")
    console.print(f"Concurrent Requests: {args.concurrent}")
    
    asyncio.run(tester.run_tests(args.requests, args.concurrent))
    tester.print_results()

if __name__ == "__main__":
    main() 