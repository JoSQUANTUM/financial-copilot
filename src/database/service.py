import pyodbc
import time
from faker import Faker

from .schema import Column, DatabaseSchema, ForeignKey, Table
from .utils import create_table, insert_record, table_exists
from ..utils import get_logger

logger = get_logger(__name__)

# scope = "https://database.windows.net/.default"


# If you have issues connecting, make sure you have the correct driver installed
# ODBC Driver for SQL Server - https://learn.microsoft.com/en-us/sql/connect/odbc/download-odbc-driver-for-sql-server
# connection_string_template = "DRIVER={driver};SERVER=tcp:{server_name}.database.windows.net,1433;DATABASE={database_name}"
connection_string_template = (
    "DRIVER={driver};Server=tcp:{server_name},1433;Database={database_name};"
    "Uid={uname};Pwd={pwd};Encrypt=yes;TrustServerCertificate=no;"
)
driver = "ODBC Driver 18 for SQL Server"


class SQLDatabase:
    def __init__(
        self, server_name: str, database_name: str, uname: str, pwd: str
    ) -> None:
        # token = credential.get_token(scope).token
        self.connection_string = connection_string_template.format(
            driver=driver,
            server_name=server_name,
            database_name=database_name,
            uname=uname,
            pwd=pwd,
        )
        self.conn = self._get_connection()

    def _get_connection(self) -> pyodbc.Connection:
        # see https://learn.microsoft.com/en-us/azure/azure-sql/database/azure-sql-python-quickstart
        # token_bytes = token.encode("UTF-16-LE")
        # token_struct = struct.pack(f"<I{len(token_bytes)}s", len(token_bytes), token_bytes)
        # SQL_COPT_SS_ACCESS_TOKEN = (
        #     1256  # This connection option is defined by microsoft in msodbcsql.h
        # )
        max_retries = 5
        for i in range(max_retries):
            try:
                return pyodbc.connect(self.connection_string, timeout=10)
            except pyodbc.Error:
                logger.debug(
                    "Failed to connect. Retrying in 5 seconds ({}/{} attempts).".format(
                        i + 1, max_retries
                    )
                )
                time.sleep(5)
        raise ConnectionError(
            "Failed to connect to the database after multiple attempts."
        )

    def setup(self) -> None:
        """
        Set up the database by creating the table and inserting fake records.
        """
        logger.debug("Setting up the database.")
        # Create a cursor object to execute SQL queries
        self.cursor = self.conn.cursor()

        if table_exists(self.cursor):
            # skip if table already exists
            return

        logger.debug("Creating table.")
        create_table(self.cursor)

        # Create Faker object
        fake = Faker()

        logger.debug("Generating and inserting records.")
        # Generate and insert 1,000 fake records
        for i in range(1000):
            insert_record(self.cursor, i, fake)

        # Commit the changes and close the connection
        self.conn.commit()

        logger.debug("Database setup completed.")

    def discover(self) -> DatabaseSchema:
        """
        Discovers the structure of the attached Database
        """
        logger.debug("Discovering attached Database")
        cursor = self.conn.cursor()

        # Get list of tables
        cursor.execute(
            """
            SELECT TABLE_NAME
            FROM INFORMATION_SCHEMA.TABLES
            WHERE TABLE_TYPE = 'BASE TABLE'
            """
        )
        tables = [row[0] for row in cursor.fetchall()]

        # Get foreign key relationships
        cursor.execute(
            """
            SELECT
                fk.name AS FK_name,
                tp.name AS parent_table,
                tr.name AS referenced_table
            FROM
                sys.foreign_keys AS fk
            INNER JOIN
                sys.tables AS tp ON fk.parent_object_id = tp.object_id
            INNER JOIN
                sys.tables AS tr ON fk.referenced_object_id = tr.object_id
            """
        )
        foreign_keys = cursor.fetchall()

        # Retrieve columns and primary keys for each table
        table_columns = {}
        for table in tables:
            cursor.execute(
                """
                SELECT COLUMN_NAME, DATA_TYPE
                FROM INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_NAME = ?
                """,
                (table,),
            )
            columns = cursor.fetchall()
            table_columns[table] = [(row[0], row[1]) for row in columns]

        # Retrieve primary keys for each table
        primary_keys = {}
        for table in tables:
            cursor.execute(
                """
                SELECT kcu.COLUMN_NAME
                FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS AS tc
                JOIN INFORMATION_SCHEMA.KEY_COLUMN_USAGE AS kcu
                ON tc.CONSTRAINT_TYPE = 'PRIMARY KEY'
                AND tc.CONSTRAINT_NAME = kcu.CONSTRAINT_NAME
                WHERE kcu.TABLE_NAME = ?
                """,
                (table,),
            )
            pk_columns = cursor.fetchall()
            primary_keys[table] = [row[0] for row in pk_columns]

            # Create an instance of DatabaseSchema
            database_schema = DatabaseSchema()

            for table, columns in table_columns.items():
                # Create a Table instance
                table_instance = Table(name=table)

                for column in columns:
                    column_name = column[0]
                    data_type = column[1]
                    is_primary_key = (
                        column_name in primary_keys[table]
                        if table in primary_keys
                        else False
                    )

                    # Create a Column instance and add it to the table
                    column_instance = Column(
                        name=column_name,
                        data_type=data_type,
                        is_primary_key=is_primary_key,
                    )
                    table_instance.columns.append(column_instance)

                # Add the populated Table instance to the DatabaseSchema
                database_schema.tables.append(table_instance)

        # Populate foreign keys
        for fk in foreign_keys:
            fk_name = fk.FK_name
            parent_table = fk.parent_table
            referenced_table = fk.referenced_table

            # Find the corresponding table instance and add the foreign key
            for table in database_schema.tables:
                if table.name == parent_table:
                    foreign_key_instance = ForeignKey(
                        name=fk_name,
                        parent_table=parent_table,
                        referenced_table=referenced_table,
                    )
                    table.foreign_keys.append(foreign_key_instance)

        logger.debug(
            "Successfully discovered attached database: {}".format(database_schema)
        )

        return database_schema

    def query(self, query: str) -> list[pyodbc.Row]:
        """
        Query the database with the given SQL query.
        """
        cursor = self.conn.cursor()
        try:
            logger.debug("Querying database with: {}.".format(query))
            cursor.execute(query)
            result = cursor.fetchall()
            logger.debug("Successfully queried database: {}.".format(result))
        except Exception as ex:
            try:
                logger.debug(
                    "Error querying database: {}. Trying to reconnect.".format(ex)
                )
                self.conn = self._get_connection()
                cursor = self.conn.cursor()
                cursor.execute(query)
                result = cursor.fetchall()
                logger.debug("Successfully queried database: {}.".format(result))
            except Exception as ex:
                logger.error("Error querying database: {}.".format(ex))
                return "No Result Found"
        finally:
            cursor.close()

        return result

    def close(self):
        self.cursor.close()
        self.conn.close()
