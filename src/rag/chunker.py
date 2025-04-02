import io
import base64
import json
from pathlib import Path
from pdf2image import convert_from_path

from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential
from azure.ai.inference.prompts import PromptTemplate

from src.utils import TEMPLATE_PATH


class TextChunker:

    def __init__(self, config: dict, conn_str: str, model: str):
        self.config = config
        self.model = model

        self.project = AIProjectClient.from_connection_string(
            conn_str=conn_str,
            credential=DefaultAzureCredential(),
        )

        # create a chat client we can use for testing
        self.chat = self.project.inference.get_chat_completions_client()

    def _token_len(self, chunk):
        return len(chunk.split())

    def recursive_chunking(self, texts):
        separator = self.config["separator"]
        max_chunk_size = self.config["max_chunk_size"]
        chunks, current_chunk = [], ""

        for text in texts:
            entries = text.split(separator)

            for entry in entries:
                if not current_chunk:
                    current_chunk = entry
                    continue
                if self._token_len(current_chunk + " " + entry) > max_chunk_size:
                    chunks.append(current_chunk)
                    current_chunk = entry
                else:
                    current_chunk += "\n" + entry

        if current_chunk:
            chunks.append(current_chunk)

        return chunks

    def extract_images_from_pdf(self, input_path):
        return convert_from_path(input_path)

    def chunk_from_pdf(self, input_path):
        pages = self.extract_images_from_pdf(input_path)

        prompt_template = PromptTemplate.from_prompty(
            Path(TEMPLATE_PATH) / self.config["template"]
        )
        system_message = prompt_template.create_messages(
            separator=self.config["separator"]
        )

        texts, metadatas = [], {}
        for page in pages:
            img_byte_arr = io.BytesIO()
            page.save(img_byte_arr, format="PNG")  # Change format if needed
            image_data = base64.b64encode(img_byte_arr.getvalue()).decode("utf-8")

            # Convert to Data URL format
            image_format = "png"
            data_url = f"data:image/{image_format};base64,{image_data}"

            # Create the multimodal input
            multimodal_input = {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            }

            response = self.chat.complete(
                model=self.model,
                messages=system_message + [multimodal_input],
            )

            try:
                json_output = json.loads(response.choices[0].message.content)
                texts.append(json_output.pop("content"))

                for k, v in json_output.items():
                    metadatas[k] = metadatas.get(k, v) or v

            except:
                texts.append(response.choices[0].message.content)
                print(f"Invalid JSON: {json_output}")

        return self.recursive_chunking(texts), metadatas
