import requests
import json

url = "http://localhost:8001/agent/audit-documents"

payload = {
    "doc1_text": "The monthly service fee is 500 USD, payable on the 1st of each month. Termination requires 30 days notice.",
    "doc2_text": "The monthly service fee is 750 USD, payable on the 15th of each month. Termination notice is not mentioned."
}

print("Sending request to Cross-Document Auditor API (http://localhost:8001)...")
try:
    response = requests.post(url, json=payload)
    if response.status_code != 200:
        print("\nError: API returned status code", response.status_code)
        print("Response text:", response.text)
    else:
        response.raise_for_status()
        data = response.json()
        
        if data.get("success"):
            print("\n=== COMPARISON RESULTS ===")
            print(json.dumps(data.get("comparison_results"), indent=2, ensure_ascii=False))
            
            print("\n=== EXECUTIVE SUMMARY ===")
            print(data.get("executive_summary"))
        else:
            print("\nError: API returned success=False")
            print(data)
        
except requests.exceptions.RequestException as e:
    print(f"\nRequest failed: {e}")
