# ruff: noqa: ANN201, ANN001

import logging
import pathlib
import sys


# Set "./assets" as the path where assets are stored, resolving the absolute path:
ASSET_PATH = pathlib.Path(__file__).parent.parent.parent.resolve() / "assets"
TEMPLATE_PATH = ASSET_PATH / "templates"

CONFIG = {
    "template": "text_extraction.prompty",
    "separator": "|||",
    "max_chunk_size": 500,
    "top_k": 5,
    "rag_entities": ["product_name", "manufacturer", "risk_class"],
}


SYSTEM_MESSAGE = """You are an AI financial advisor answering questions about finance, capital market, investments, pensions, insurance and banking products
        You have access to a a vector database of ETF key information documents and a SQL database of transactions. The SQL database must be discovered in order to understand its structure.
        From the query given by the user you must understand which tool call to perform (if any)
        Every query you make MUST be in the MSSQL language"""


logging.basicConfig(
    filename="app.log",
    format="[%(asctime)s - %(name)s:%(lineno)d - %(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    level=logging.INFO,
)

# Configure an root app logger that prints info level logs to stdout
logger = logging.getLogger("app")
logger.setLevel(logging.DEBUG)
logger.addHandler(logging.StreamHandler(stream=sys.stdout))


# Returns a module-specific logger, inheriting from the root app logger
def get_logger(module_name):
    return logging.getLogger(f"app.{module_name}")
