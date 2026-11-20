FROM python:3.12-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 MPLCONFIGDIR=/tmp/mpl PORT=8080 LESSON=monomials.mth
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8080
# какой урок грузить — переменная LESSON (по умолчанию monomials.mth)
CMD ["sh", "-c", "python server.py ${LESSON}"]
