from typing import Annotated, List

import pyodbc
from semantic_kernel.functions.kernel_function_decorator import kernel_function

from src.database.service import SQLDatabase
from src.utils import get_logger

logger = get_logger(__name__)


class SQLPlugin:
    """SQLPlugin provides a set of functions to access the database."""

    def __init__(self, db: SQLDatabase) -> None:
        self.db = db

    @kernel_function(name="sql_query", description="Query the database.")
    def sql_query(
        self, query: Annotated[str, "The SQL query"]
    ) -> Annotated[List[pyodbc.Row], "The rows returned"]:
        logger.info("Running database plugin with query: {}".format(query))
        return self.db.query(query)

    @kernel_function(
        name="discover_database",
        description="Qiscover the tables and columns of the database",
    )
    def discover_database(
        self,
    ) -> Annotated[str, "The structure of the Database"]:
        logger.info("Running the discover database tool")
        return self.db.discover()
