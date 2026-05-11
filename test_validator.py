from dotenv import load_dotenv
load_dotenv(override=True)

from agent.missing_info_agent import validator_app

def main():
    mock_text = (
        "To Harran University Rectorate, I would like to apply for the graduation ceremony. "
        "Name: Merve Aişeoğlu. Address: Şanlıurfa. "
        "(Note: The user forgot to add Date and TC ID Number)"
    )
    
    initial_state = {
        "extracted_text": mock_text,
        "validation_results": {}
    }
    
    print("Invoking Dynamic Missing-Info Agent...\n")
    print(f"Input Text:\n\"{mock_text}\"\n")
    
    try:
        # Run the graph synchronously
        final_state = validator_app.invoke(initial_state)
        results = final_state.get("validation_results", {})
        
        print("=== VALIDATION RESULTS ===")
        print(f"Document Type  : {results.get('document_type')}")
        print(f"Is Complete?   : {results.get('is_complete')}")
        
        missing = results.get('missing_fields', [])
        if missing:
            print(f"Missing Fields : {', '.join(missing)}")
        else:
            print("Missing Fields : None")
            
    except Exception as e:
        print(f"Graph execution failed: {e}")

if __name__ == "__main__":
    main()
