FROM python:3.12-slim

WORKDIR /app

RUN pip install hatch

COPY pyproject.toml .
RUN pip install -e ".[voice]"

COPY . .

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
