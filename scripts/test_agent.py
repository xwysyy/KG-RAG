"""Quick smoke test for the agent pipeline (non-interactive)."""

import asyncio
import logging
import time

from langchain_core.messages import HumanMessage

from kg_rag.config import settings
from kg_rag.storage.nano_vector import NanoVectorStore
from kg_rag.storage.neo4j_graph import Neo4jGraphStore
from kg_rag.tools.vector_search import create_vector_search
from kg_rag.tools.graph_query import create_graph_query
from kg_rag.tools.web_search import web_search
from kg_rag.agent.graph import build_agent_graph
from kg_rag.memory.profile import read_profile

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)

TEST_QUESTION = "BFS 和 DFS 有什么区别？分别适用于什么场景？"


async def main():
    # Init stores
    vector_store = NanoVectorStore()
    graph_store = Neo4jGraphStore()
    await graph_store.initialize()

    try:
        # Build tools & graph
        tools = [
            create_vector_search(vector_store),
            create_graph_query(graph_store),
            web_search,
        ]
        agent = build_agent_graph(tools)

        # Read profile
        profile = await read_profile("default", graph_store)
        logger.info("User profile: %s", profile[:200] if profile else "(empty)")

        # Run agent
        logger.info("Question: %s", TEST_QUESTION)
        t0 = time.time()

        result = await agent.ainvoke(
            {
                "messages": [HumanMessage(content=TEST_QUESTION)],
                "todos": [],
                "user_profile": profile,
                "iteration": 0,
                "max_iterations": settings.max_iterations,
                "intermediate_results": [],
                "final_answer": "",
            }
        )

        elapsed = time.time() - t0
        answer = result.get("final_answer", "No answer produced.")
        iteration = result.get("iteration", 0)

        print("\n" + "=" * 60)
        print(f"Question: {TEST_QUESTION}")
        print(f"Iterations: {iteration}")
        print(f"Time: {elapsed:.1f}s")
        print("=" * 60)
        print(answer)
        print("=" * 60)

    finally:
        await graph_store.finalize()
        await vector_store.finalize()


if __name__ == "__main__":
    asyncio.run(main())
