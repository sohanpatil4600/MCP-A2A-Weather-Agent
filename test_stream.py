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
        print("Starting stream...")
        async for chunk in agent.stream("What is the weather in Paris?"):
            print("CHUNK:", repr(chunk))
    except Exception as e:
        print("ERROR:", e)
    await agent.close()

if __name__ == "__main__":
    asyncio.run(test())
