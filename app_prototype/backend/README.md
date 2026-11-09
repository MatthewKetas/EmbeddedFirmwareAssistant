# Local Python backend

See the [local setup instructions](../README.md) for starting the browser and backend.

- `GET /api/boards` lists the boards in the SQLite knowledge map.
- `POST /api/boards` accepts a multipart CMSIS-SVD file and adds its device and board records.
- `POST /api/chat` takes a board ID, prompt, and conversation history. It adds board and indexed document context and streams the local Lemonade reply as newline-delimited JSON.
- `GET /api/health` reports the API status and configured model.
- `POST /api/index-svd` and `POST /api/registers/calculate` provide the standalone parser and bitfield calculator.

The optional `desktop_main.py` runner opens the local Vite frontend in PyWebView.
