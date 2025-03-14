import os
from typing import AsyncGenerator

from azure.ai.projects.aio import AIProjectClient
from azure.identity import DefaultAzureCredential
from semantic_kernel import Kernel as SemanticKernel
from semantic_kernel.connectors.ai.azure_ai_inference import (
    AzureAIInferenceChatCompletion,
)
from semantic_kernel.connectors.ai.azure_ai_inference.azure_ai_inference_prompt_execution_settings import (
    AzureAIInferenceChatPromptExecutionSettings,
)
from semantic_kernel.connectors.ai.function_choice_behavior import (
    FunctionChoiceBehavior,
)

# from semantic_kernel.connectors.ai.prompt_execution_settings import (
#     PromptExecutionSettings,
# )
from semantic_kernel.contents import AuthorRole, FinishReason
from semantic_kernel.contents.chat_history import ChatHistory
from semantic_kernel.functions import KernelArguments

from src.database.vector_db import VectorDatabase

from ..database import SQLDatabase, VectorDatabase
from ..utils import get_logger

logger = get_logger(__name__)


# see https://learn.microsoft.com/en-us/azure/ai-services/openai/how-to/managed-identity
scope = "https://cognitiveservices.azure.com/.default"


class Kernel:
    def __init__(self):
        self.kernel = None
        self.project = None
        self.model_name = None
        self.chat = None
        self.chat_completion = None
        self.execution_settings = None

    @classmethod
    async def create(
        cls,
        database_service: SQLDatabase,
        credential: DefaultAzureCredential,
        conn_str: str,
        model_name: str,
        vector_db: VectorDatabase,
    ):
        self = Kernel()

        self.model_name = model_name

        # Create a new kernel
        self.kernel = SemanticKernel()

        # Connect to the AI Project
        self.project = AIProjectClient.from_connection_string(
            conn_str=conn_str,
            credential=credential,  # type: ignore[arg-type]
        )

        # create a chat client
        self.chat = await self.project.inference.get_chat_completions_client()

        self.chat_completion = AzureAIInferenceChatCompletion(
            ai_model_id=self.model_name, client=self.chat
        )
        self.chat_completion.client._model = self.model_name

        # Add Azure chat completion to Kernel
        self.kernel.add_service(self.chat_completion)

        # Add plugins located under /plugins folder
        parent_directory = os.path.join(__file__, "../../")
        init_args = {
            "SQLPlugin": {
                "db": database_service,
            },
            "nlp_to_sql": {
                "schema": str(database_service.discover()),
            },
            "RAGPlugin": {"vector_db": vector_db},
            "ProcessingPlugin": {"vector_db": vector_db},
        }
        self.kernel.add_plugin(
            parent_directory=parent_directory,
            plugin_name="plugins",
            class_init_arguments=init_args,
        )

        self.execution_settings = AzureAIInferenceChatPromptExecutionSettings(
            # PromptExecutionSettings(
            function_choice_behavior=FunctionChoiceBehavior.Auto(
                # enable_kernel_functions=True,
                # auto_invoke=True,
                # max_auto_invoke_attempts=10,
                filters={
                    "included_functions": [
                        "plugins-rag_retrieve",
                        "plugins-discover_database",
                        "plugins-nlp_to_sql",
                        "plugins-sql_query",
                    ],
                },
            ),
        )
        return self

    async def message(self, user_input: str, chat_history: ChatHistory) -> str:
        """
        Send a message to the kernel and get a response.
        """
        chat_history.add_user_message(user_input)
        chat_history_count = len(chat_history)
        response = await self.chat_completion.get_chat_message_contents(
            chat_history=chat_history,
            settings=self.execution_settings,
            kernel=self.kernel,
            arguments=KernelArguments(settings=self.execution_settings),
            model=self.model_name,
        )

        # print assistant/tool actions
        for message in chat_history[chat_history_count:]:
            if message.role == AuthorRole.TOOL:
                for item in message.items:
                    logger.info(
                        "Tool {} called and returned {}".format(item.name, item.result)
                    )
            elif (
                message.role == AuthorRole.ASSISTANT
                and message.finish_reason == FinishReason.TOOL_CALLS
            ):
                for item in message.items:
                    logger.info(
                        "Tool {} needs to be called with parameters {}".format(
                            item.name, item.arguments
                        )
                    )

        return str(response[0])


    async def close(self):
        await self.project.close()

    async def stream_message(
        self, user_input: str, chat_history: ChatHistory
    ) -> AsyncGenerator[str, None]:
        """
        Send a message to the kernel and get a streaming response.
        """
        chat_history.add_user_message(user_input)
        len(chat_history)
        response = self.chat_completion.get_streaming_chat_message_contents(
            chat_history=chat_history,
            settings=self.execution_settings,
            kernel=self.kernel,
            arguments=KernelArguments(settings=self.execution_settings),
            model=self.model_name,
        )

        async for chunk in response:
            print(chunk)
            yield str(chunk[0]) + "\n"

