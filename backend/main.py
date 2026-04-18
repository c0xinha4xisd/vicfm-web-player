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
@app.get("/stream/{path:path}")
async def proxy_stream(path: str):
    async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
        # Define o URL original da rádio
        target_url = f"{STREAM_BASE_URL}/{path}"
        
        # Headers para fingir que é um navegador comum
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": STREAM_BASE_URL
        }

        try:
            # Faz a requisição para o servidor original
            resp = await client.get(target_url, headers=headers)
            
            # Se for uma playlist (.m3u8), precisamos reescrever os links internos
            if path.endswith(".m3u8"):
                content = resp.text
                lines = content.splitlines()
                new_lines = []
                for line in lines:
                    if line and not line.startswith("#"):
                        if not line.startswith("http"):
                            # É um link relativo, redireciona para o nosso proxy
                            new_lines.append(f"/stream/{line}")
                        else:
                            # É um link absoluto, mantém como está
                            new_lines.append(line)
                    else:
                        new_lines.append(line)
                
                return Response(
                    content="\n".join(new_lines), 
                    media_type="application/vnd.apple.mpegurl",
                    headers={"Access-Control-Allow-Origin": "*"}
                )
            
            # Se for um segmento de áudio (.ts), faz o stream dos bytes diretamente
            media_type = "video/MP2T" if path.endswith(".ts") else resp.headers.get("content-type")
            
            return Response(
                content=resp.content,
                media_type=media_type,
                headers={"Access-Control-Allow-Origin": "*"}
            )
            
        except Exception as e:
            print(f"Proxy Error: {str(e)}")
            return Response(content=f"Error: {str(e)}", status_code=500)

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
