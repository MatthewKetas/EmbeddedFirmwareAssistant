# Hardware Copilot

Run the Stitch frontend and the Python firmware assistant locally. Use Node.js 22.12 or newer and the Python environment you use for `RAG/rag.py`.

1. Start Lemonade on port 13305 with `Qwen3.6-35B-A3B-GGUF` available. If Lemonade is already running, use that instance.
2. From the repository root, start the Python API.

   ```sh
   .venv/bin/python -m pip install -r app_prototype/backend/requirements.txt
   .venv/bin/python -m uvicorn app_prototype.backend.app:app --host 127.0.0.1 --port 8000
   ```

3. In a second terminal, from the repository root, start the frontend.

   ```sh
   cd app_prototype
   npm install
   npm run dev
   ```

4. Open [Hardware Copilot on localhost](http://127.0.0.1:3000). Pick a project or create a named project for any installed board. Use **New chat** for a separate conversation and the **+** by **Projects** to import a CMSIS-SVD `.xml` or `.svd` file.

Projects and conversations are kept in the open page and reset on reload. Boards and their register definitions are saved in the existing SQLite board database and appear again the next time you open the app.

The app also searches the existing Qdrant library when it contains indexed material. To add datasheets or code to that library, stop the Python API, run `RAG/rag.py` and use its existing `/add` or `/code` commands, then quit the terminal assistant and restart the API. Both use the same local index, which can be opened by one process at a time. Datasheet and code search also require Lemonade’s `Qwen3-Embedding-8B-GGUF` model.
