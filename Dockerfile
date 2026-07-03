FROM python:3.11

ENV PYTHONUNBUFFERED=1
# Ensure Streamlit doesn't try to open a browser window
ENV STREAMLIT_SERVER_HEADLESS=true 

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Use CMD in shell form to support the $PORT variable
CMD streamlit run app.py --server.port ${PORT:-8505} --server.address 0.0.0.0
