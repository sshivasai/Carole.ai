import asyncio
import uuid
from core.llm.multi_model_router import MultiModelRouter
from core.memory.database import async_session, engine
from core.memory.models import TokenUsage, User, Project, Team, Agent, Base
from sqlalchemy import select

async def main():
    # 0. Initialize the database schema for testing
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    # 1. Instantiate MultiModelRouter
    router = MultiModelRouter()
    
    # 2. Dummy UUIDs
    user_id = uuid.uuid4()
    project_id = uuid.uuid4()
    team_id = uuid.uuid4()
    agent_id = uuid.uuid4()
    
    # Create the dummy hierarchy so foreign keys don't fail
    async with async_session() as session:
        user = User(id=user_id, email=f"{user_id}@test.com", hashed_password="pw")
        session.add(user)
        await session.flush()
        
        project = Project(id=project_id, name="Test Project", owner_id=user_id)
        session.add(project)
        await session.flush()
        
        team = Team(id=team_id, name="Test Team", project_id=project_id)
        session.add(team)
        await session.flush()
        
        agent = Agent(
            id=agent_id, team_id=team_id, name="Test Agent", 
            role="Test", model="openrouter/free", system_prompt="Test"
        )
        session.add(agent)
        await session.commit()
    
    print("Testing MultiModelRouter generation...")
    
    model = "openrouter/free"
    system_prompt = "You are a helpful assistant."
    messages = [{"role": "user", "content": "Hello, this is a test."}]
    
    # 3. Call generate_stream and print chunks
    chunks = []
    async for chunk in router.generate_stream(
        model=model,
        system_prompt=system_prompt,
        messages=messages,
        project_id=str(project_id),
        team_id=str(team_id),
        agent_id=str(agent_id),
        agent_name="Test Agent"
    ):
        print(f"CHUNK: {chunk}")
        chunks.append(chunk)
        
    print("\nGeneration finished.")
    
    # 4. Wait briefly for background task to complete logging
    print("Waiting for background task to log usage...")
    await asyncio.sleep(2)
    
    # 5. Query TokenUsage table
    print("Querying TokenUsage table...")
    async with async_session() as session:
        result = await session.execute(
            select(TokenUsage).where(TokenUsage.project_id == project_id)
        )
        usage = result.scalars().first()
        
        if usage:
            print("\n--- Token Usage Log Found ---")
            print(f"ID: {usage.id}")
            print(f"Project ID: {usage.project_id}")
            print(f"Agent Name: {usage.agent_name}")
            print(f"Model: {usage.model}")
            print(f"Prompt Tokens: {usage.prompt_tokens}")
            print(f"Completion Tokens: {usage.completion_tokens}")
            print(f"Total Tokens: {usage.total_tokens}")
            print(f"Estimated Cost USD: {usage.estimated_cost_usd}")
            print("-----------------------------\n")
        else:
            print("\n--- NO TOKEN USAGE LOG FOUND! ---")

if __name__ == "__main__":
    asyncio.run(main())
