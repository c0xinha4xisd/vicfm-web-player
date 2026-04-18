from fastapi import FastAPI, Response, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse
import os
import httpx
import re

app = FastAPI()

# Configurações do Stream
STREAM_BASE_URL = "http://45.224.108.166:1923/BZCWmdKZy2GZnJeYodiZ/a"
PLAYLIST_NAME = "playlist.m3u8"

@app.get("/api/health")
def health_check():
    return {"status": "ok", "radio": "VICFM 91.5"}

# Proxy de Áudio para evitar erros de Mixed Content (HTTP no HTTPS)
@app.get("/stream/playlist.m3u8")
async def proxy_playlist():
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(f"{STREAM_BASE_URL}/{PLAYLIST_NAME}")
            content = resp.text
            
            # Reescreve URLs relativas para passarem pelo nosso proxy
            # Se a linha não começar com # (comentário) e não for uma URL absoluta, é um segmento
            lines = content.splitlines()
            new_lines = []
            for line in lines:
                if line and not line.startswith("#"):
                    if not line.startswith("http"):
                        # É um segmento relativo, redireciona para o nosso proxy de segmento
                        new_lines.append(f"/stream/{line}")
                    else:
                        new_lines.append(line)
                else:
                    new_lines.append(line)
            
            return Response(content="\n".join(new_lines), media_type="application/vnd.apple.mpegurl")
        except Exception as e:
            return Response(content=f"Error: {str(e)}", status_code=500)

@app.get("/stream/{segment:path}")
async def proxy_segment(segment: str):
    async with httpx.AsyncClient() as client:
        # Repassa a requisição para o servidor original
        url = f"{STREAM_BASE_URL}/{segment}"
        
        # Streaming da resposta para economizar memória
        async def stream_response():
            async with client.stream("GET", url) as resp:
                async for chunk in resp.aiter_bytes():
                    yield chunk

        return StreamingResponse(stream_response(), media_type="video/MP2T")

# Servir arquivos estáticos do frontend (após o build)
# Note: No Docker, vamos copiar o build do frontend para uma pasta acessível.
# No container, a estrutura será /app/frontend/dist
frontend_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend/dist")

if os.path.exists(frontend_path):
    app.mount("/", StaticFiles(directory=frontend_path, html=True), name="static")
else:
    # Tenta um caminho alternativo se não encontrar (caso o main.py seja rodado de dentro da pasta backend)
    alt_frontend_path = os.path.join(os.getcwd(), "frontend/dist")
    if os.path.exists(alt_frontend_path):
        app.mount("/", StaticFiles(directory=alt_frontend_path, html=True), name="static")
    else:
        @app.get("/")
        def read_root():
            return {"message": "Backend rodando. O frontend ainda não foi construído ou não está na pasta /frontend/dist", "searched": [frontend_path, alt_frontend_path]}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
