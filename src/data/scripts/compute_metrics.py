from fastapi import FastAPI

app = FastAPI()

@app.get("/")
def home():
    return {"message": "Graphene Trace API is running."}