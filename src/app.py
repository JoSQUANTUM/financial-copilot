import os

from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv
from semantic_kernel.contents.chat_history import ChatHistory

from .database import SQLDatabase, VectorDatabase
from .kernel import Kernel
from .utils import SYSTEM_MESSAGE, get_logger, CONFIG


logger = get_logger(__name__)

load_dotenv()


# Main function to set up services
async def kernel_setup():
    load_dotenv()
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
        server_name=server_name,
        database_name=database_name,
        uname=uname,
        pwd=pwd,
    )
    database_service.setup()

    # Setup the vector database for RAG
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


def chat_setup():
    # Create a history of the conversation
    chat_history = ChatHistory()
    chat_history.add_system_message(SYSTEM_MESSAGE)
    return chat_history


from .api import serve_app

serve_app(kernel_setup, chat_setup)
