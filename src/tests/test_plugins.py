import os
from dotenv import load_dotenv

from ..database import SQLDatabase, VectorDatabase
from ..plugins.rag_plugin import RAGPlugin
from ..plugins.sql_plugin import SQLPlugin
from ..plugins.processing_plugin import ProcessingPlugin
from ..utils import CONFIG

load_dotenv()
INDEX_NAME = "rag-search-test"
config = CONFIG.copy()


def test_rag_plugin():
    original_top_k = config["top_k"]
    config["top_k"] = 2
    vector_db = VectorDatabase(
        config=config,
        search_index=INDEX_NAME,
        conn_str=os.getenv("AIPROJECT_CONNECTION_STRING"),
        model=os.getenv("DEPLOYMENT_NAME"),
        emb_model=os.getenv("EMBEDDINGS_MODEL"),
    )
    rag_plugin = RAGPlugin(vector_db)

    query = "In welchem ETF soll ich investieren?"
    context = rag_plugin.rag_retrieve(query)
    assert isinstance(context, list)
    assert len(context) == config["top_k"]
    assert isinstance(context[0], dict)
    assert isinstance(context[0]["content"], str)
    assert "product_name" in context[0]
    assert "manufacturer" in context[0]
    assert "risk_class" in context[0]

    config["top_k"] = original_top_k


def test_database_plugin():
    server_name = os.getenv("server_name")
    database_name = os.getenv("database_name")
    uname = os.getenv("uname")
    pwd = os.getenv("pwd")

    database_service = SQLDatabase(
        server_name=server_name, database_name=database_name, uname=uname, pwd=pwd
    )
    database_service.setup()

    database_plugin = SQLPlugin(database_service)

    queries = [
        "SELECT COUNT(*) FROM qna WHERE errors is NOT NULL;",
        "SELECT MAX(amount) AS max_amount FROM qna;",
        "SELECT SUM(amount) FROM qna WHERE merchant_city == 'Beulah';",
        "SELECT use_chip FROM qna GROUP BY use_chip ORDER BY COUNT(use_chip) DESC LIMIT 1;",
    ]
    ground_truths = [[(9,)], [(1153.61,)], [(39.63,)], [("Swipe Transaction",)]]

    for i, query in enumerate(queries):
        output = database_plugin.sql_query(query)
        output_as_tuples = [tuple(row) for row in output]

        assert output_as_tuples == ground_truths[i]


def test_processing_plugin():
    vector_db = VectorDatabase(
        config=config,
        search_index=INDEX_NAME,
        conn_str=os.getenv("AIPROJECT_CONNECTION_STRING"),
        model=os.getenv("DEPLOYMENT_NAME"),
        emb_model=os.getenv("EMBEDDINGS_MODEL"),
    )
    processing_plugin = ProcessingPlugin(vector_db)
    test_folder = "assets/tests/"
    test_file_1 = "KID_test_1.pdf"
    test_file_2 = "KID_test_2.pdf"

    # Initialize test search index
    vector_db.create_index_from_pdf(pdf_file=os.path.join(test_folder, test_file_1))

    with open(os.path.join(test_folder, test_file_2), "rb") as f:
        pdf_bytes = f.read()

    # Add pdf to index
    processing_plugin.process_pdf(pdf_bytes, test_file_2)

    # Remove pdf to index
    processing_plugin.remove_pdf(test_file_2)

    # Check remaining entries from search index
    results = vector_db.search_client.search(
        search_text="*",
        filter=f"file eq '{test_file_2}'",
        select=["id"],
        include_total_count=True,
    )
    assert results.get_count() == 0
