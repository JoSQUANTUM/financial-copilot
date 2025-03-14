import os
import tempfile
from typing import Annotated

from semantic_kernel.functions.kernel_function_decorator import kernel_function

from src.database import VectorDatabase
from src.utils import get_logger

logger = get_logger(__name__)


class ProcessingPlugin:
    """ProcessingPlugin provides a set of functions to process documents and add them to the search index."""

    def __init__(self, vector_db: VectorDatabase) -> None:
        self.vector_db = vector_db

    @kernel_function(
        name="process_pdf",
        description="Process a PDF document uploaded by the user and integrate it to the Azure AI Search Index used by the RAG pipeline.",
    )
    def process_pdf(
        self,
        pdf_file: Annotated[
            bytes, "The PDF file uploaded by the user, as a byte stream."
        ],
        filename: Annotated[
            bytes, "The name of the PDF file, with the .pdf extension."
        ],
    ) -> Annotated[str, "The result of the PDF processing."]:
        try:
            # Save the uploaded PDF to a temporary location
            temp_dir = tempfile.gettempdir()
            temp_path = os.path.join(temp_dir, filename)

            with open(temp_path, "wb") as temp_file:
                temp_file.write(pdf_file)

            # Process the file
            self.vector_db.add_to_index_from_pdf(temp_path)

            # Delete the temporary file after processing
            os.remove(temp_path)

            return "PDF successfully processed."

        except Exception as e:
            logger.error(f"An error occurred: {e}")
            return f"Error during PDF processing: {str(e)}"

    @kernel_function(
        name="remove_pdf",
        description="Remove all entries from a PDF document in the Azure AI Search Index.",
    )
    def remove_pdf(
        self,
        filename: Annotated[
            str, "The name of the PDF file to be removed from the Search Index."
        ],
    ) -> Annotated[str, "The result of the PDF removing."]:
        try:
            # Remove all entries from the PDF file
            self.vector_db.remove_from_index(filename)

            return "PDF successfully removed from the Search Index."

        except Exception as e:
            logger.error(f"An error occurred: {e}")
            return f"Error during PDF removing: {str(e)}"
