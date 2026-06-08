import asyncio
from core.tools.file_tools import file_tools
from core.knowledge.code_graph import code_graph
from core.tools.code_analysis_tools import code_analysis_tools

async def main():
    print("--- Test Sandboxing ---")
    try:
        # Try to read outside the workspace
        res = await file_tools.read_file("../../../../../etc/passwd")
        print(f"Read file result: {res}")
        if "Access Denied" in res or "PermissionError" in res or "Error reading file" in res:
            print("Successfully caught path traversal!")
    except PermissionError as e:
        print(f"Caught expected PermissionError: {e}")
    except Exception as e:
        print(f"Caught other exception: {e}")

    print("\n--- Test File Writing ---")
    res_a = await file_tools.write_file("dummy_a.py", "import os\nfrom dummy_b import my_func\n", "Agent1")
    print(f"Write dummy_a.py: {res_a.message if hasattr(res_a, 'message') else res_a}")
    res_b = await file_tools.write_file("dummy_b.py", "def my_func(): pass\n", "Agent2")
    print(f"Write dummy_b.py: {res_b.message if hasattr(res_b, 'message') else res_b}")

    print("\n--- Test Code Graph Integration ---")
    # Simulate event bus hook
    print("Parsing dummy_a.py...")
    code_graph.parse_file("dummy_a.py")
    
    # Analyze impact
    print("Analyzing impact of dummy_b.py:")
    impact = code_analysis_tools.analyze_impact("dummy_b.py")
    print(impact)

    print("\n--- Test Active Lock Tracking ---")
    code_graph.mark_file_active("dummy_b.py", "Nova")
    impact_with_lock = code_analysis_tools.analyze_impact("dummy_b.py")
    print("Impact with lock:")
    print(impact_with_lock)
    
    # Cleanup (optional but good practice)
    await file_tools.delete_file("dummy_a.py")
    await file_tools.delete_file("dummy_b.py")

if __name__ == "__main__":
    asyncio.run(main())
