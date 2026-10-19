
import asyncio
import json

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main():
    server = StdioServerParameters(
        command="wsl",
        args=[
            "-e",
            "/mnt/c/Users/Abdul Hannan/OneDrive/Desktop/MindMeshAI/whatsapp-mcp-server/whatsapp-mcp",
            "serve",
        ],
    )

    async with stdio_client(server) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()

            tools = await session.list_tools()

            print("Connected to WhatsApp MCP server!")
            print("\nAvailable tools:")

            # for tool in tools.tools:
            #     if tool.name in ("list_chats", "list_messages", "get_chat"):
            #         print(f"\n--- {tool.name} ---")
            #         print(tool.inputSchema)
            # result = await session.call_tool(
            #     "list_chats",
            #     arguments={"limit": 5}
            # )

            # print("\n--- RECENT CHATS ---")
            # print(result)

            result = await session.call_tool(
                "list_messages",
                arguments={
                    "chat": "120363409895090843@g.us",
                    "limit": 3
                }
            )

            print("\n--- THREE RECENT MESSAGES ---")
            print(result.structuredContent)


if __name__ == "__main__":
    asyncio.run(main())