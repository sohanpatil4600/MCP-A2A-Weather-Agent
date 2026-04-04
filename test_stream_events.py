import asyncio
from mcp_use import MCPAgent, MCPClient
from langchain_groq import ChatGroq
from dotenv import load_dotenv

load_dotenv()

async def test():
    client = MCPClient.from_config_file("server/weather.json")
    llm = ChatGroq(model="llama-3.1-8b-instant")
    agent = MCPAgent(llm=llm, client=client, max_steps=3)
    
    try:
        async for event in agent.stream_events("What is the weather in Paris?", version="v2"):
            if event["event"] == "on_chat_model_stream":
                content = event["data"]["chunk"].content
                if content:
                    print(content, end="", flush=True)
    except Exception as e:
        print("\nERROR:", e)
    await agent.close()

if __name__ == "__main__":
    asyncio.run(test())
