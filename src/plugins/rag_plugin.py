from typing import Annotated

from semantic_kernel.functions.kernel_function_decorator import kernel_function

from src.database import VectorDatabase
from src.utils import get_logger

logger = get_logger(__name__)


class RAGPlugin:
    """RAGPlugin provides a set of functions to run the RAG pipeline."""

    def __init__(self, vector_db: VectorDatabase) -> None:
        self.vector_db = vector_db

    @kernel_function(
        name="rag_retrieve",
        description="Retrieve relevant ETF investment information from key information documents based on the user's query. "
        "This includes ETF details such as product name, manufacturer, risk class, costs, and key content. "
        "Use this function when the user asks about ETFs, investment options, risks, or costs.",
    )
    def rag_retrieve(
        self,
        query: Annotated[
            str,
            "A search query to retrieve documents from the search index based on the user query.",
        ],
    ) -> Annotated[
        str,
        "The context retrieved, containing relevant details from the ETF key information documents.",
    ]:
        logger.info("Running RAG retrieval with query: {}".format(query))

        outputs = self.vector_db.get_documents(query)
        context_keys = ["product_name", "manufacturer", "risk_class", "content"]
        context = [{k: d[k] for k in context_keys if k in d} for d in outputs]

        return context
