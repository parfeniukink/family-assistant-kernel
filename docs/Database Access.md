This document explains how the database layer works in this project, using ContextVars and the CQS (Command/Query Separation) pattern.

# The Problem with Async Code

aka REASONING: How do we make sure each request uses its OWN session?

```python
# In synchronous code, things happen one at a time:
def create_cost():
    session = get_session()
    session.add(cost)
    session.commit()
    session.close()
```

```python
# In async code, multiple things can happen "simultaneously"
async def handle_request_1():
    session = get_session()  # Gets session A
    await session.add(cost)  # Pauses here...
    # While paused, request_2 runs!
    await session.commit()

async def handle_request_2():
    session = get_session()  # Gets session B? Or A?
    await session.add(income)
    await session.commit()
```

## Solution: `ContextVar`

Python's `ContextVar` is like a **thread-local variable for async code**. Each async "task" gets its own isolated copy.
ContextVar keeps values isolated between concurrent async operations.

```python
from contextvars import ContextVar

# Create a variable that's isolated per async task
current_user: ContextVar[str] = ContextVar("current_user", default="anonymous")

async def handle_request_john():
    current_user.set("john")
    await do_something()
    print(current_user.get())  # Prints "john"

async def handle_request_mary():
    current_user.set("mary")
    await do_something()
    print(current_user.get())  # Prints "mary"

# Even if these run concurrently, each sees its own value!
await asyncio.gather(
    handle_request_john(),
    handle_request_mary()
)
```

## Using ContextVar for Database Sessions Management

The CQS layer uses ContextVar to store the current transaction's session.
Each request has its own isolated ContextVar state.

```python
CTX_CQS_COMMAND_SESSION: ContextVar[AsyncSession | None] = ContextVar(
    "cqs command session", default=None
)
```

### How it works?

```
Request 1 (John)              Request 2 (Mary)
─────────────────            ─────────────────
ContextVar = None            ContextVar = None
     │                            │
transaction()                transaction()
     │                            │
ContextVar = Session_A       ContextVar = Session_B
     │                            │
repo.add_cost()              repo.add_income()
  └── uses Session_A           └── uses Session_B
     │                            │
commit                       commit
```

# The Command/Query Separation (CQS)

The architecture separates **reads** and **writes**:

## Writes (Command) - Need Transaction

```python
# Multiple writes should share ONE session (for atomicity)
async with database.transaction() as session:
    await repo.add_cost(cost1)      # Uses session from ContextVar
    await repo.add_cost(cost2)      # Same session
    await repo.update_equity(...)   # Same session
    # All succeed or all fail together (atomic)
```

## Reads (Query) - Independent

```python
# Reads can each have their own session (for concurrency)
costs = await repo.get_costs()     # Creates fresh session, closes it
incomes = await repo.get_incomes() # Creates another fresh session
# These can run concurrently without issues
```

# How the Repository Accesses Sessions

## The Command Descriptor (for writes)

```python
class Command:
    def __get__(self, instance, owner):
        # Get session from ContextVar (set by transaction())
        session = CTX_CQS_COMMAND_SESSION.get()
        if not session:
            raise ValueError("Must be inside database.transaction()!")
        return self  # Returns self with session attached

# Usage in repository:
class TransactionRepository(Repository):
    async def add_cost(self, candidate):
        # self.command.session gets session from ContextVar
        self.command.session.add(candidate)
        return candidate
```

## The Query Descriptor (for reads)

```python
class Query:
    @property
    @asynccontextmanager
    async def session(self):
        # Creates NEW session each time (doesn't use ContextVar)
        session = session_factory()
        try:
            yield session
        finally:
            await session.close()

# Usage in repository:
class TransactionRepository(Repository):
    async def get_costs(self):
        async with self.query.session as session:  # Fresh session
            result = await session.execute(select(Cost))
            return result.scalars().all()
```

# The Transaction Context Manager

```python
@asynccontextmanager
async def transaction():
    # 1. Create a new session
    session = session_factory()

    # 2. Store it in ContextVar (so Command can find it)
    token = CTX_CQS_COMMAND_SESSION.set(session)

    try:
        # 3. Start database transaction
        async with session.begin():
            yield session  # Your code runs here
        # 4. Auto-commit on success

    except IntegrityError:
        # 5. Auto-rollback on error
        raise

    finally:
        # 6. Clean up
        await session.close()
        CTX_CQS_COMMAND_SESSION.reset(token)  # Restore previous state
```

## Why Token-Based Reset?

The `token` from `ContextVar.set()` allows you to **restore the previous value**:

```python
# Without token:
CTX_VAR.set("A")
CTX_VAR.set("B")
# How do you get back to "A"? You can't easily.

# With token:
token_a = CTX_VAR.set("A")
token_b = CTX_VAR.set("B")
CTX_VAR.reset(token_b)  # Back to "A"
CTX_VAR.reset(token_a)  # Back to None (default)
```

This matters for **nested transactions** (even if you don't use them often):

```python
async with database.transaction():  # Sets session_A, saves token_A
    await repo.add_cost(...)

    async with database.transaction():  # Sets session_B, saves token_B
        await repo.add_income(...)
    # reset(token_B) -> ContextVar back to session_A

    await repo.add_cost(...)  # Uses session_A again
# reset(token_A) -> ContextVar back to None
```

---

# Visual Description

```
┌──────────────────────────────────────────────────────────────────────┐
│                         ENTRYPOINT                                   │
│                                                                      │
│   async with database.transaction() as session:                      │
│       await repo.add_cost(cost)                                      │
│       await repo.update_equity(currency_id, value)                   │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────────────┐
│                    TRANSACTION CONTEXT MANAGER                       │
│                                                                      │
│   1. session = session_factory()      <- Create session              │
│   2. token = CTX_VAR.set(session)     <- Store in ContextVar         │
│   3. session.begin()                  <- Start transaction           │
│   4. yield session                    <- Your code runs              │
│   5. commit (or rollback on error)    <- End transaction             │
│   6. session.close()                  <- Close session               │
│   7. CTX_VAR.reset(token)             <- Restore ContextVar          │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────────────┐
│                         REPOSITORY                                   │
│                                                                      │
│   async def add_cost(self, candidate):                               │
│       self.command.session.add(candidate)                            │
│              │                                                       │
│              └── Command.__get__() reads from CTX_VAR                │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────────────┐
│                         CONTEXT VAR                                  │
│                                                                      │
│   Request 1: CTX_VAR = Session_A     (isolated)                      │
│   Request 2: CTX_VAR = Session_B     (isolated)                      │
│   Request 3: CTX_VAR = Session_C     (isolated)                      │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────────────┐
│                      ENGINE (Shared, Cached)                         │
│                                                                      │
│   @lru_cache                                                         │
│   def engine_factory():                                              │
│       return create_async_engine(DATABASE_URL)                       │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
                    ┌─────────────────┐
                    │   PostgreSQL    │
                    └─────────────────┘
```
