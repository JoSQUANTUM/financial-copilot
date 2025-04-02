import sys
import os
import json
import uuid
import argparse

# sys.path.append("./src/")

from ..database import VectorDatabase
from ..utils import CONFIG, get_logger


def create_docs_from_json(json_file, vector_db):
    with open(json_file, "r") as f:
        datas = json.load(f)

    items = []
    for data in datas:
        id = str(uuid.uuid4())
        emb = vector_db.embeddings.embed(input=data["Chunk"], model=vector_db.emb_model)
        rec = {
            "id": id,
            "content": data["Chunk"],
            "title": data["from"],
            "file": data["from"],
            "contentVector": emb.data[0].embedding,
        }
        for key, value in data.items():
            if key not in ["Chunk", "from", "type"]:
                rec[key] = value
        items.append(rec)

    return items


def create_index_from_json(json_file, vector_db):
    # If a search index already exists, delete it:
    index_names = vector_db.list_index_names()
    if vector_db.search_index in index_names:
        vector_db.index_client.delete_index(vector_db.search_index)
        logger.info(
            f"🗑️  Found existing index named '{vector_db.search_index}', and deleted it"
        )

    # create an empty search index
    index_definition = vector_db.create_index_definition()
    vector_db.index_client.create_index(index_definition)

    docs = create_docs_from_json(json_file, vector_db)

    vector_db.search_client.upload_documents(docs)
    logger.info(
        f"➕ Uploaded {len(docs)} documents to '{vector_db.search_index}' index"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Create an index from a json file.")
    parser.add_argument("--file", type=str, required=True, help="Path to the json file")

    args = parser.parse_args()
    logger = get_logger(__name__)

    emb_model = os.environ["EMBEDDINGS_MODEL"]
    index_name = os.environ["AISEARCH_INDEX_NAME"]
    conn_str = os.environ["AIPROJECT_CONNECTION_STRING"]
    model_name = os.environ["DEPLOYMENT_NAME"]

    vector_db = VectorDatabase(
        config=CONFIG,
        search_index=index_name,
        conn_str=conn_str,
        model=model_name,
        emb_model=emb_model,
    )

    if not args.file.lower().endswith(".json"):
        print("Error: The file must be a JSON file.")
    else:
        create_index_from_json(args.file, vector_db)
