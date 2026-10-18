"""Start Crewboard with host/port from the environment (.env): python run.py"""
import uvicorn, config
if __name__ == "__main__":
    uvicorn.run("app:app", host=config.HOST, port=config.PORT, proxy_headers=True)
