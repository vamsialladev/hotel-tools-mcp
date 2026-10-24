FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt pyproject.toml ./
COPY src/ src/
COPY data/ data/
RUN pip install --no-cache-dir -r requirements.txt && pip install --no-cache-dir --no-deps .
# A stdio MCP server: run with -i and pass HOTEL_MCP_API_KEY; mount .hotel-mcp/ for the keys file and logs.
ENV HOTEL_MCP_DATA_DIR=/app/data HOTEL_MCP_RUNTIME_DIR=/app/.hotel-mcp
ENTRYPOINT ["hotel-tools-mcp"]
