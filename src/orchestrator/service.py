from semantic_kernel.contents.chat_history import ChatHistory

from ..kernel import Kernel
from ..utils import get_logger

logger = get_logger(__name__)


class Orchestrator:
    def __init__(self, kernel: Kernel) -> None:
        self.kernel = kernel

    async def run(self, chat_history: ChatHistory) -> None:
        """
        Run the orchestrator
        """
        while True:
            try:
                user_input = input("User > ")

                # Terminate the loop if the user says "exit"
                if user_input == "exit":
                    break

                response = await self.kernel.message(
                    user_input=user_input, chat_history=chat_history
                )

                print("Assistant > " + response)
            except Exception as e:
                logger.error("An exception occurred: {}".format(e))
                raise e
