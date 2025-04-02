import os
import uuid
from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import ConnectionType
from azure.identity import DefaultAzureCredential
from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient
from azure.search.documents.models import VectorizedQuery
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import (
    SemanticSearch,
    SearchField,
    SimpleField,
    SearchableField,
    SearchFieldDataType,
    SemanticConfiguration,
    SemanticPrioritizedFields,
    SemanticField,
    VectorSearch,
    HnswAlgorithmConfiguration,
    VectorSearchAlgorithmKind,
    HnswParameters,
    VectorSearchAlgorithmMetric,
    ExhaustiveKnnAlgorithmConfiguration,
    ExhaustiveKnnParameters,
    VectorSearchProfile,
    SearchIndex,
)

from ..utils import get_logger
from ..rag import TextChunker

logger = get_logger(__name__)


class VectorDatabase:

    def __init__(
        self, config: dict, search_index: str, conn_str: str, model: str, emb_model: str
    ):
        self.text_chunker = TextChunker(config, conn_str, model)
        self.search_index = search_index
        self.config = config
        self.emb_model = emb_model

        # create a project client using environment variables loaded from the .env file
        self.project = AIProjectClient.from_connection_string(
            conn_str=conn_str,
            credential=DefaultAzureCredential(),
        )

        # create a chat client for entity extraction
        self.chat = self.project.inference.get_chat_completions_client()

        # create a vector embeddings client that will be used to generate vector embeddings
        self.embeddings = self.project.inference.get_embeddings_client()

        # use the project client to get the default search connection
        self.search_connection = self.project.connections.get_default(
            connection_type=ConnectionType.AZURE_AI_SEARCH, include_credentials=True
        )

        # Create a search index client using the search connection
        # This client will be used to create and delete search indexes
        self.index_client = SearchIndexClient(
            endpoint=self.search_connection.endpoint_url,
            credential=AzureKeyCredential(key=self.search_connection.key),
        )
        # Create a search index client using the search connection
        # This client will be used to retrieve documents
        self.search_client = SearchClient(
            index_name=search_index,
            endpoint=self.search_connection.endpoint_url,
            credential=AzureKeyCredential(key=self.search_connection.key),
        )

    def create_index_definition(self) -> SearchIndex:
        """
        Create search index parameters and fields.
        """
        dimensions = 1536  # text-embedding-ada-002
        if self.emb_model == "text-embedding-3-large":
            dimensions = 3072

        # The fields we want to index. The "embedding" field is a vector field that will
        # be used for vector search.
        fields = [
            SimpleField(name="id", type=SearchFieldDataType.String, key=True),
            SearchableField(name="content", type=SearchFieldDataType.String),
            SimpleField(name="label", type=SearchFieldDataType.String),
            SearchableField(name="title", type=SearchFieldDataType.String),
            SearchableField(
                name="file", type=SearchFieldDataType.String, filterable=True
            ),
            SearchField(
                name="contentVector",
                type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
                searchable=True,
                # Size of the vector created by the text-embedding-ada-002 model.
                vector_search_dimensions=dimensions,
                vector_search_profile_name="myHnswProfile",
            ),
        ]

        if self.config["rag_entities"]:
            for entity_type in self.config["rag_entities"]:
                fields.append(
                    SearchableField(name=entity_type, type=SearchFieldDataType.String)
                )

        # The "content" field should be prioritized for semantic ranking.
        semantic_config = SemanticConfiguration(
            name="default",
            prioritized_fields=SemanticPrioritizedFields(
                title_field=SemanticField(field_name="title"),
                keywords_fields=[],
                content_fields=[SemanticField(field_name="content")],
            ),
        )

        # For vector search, we want to use the HNSW (Hierarchical Navigable Small World)
        # algorithm (a type of approximate nearest neighbor search algorithm) with cosine
        # distance.
        vector_search = VectorSearch(
            algorithms=[
                HnswAlgorithmConfiguration(
                    name="myHnsw",
                    kind=VectorSearchAlgorithmKind.HNSW,
                    parameters=HnswParameters(
                        m=4,
                        ef_construction=1000,
                        ef_search=1000,
                        metric=VectorSearchAlgorithmMetric.COSINE,
                    ),
                ),
                ExhaustiveKnnAlgorithmConfiguration(
                    name="myExhaustiveKnn",
                    kind=VectorSearchAlgorithmKind.EXHAUSTIVE_KNN,
                    parameters=ExhaustiveKnnParameters(
                        metric=VectorSearchAlgorithmMetric.COSINE
                    ),
                ),
            ],
            profiles=[
                VectorSearchProfile(
                    name="myHnswProfile",
                    algorithm_configuration_name="myHnsw",
                ),
                VectorSearchProfile(
                    name="myExhaustiveKnnProfile",
                    algorithm_configuration_name="myExhaustiveKnn",
                ),
            ],
        )

        # Create the semantic settings with the configuration
        semantic_search = SemanticSearch(configurations=[semantic_config])

        # Create the search index definition
        return SearchIndex(
            name=self.search_index,
            fields=fields,
            semantic_search=semantic_search,
            vector_search=vector_search,
        )

    def create_docs_from_pdf(self, path: str) -> list[dict[str, any]]:
        """
        Create index entries from a pdf file.
        """
        filename = os.path.basename(path)
        chunks, metadatas = self.text_chunker.chunk_from_pdf(path)
        items = []

        for chunk in chunks:
            id = str(uuid.uuid4())
            emb = self.embeddings.embed(input=chunk, model=self.emb_model)
            rec = {
                "id": id,
                "content": chunk,
                # "label": "text",
                "title": filename,
                "file": filename,
                "contentVector": emb.data[0].embedding,
            }
            if isinstance(metadatas, dict):
                rec.update(metadatas)
            items.append(rec)

        return items

    def add_to_index_from_pdf(self, pdf_file):
        """
        Add entries to the index from a pdf file.
        """

        # create documents from the pdf file, generating vector embeddings for the extracted chunks
        docs = self.create_docs_from_pdf(path=pdf_file)

        # Add the documents to the index using the Azure AI Search client
        self.search_client.upload_documents(docs)
        logger.info(f"➕ Uploaded {len(docs)} documents to '{self.search_index}' index")

    def create_index_from_pdf(self, pdf_file):
        # If a search index already exists, delete it:
        index_names = self.list_index_names()
        if self.search_index in index_names:
            self.index_client.delete_index(self.search_index)
            logger.info(
                f"🗑️  Found existing index named '{self.search_index}', and deleted it"
            )

        # create an empty search index
        index_definition = self.create_index_definition()
        self.index_client.create_index(index_definition)

        self.add_to_index_from_pdf(pdf_file)

    def remove_from_index(self, pdf_file):
        """
        Remove from the index all entries from a pdf_file.
        """
        try:
            # Search for documents with the given filename in the 'id' field
            filename = os.path.basename(pdf_file)
            results = self.search_client.search(
                search_text="*", filter=f"file eq '{filename}'", select=["id"]
            )
            document_keys = [doc["id"] for doc in results]

            if not document_keys:
                logger.info(
                    f"ℹ️ No documents found with filename '{filename}' in '{self.search_index}' index."
                )
                return None

            actions = [
                {"@search.action": "delete", "id": doc_id} for doc_id in document_keys
            ]

            result = self.search_client.upload_documents(actions)
            logger.info(
                f"🗑️ Deleted {len(document_keys)} documents with filename '{filename}' from '{self.search_index}' index"
            )
            return result
        except Exception as e:
            logger.error(f"⚠️ Error deleting documents: {str(e)}")
            return None

    def list_index_names(self) -> list[str]:
        """
        List all indexes of the index client.
        """
        return [index for index in self.index_client.list_index_names()]

    def get_documents(self, search_query: str, context: dict = None) -> dict:
        """
        Search through the Search Index and retriev relevant documents.
        """
        if context is None:
            context = {}

        overrides = context.get("overrides", {})
        top = overrides.get("top", self.config["top_k"])

        logger.debug(f"🧠 Intent mapping: {search_query}")

        # generate a vector representation of the search query
        embedding = self.embeddings.embed(model=self.emb_model, input=search_query)
        search_vector = embedding.data[0].embedding

        # search the index for products matching the search query
        vector_query = VectorizedQuery(
            vector=search_vector, k_nearest_neighbors=top, fields="contentVector"
        )

        search_results = self.search_client.search(
            search_text=search_query,
            vector_queries=[vector_query],
            # select=["file", "content", "product_name"],
            top=top,
        )

        documents = [result for result in search_results]

        # add results to the provided context
        if "thoughts" not in context:
            context["thoughts"] = []

        # add thoughts and documents to the context object so it can be returned to the caller
        context["thoughts"].append(
            {
                "title": "Generated search query",
                "description": search_query,
            }
        )

        if "grounding_data" not in context:
            context["grounding_data"] = []
        context["grounding_data"].append(documents)

        logger.debug(f"📄 {len(documents)} documents retrieved: {documents}")
        return documents

    def __del__(self):
        self.project.close()

    def close(self):
        self.project.close()
