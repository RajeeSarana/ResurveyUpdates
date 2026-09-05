import uvicorn

if __name__ == "__main__":
    print("=" * 65)
    print(" RESURVEY UPDATES - FIELD PROGRESS MONITORING PORTAL")
    print("=" * 65)
    print("Starting local server at: http://127.0.0.1:8000")
    print("Open your browser and navigate to: http://127.0.0.1:8000")
    print("Press Ctrl+C to stop the server.")
    print("=" * 65)
    uvicorn.run("api.index:app", host="127.0.0.1", port=8000, reload=True)
