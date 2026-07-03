# AIrport — Project Instructions

## State Management

Always use **Redux Toolkit (RTK)** for all state management.  
- Use `createSlice`, `createAsyncThunk`, and `configureStore` from `@reduxjs/toolkit`.  
- Never introduce plain Redux, Zustand, Context API (for global state), or any other state library.  
- RTK Query is preferred for server state / API calls.
