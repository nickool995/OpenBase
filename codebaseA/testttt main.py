


"""main.py
A more complete FastAPI application example.

This server includes:
1. A simple in-memory database for "items".
2. Full CRUD endpoints (create, read all, read one, update, delete).
3. Health-check endpoint at /health.
4. Application startup and shutdown event handlers.
5. A custom exception handler for item not found errors.

Although it is still intentionally **simple** (no persistence layer, auth, etc.),
it demonstrates common FastAPI patterns while remaining easy to read.
"""

from typing import Dict, List, Optional

from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

###############################################################################
# Pydantic models
###############################################################################


class Item(BaseModel):
    """Pydantic model representing an item in the inventory."""

    id: int = Field(..., description="Unique identifier for the item")
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=300)
    price: float = Field(..., gt=0)
    tax: Optional[float] = Field(None, ge=0)

    class Config:
        schema_extra = {
            "example": {
                "id": 1,
                "name": "Awesome Widget",
                "description": "An awesome widget you definitely need!",
                "price": 19.99,
                "tax": 1.6,
            }
        }
        

###############################################################################
# Custom exception handler
###############################################################################


class ItemNotFoundError(HTTPException):
    """Custom exception raised when an item is not found."""


@app.exception_handler(ItemNotFoundError)
async def item_not_found_handler(request: Request, exc: ItemNotFoundError) -> JSONResponse:
    """Handles `ItemNotFoundError` exceptions, returning a custom JSON 404 response.

    Args:
        request (Request): The incoming request that caused the exception.
        exc (ItemNotFoundError): The exception instance raised.

    Returns:
        JSONResponse: A JSON response with status code 404 and error details.
    """

    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={"error": exc.detail, "item_id": exc.headers.get("item_id")},
    )


###############################################################################
# Repository Layer (Data Access)
###############################################################################


class ItemRepository:
    """
    Manages direct interaction with the in-memory "database" for Item objects.
    This acts as a simple repository pattern.
    """

    def __init__(self):
        self._db: Dict[int, Item] = {}

    def get_all(self) -> List[Item]:
        """Retrieves all items from the database."""
        return list(self._db.values())

    def get_by_id(self, item_id: int) -> Item:
        """
        Retrieves an item by its ID.
        Raises ItemNotFoundError if the item is not found.
        """
        if item_id not in self._db:
            raise ItemNotFoundError(
                detail=f"Item with ID {item_id} was not found.", headers={"item_id": str(item_id)}
            )
        return self._db[item_id]

    def add(self, item: Item) -> None:
        """Adds a new item to the database."""
        self._db[item.id] = item

    def update(self, item: Item) -> None:
        """Updates an existing item in the database."""
        self._db[item.id] = item

    def delete(self, item_id: int) -> None:
        """Deletes an item from the database by ID."""
        if item_id not in self._db:
            raise ItemNotFoundError(
                detail=f"Item with ID {item_id} was not found.", headers={"item_id": str(item_id)}
            )
        del self._db[item_id]

    def clear(self) -> None:
        """Clears all items from the database."""
        self._db.clear()


###############################################################################
# Service Layer (Business Logic)
###############################################################################


class ItemService:
    """
    Handles business logic related to Item operations, using an ItemRepository
    for data access.
    """

    def __init__(self, repository: ItemRepository):
        self._repository = repository

    def get_all_items(self) -> List[Item]:
        """Retrieves all items."""
        return self._repository.get_all()

    def get_item_by_id(self, item_id: int) -> Item:
        """Retrieves a single item by ID."""
        return self._repository.get_by_id(item_id)

    def create_item(self, item: Item) -> Item:
        """
        Creates a new item.
        Raises HTTPException if an item with the same ID already exists.
        """
        try:
            self._repository.get_by_id(item.id)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"An item with ID {item.id} already exists.",
            )
        except ItemNotFoundError:
            self._repository.add(item)
            return item

    def update_item(self, item_id: int, updated_item: Item) -> Item:
        """
        Updates an existing item.
        Raises ItemNotFoundError if the item to update is not found.
        Raises HTTPException if path ID and item body ID mismatch.
        """
        self._repository.get_by_id(item_id)  # Ensure item exists
        if item_id != updated_item.id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Path ID and item ID mismatch.",
            )
        self._repository.update(updated_item)
        return updated_item

    def delete_item(self, item_id: int) -> None:
        """
        Deletes an item by ID.
        Raises ItemNotFoundError if the item is not found.
        """
        self._repository.delete(item_id)


###############################################################################
# FastAPI application instance and Dependency Setup
###############################################################################

app = FastAPI(
    title="Example FastAPI Server",
    version="0.1.0",
    description="A simple FastAPI server with basic CRUD operations.",
)

# Instantiate repository and service globally for this single-file example.
# In a larger application, these would typically be managed via FastAPI's
# dependency injection system.
item_repository = ItemRepository()
item_service = ItemService(item_repository)


###############################################################################
# Event handlers
###############################################################################


@app.on_event("startup")
async def startup_event() -> None:
    """Initializes application state and populates the in-memory database.

    This function is called when the FastAPI application starts up.
    It adds a sample item to the `items_db` to ensure the list endpoint is not empty
    on initial access.
    """

    # Populate the in-memory DB with a sample item so list endpoint isn't empty.
    sample_item: Item = Item(
        id=1,
        name="Sample Item",
        description="This item is automatically added on startup.",
        price=9.99,
        tax=0.8,
    )
    item_repository.add(sample_item)
    print("🚀 FastAPI application started and sample item inserted.")


@app.on_event("shutdown")
async def shutdown_event() -> None:
    """Cleans up application state when the application is shutting down.

    This function is called when the FastAPI application shuts down.
    It clears the `items_db` to release memory and ensure a clean state.
    """

    item_repository.clear()
    print("👋 FastAPI application is shutting down. DB cleared.")


###############################################################################
# Routes (Controller Layer)
###############################################################################


@app.get("/", summary="Root endpoint", tags=["Misc"])
async def read_root() -> Dict[str, str]:
    """Returns a friendly greeting message from the root endpoint.

    Returns:
        Dict[str, str]: A dictionary containing a welcome message.
    """

    return {"message": "Hello, FastAPI World!"}


@app.get("/health", summary="Health check", tags=["Misc"])
async def health_check() -> Dict[str, str]:
    """Provides a simple health check endpoint for the application.

    Returns:
        Dict[str, str]: A dictionary indicating the application's status.
    """

    return {"status": "ok"}


# ------------------------- Item CRUD operations -----------------------------


@app.get("/items", response_model=List[Item], tags=["Items"])
async def list_items() -> List[Item]:
    """Retrieves all items currently stored in the in-memory database.

    Returns:
        List[Item]: A list of all `Item` objects.
    """

    return item_service.get_all_items()


@app.get("/items/{item_id}", response_model=Item, tags=["Items"])
async def get_item(item_id: int) -> Item:
    """Retrieves a single item from the database by its unique ID.

    Args:
        item_id (int): The unique identifier of the item to retrieve.

    Returns:
        Item: The `Item` object corresponding to the given ID.

    Raises:
        ItemNotFoundError: If no item with the specified `item_id` is found.
    """

    return item_service.get_item_by_id(item_id)


@app.post(
    "/items",
    response_model=Item,
    status_code=status.HTTP_201_CREATED,
    tags=["Items"],
)
async def create_item(item: Item) -> Item:
    """Adds a new item to the in-memory database.

    Args:
        item (Item): The `Item` object to be created. The `id` must be unique.

    Returns:
        Item: The newly created `Item` object.

    Raises:
        HTTPException: If an item with the same ID already exists (400 Bad Request).
    """

    return item_service.create_item(item)


@app.put("/items/{item_id}", response_model=Item, tags=["Items"])
async def update_item(item_id: int, updated_item: Item) -> Item:
    """Updates an existing item in the database identified by its ID.

    The `item_id` in the path must match the `id` in the `updated_item` body.

    Args:
        item_id (int): The unique identifier of the item to update.
        updated_item (Item): The `Item` object with updated details.

    Returns:
        Item: The updated `Item` object.

    Raises:
        ItemNotFoundError: If no item with the specified `item_id` is found.
        HTTPException: If the path `item_id` does not match the `id` in the request body (400 Bad Request).
    """

    return item_service.update_item(item_id, updated_item)


@app.delete(
    "/items/{item_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    tags=["Items"],
)
async def delete_item(item_id: int) -> None:
    """Removes an item from the in-memory database by its unique ID.

    Args:
        item_id (int): The unique identifier of the item to delete.

    Raises:
        ItemNotFoundError: If no item with the specified `item_id` is found.
    """

    item_service.delete_item(item_id)


###############################################################################
# Application entry-point helper (for `python main.py`)
###############################################################################


if __name__ == "__main__":
    import uvicorn

    # The `reload=True` flag watches for file changes and restarts the
    # development server automatically. Disable it in production.
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info",
    )
