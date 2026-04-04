import asyncio
from mcp_use import MCPAgent, MCPClient
from langchain_groq import ChatGroq
from langchain_core.callbacks import AsyncCallbackHandler
from dotenv import load_dotenv
import sys

load_dotenv()

class MyAsyncHandler(AsyncCallbackHandler):
    async def on_llm_new_token(self, token: str, **kwargs) -> None:
        sys.stdout.write(token)
        sys.stdout.flush()

async def test():
    client = MCPClient.from_config_file("server/weather.json")
    handler = MyAsyncHandler()
    llm = ChatGroq(model="llama-3.1-8b-instant", streaming=True, callbacks=[handler])
    agent = MCPAgent(llm=llm, client=client, max_steps=3)
    
    try:
        print("Starting agent.run...")
        await agent.run("What is the weather in Paris?")
        print("\n\nFinished agent.run")
    except Exception as e:
        print("\n\nERROR:", e)
    await agent.close()

if __name__ == "__main__":
    asyncio.run(test())
