#!/usr/bin/env python3
"""Direct Timmy interview — bypasses dashboard, tests core agent."""

import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

def main():
    print("\n" + "=" * 75)
    print("  TIMMY TIME — DIRECT INTERVIEW")
    print("=" * 75 + "\n")
    
    try:
        # Import after path setup
        from timmy.interview import run_interview, format_transcript
        from timmy.session import chat
        
        print("🚀 Initializing Timmy agent...\n")
        
        # Run the interview
        transcript = run_interview(chat)
        
        # Format and display
        formatted = format_transcript(transcript)
        print(formatted)
        
        # Save to file
        with open("interview_transcript.txt", "w") as f:
            f.write(formatted)
        print("\n✅ Transcript saved to interview_transcript.txt\n")
        
        return 0
        
    except Exception as e:
        print(f"\n❌ ERROR: {e}\n")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())
