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
    """Represents an item in our tiny inventory."""

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
# In-memory "database"
###############################################################################

# This dictionary will act as our storage. Keys are item IDs, values are Item
# instances. **Not** suitable for production usage!
items_db: Dict[int, Item] = {}

###############################################################################
# FastAPI application instance
###############################################################################

app = FastAPI(
    title="Example FastAPI Server",
    version="0.1.0",
    description="A simple FastAPI server with basic CRUD operations.",
)

###############################################################################
# Event handlers
###############################################################################


@app.on_event("startup")
async def startup_event() -> None:
    """Initialize application state before the first request is processed."""

    # Populate the in-memory DB with a sample item so list endpoint isn't empty.
    sample_item = Item(
        id=1,
        name="Sample Item",
        description="This item is automatically added on startup.",
        price=9.99,
        tax=0.8,
    )
    items_db[sample_item.id] = sample_item
    print("🚀 FastAPI application started and sample item inserted.")


@app.on_event("shutdown")
async def shutdown_event() -> None:
    """Cleanup logic executed when the application is shutting down."""

    items_db.clear()
    print("👋 FastAPI application is shutting down. DB cleared.")

###############################################################################
# Custom exception handler
###############################################################################


class ItemNotFoundError(HTTPException):
    """Custom exception raised when an item is not found."""


@app.exception_handler(ItemNotFoundError)
async def item_not_found_handler(request: Request, exc: ItemNotFoundError) -> Response:
    """Return a JSON 404 response with a custom error structure."""

    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={"error": exc.detail, "item_id": exc.headers.get("item_id")},
    )

###############################################################################
# Routes
###############################################################################


@app.get("/", summary="Root endpoint", tags=["Misc"])
async def read_root() -> Dict[str, str]:
    """Return a friendly greeting."""

    return {"message": "Hello, FastAPI World!"}


@app.get("/health", summary="Health check", tags=["Misc"])
async def health_check() -> Dict[str, str]:
    """Simple health check endpoint."""

    return {"status": "ok"}


# ------------------------- Item CRUD operations -----------------------------


@app.get("/items", response_model=List[Item], tags=["Items"])
async def list_items() -> List[Item]:
    """Retrieve **all** items from the database."""

    return list(items_db.values())


@app.get("/items/{item_id}", response_model=Item, tags=["Items"])
async def get_item(item_id: int) -> Item:
    """Retrieve a single item by its ID."""

    if item_id not in items_db:
        raise ItemNotFoundError(
            detail=f"Item with ID {item_id} was not found.", headers={"item_id": str(item_id)}
        )
    return items_db[item_id]


@app.post(
    "/items",
    response_model=Item,
    status_code=status.HTTP_201_CREATED,
    tags=["Items"],
)
async def create_item(item: Item) -> Item:
    """Add a new item to the database."""

    if item.id in items_db:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"An item with ID {item.id} already exists.",
        )
    items_db[item.id] = item
    return item


@app.put("/items/{item_id}", response_model=Item, tags=["Items"])
async def update_item(item_id: int, updated_item: Item) -> Item:
    """Update an existing item identified by *item_id*."""

    if item_id not in items_db:
        raise ItemNotFoundError(
            detail=f"Item with ID {item_id} was not found.", headers={"item_id": str(item_id)}
        )
    if item_id != updated_item.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Path ID and item ID mismatch.",
        )
    items_db[item_id] = updated_item
    return updated_item


@app.delete(
    "/items/{item_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    tags=["Items"],
)
async def delete_item(item_id: int) -> None:
    """Remove an item from the database."""

    if item_id not in items_db:
        raise ItemNotFoundError(
            detail=f"Item with ID {item_id} was not found.", headers={"item_id": str(item_id)}
        )
    del items_db[item_id]


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