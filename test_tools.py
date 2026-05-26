"""
Test script to verify all tools are properly registered
"""

import sys
from core.tools import ToolRegistry
from core.tools import all_tools  # noqa: F401 - side effect import to register tools

# Fix Windows encoding
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')


def main():
    print("=" * 60)
    print("BATTLEFIELD TOOL REGISTRY TEST")
    print("=" * 60)

    tools = ToolRegistry.list_all()
    print(f"\n✓ Registered {len(tools)} tools\n")

    categories = {}
    for tool in tools:
        if tool.category not in categories:
            categories[tool.category] = []
        categories[tool.category].append(tool)

    for category, cat_tools in sorted(categories.items()):
        print(f"\n{'=' * 60}")
        print(f"CATEGORY: {category.upper()}")
        print('=' * 60)

        for tool in cat_tools:
            print(f"\n🔧 {tool.name}")
            print(f"   {tool.description}")
            print(f"   Parameters: {list(tool.parameters.keys())}")
            if tool.requires_confirmation:
                print(f"   ⚠️  Requires confirmation")

    print("\n" + "=" * 60)
    print("LLM PROMPT GENERATION")
    print("=" * 60)
    print("\n" + ToolRegistry.to_llm_prompt())

    print("\n" + "=" * 60)
    print("TESTING INDIVIDUAL TOOLS")
    print("=" * 60)

    # Test list_files
    print("\n📁 Testing list_files...")
    list_tool = ToolRegistry.get("list_files")
    if list_tool:
        import asyncio
        result = asyncio.run(list_tool.execute(path=".", recursive=False))
        print(result)

    # Test write and read
    print("\n📝 Testing write_file...")
    write_tool = ToolRegistry.get("write_file")
    if write_tool:
        result = asyncio.run(write_tool.execute(
            path="test_output.txt",
            content="Hello from Battlefield!"
        ))
        print(result)

    print("\n📖 Testing read_file...")
    read_tool = ToolRegistry.get("read_file")
    if read_tool:
        result = asyncio.run(read_tool.execute(path="test_output.txt"))
        print(result)

    print("\n✓ Tool system test complete!")


if __name__ == "__main__":
    main()
