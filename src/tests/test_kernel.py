import os
import pytest
import pytest_asyncio
from dotenv import load_dotenv
from semantic_kernel.contents.chat_history import ChatHistory
from semantic_kernel.contents import AuthorRole
from azure.identity import DefaultAzureCredential

from ..kernel import Kernel
from ..database import SQLDatabase, VectorDatabase
from ..utils import CONFIG


load_dotenv()
TEST_QUERIES = [
    "What is the total amount of transactions?",
    "Can you retrieve all purchases from Oakland?",
    "Show me the top 5 selling products.",
]


@pytest_asyncio.fixture()
async def kernel_instance():
    credential = DefaultAzureCredential()
    server_name = os.getenv("server_name")
    database_name = os.getenv("database_name")
    uname = os.getenv("uname")
    pwd = os.getenv("pwd")
    conn_str = os.getenv("AIPROJECT_CONNECTION_STRING", None)
    model_name = os.getenv("DEPLOYMENT_NAME", None)
    emb_model = os.getenv("EMBEDDINGS_MODEL", None)
    aisearch_index_name = os.getenv("AISEARCH_INDEX_NAME")

    database_service = SQLDatabase(
        server_name=server_name, database_name=database_name, uname=uname, pwd=pwd
    )
    database_service.setup()

    vector_db = VectorDatabase(
        config=CONFIG,
        search_index=aisearch_index_name,
        conn_str=conn_str,
        model=model_name,
        emb_model=emb_model,
    )

    kernel = await Kernel.create(
        database_service=database_service,
        credential=credential,
        conn_str=conn_str,
        model_name=model_name,
        vector_db=vector_db,
    )

    return kernel


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "query, expected_plugins",
    [
        (
            "What is the total amount of transactions?",
            ["plugins-discover_database", "plugins-sql_query"],
        ),
        (
            "Now let me check my transactions history. Which cities have the most transactions ?",
            ["plugins-discover_database", "plugins-sql_query"],
        ),
        (
            "I am interested in a stable investment with low-risk. What are the options?",
            ["plugins-rag_retrieve"],
        ),
    ],
)
async def test_message(kernel_instance, query, expected_plugins):
    chat_history = ChatHistory()
    chat_history.add_system_message(
        "You are an AI financial advisor answering questions about finance, capital market, investments, pensions, insurance and banking products. "
        "You have access to a vector database of ETF key information documents and a SQL database of transactions. The SQL database must be discovered in order to understand its structure. "
        "From the query given by the user you must understand which tool call to perform (if any). "
        "Every query you make MUST be in the MSSQL language."
    )

    _ = await kernel_instance.message(query, chat_history)

    await kernel_instance.close()

    used_plugins = []
    for message in chat_history[1:]:
        if message.role == AuthorRole.TOOL:
            used_plugins.extend([item.name for item in message.items])

    try:
        assert used_plugins == expected_plugins
    except AssertionError:
        print("\nAssertion failed!")
        print("Used Plugins:", used_plugins)
        print("Expected Plugins:", expected_plugins)
        raise


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "query",
    [
        "Now let me check my transactions history. Which cities have the most transactions ?",
    ],
)
async def test_single_message(kernel_instance, query):
    chat_history = ChatHistory()
    chat_history.add_system_message(
        "You are an AI financial advisor answering questions about finance, capital market, investments, pensions, insurance and banking products. "
        "You have access to a vector database of ETF key information documents and a SQL database of transactions. The SQL database must be discovered in order to understand its structure. "
        "From the query given by the user you must understand which tool call to perform (if any). "
        "Every query you make MUST be in the MSSQL language."
    )

    output = await kernel_instance.message(query, chat_history)

    await kernel_instance.close()

    print(f"\n\nOUTPUT: {output}\n\n")
