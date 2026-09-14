import asyncio
import sys
import uvicorn

if __name__ == "__main__":
    loop_opt = "asyncio:SelectorEventLoop" if sys.platform == "win32" else "auto"
    uvicorn.run("src.main:app", host="127.0.0.1", port=8000, loop=loop_opt)
