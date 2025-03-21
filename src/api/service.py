import json
from contextlib import asynccontextmanager
from typing import Callable, List, Optional

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from semantic_kernel.contents.chat_history import ChatHistory

from ..kernel import Kernel


# Pydantic models for request and response
class Message(BaseModel):
    role: str
    content: str


class ChatCompletionRequest(BaseModel):
    model: str
    messages: List[Message]
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    top_p: Optional[float] = None
    frequency_penalty: Optional[float] = None
    presence_penalty: Optional[float] = None
    stop: Optional[List[str]] = None
    stream: Optional[bool] = False


class ChatCompletionResponse(BaseModel):
    id: str
    object: str
    created: int
    model: str
    choices: List[dict]


kernel: Kernel = Kernel()
# chat_history: Any = None


def serve_app(kernel_setup: Callable, chat_setup: Callable):

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        global kernel
        # global chat_history

        kernel = await kernel_setup()  # noqa
        # chat_history = chat_setup()  # noqa
        yield

    # FastAPI app setup
    app = FastAPI(lifespan=lifespan)
    origins = ["*"]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Mount the static directory to serve static files
    app.mount("/static", StaticFiles(directory="src/api/static"), name="static")

    @app.get("/")
    async def root():
        return {
            "api_version": "1.0",
            "description": "This API provides access to the LLM chat service.",
            "endpoints": {
                "chat": {
                    "method": "POST",
                    "description": "Send a message to the LLM and receive a response.",
                    "url": "/chat",
                },
                "models": {
                    "method": "GET",
                    "description": "Retrieve a list of available models.",
                    "url": "/models",
                },
            },
            "documentation": "/docs",
        }

    @app.get("/favicon.ico")
    async def favicon():
        return FileResponse("src/api/static/JoSlogo.ico")

    async def stream_response(user_message: str, model: str, chat_history: ChatHistory):
        def get_chunk(content: str, stop: bool = False):
            return {
                "id": "chatcmpl-123",
                "object": "chat.completion.chunk",
                "created": 1234567890,
                "model": model,
                "choices": [
                    {
                        "index": 0,
                        "delta": {
                            "role": "assistant",
                            "content": content,
                        },
                        "finish_reason": None if not stop else "stop",
                    }
                ],
            }

        yield f"data: {json.dumps(get_chunk(''))}\n\n"

        response = await kernel.message(
            user_input=user_message, chat_history=chat_history
        )
        yield f"data: {json.dumps(get_chunk(str(response), False))}\n\n"

        # async for response_delta in kernel.stream_message(
        #     user_input=user_message, chat_history=chat_history
        # ):
        #     yield f"data: {json.dumps(get_chunk(str(response_delta), False))}\n\n"

    # FastAPI endpoint for chat completions
    @app.post("/v1/chat/completions", response_model=ChatCompletionResponse)
    @app.post("/chat/completions", response_model=ChatCompletionResponse)
    async def chat_completion(request: ChatCompletionRequest):
        chat_history = parse_chat_history(request)

        user_message = request.messages[-1].content  # Get the last user message
        # chat_history.add_user_message(user_message)

        if request.stream:
            # If streaming is requested, return a StreamingResponse
            return StreamingResponse(
                stream_response(user_message, request.model, chat_history=chat_history),
                media_type="text/event-stream",
            )
        else:
            response_content = await kernel.message(
                user_input=user_message, chat_history=chat_history
            )

        return {
            "id": "chatcmpl-123",
            "object": "chat.completion",
            "created": 1234567890,
            "model": request.model,
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": response_content,
                    },
                    "finish_reason": "stop",
                }
            ],
        }

    # Endpoint to list models
    @app.get("/v1/models")
    @app.get("/models")
    async def list_models():
        return {
            "data": [
                {"id": "JoSQ Financial Copilot [WIP]", "object": "model"},
                # {"id": "gpt-4", "object": "model"},
            ]
        }

    # Run the FastAPI app
    uvicorn.run(app, host="0.0.0.0", port=9998)


def parse_chat_history(request: ChatCompletionRequest) -> ChatHistory:

    chat_history = ChatHistory()
    chat_history.add_system_message(
        "You are an AI financial advisor answering questions about finance, capital market, investments, pensions, insurance and banking products"
        "You have access to a a vector database of ETF key information documents and a SQL database of transactions. The SQL database MUST be discovered in order to understand its structure."
        "From the query given by the user you must understand which tool call to perform (if any)"
        "Every query you make MUST be in the MSSQL language"
    )
    messages = request.messages
    for message in messages[:-1]:
        if message.role == "user":
            chat_history.add_user_message(message.content)
        elif message.role == "assistant":
            chat_history.add_assistant_message(message.content)
        else:
            print(f"Unknown message role {message.role}")

    return chat_history
