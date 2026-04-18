from fastapi import FastAPI, Response, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
import os
import httpx
import re

app = FastAPI()

# Configuração de CORS para permitir acesso do player
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# URL Completa da rádio (HLS)
RADIO_URL = "http://45.224.108.166:1923/BZCWmdKZy2GZnJeYodiZ/a/playlist.m3u8"
# Base da URL para os segmentos (.ts)
RADIO_BASE = "http://45.224.108.166:1923/BZCWmdKZy2GZnJeYodiZ/a/"

@app.get("/api/health")
def health_check():
    return {"status": "ok", "radio": "VICFM 91.5"}

# Proxy de Áudio
@app.get("/stream/playlist.m3u8")
async def proxy_master():
    """Busca a playlist principal da rádio"""
    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "*/*"
        }
        try:
            resp = await client.get(RADIO_URL, headers=headers)
            
            # Se der 404 na playlist.m3u8, tenta o link direto '.../a'
            if resp.status_code == 404:
                resp = await client.get(RADIO_URL.replace("/playlist.m3u8", ""), headers=headers)

            if resp.status_code >= 400:
                return Response(content=f"Erro no servidor da rádio: {resp.status_code}", status_code=resp.status_code)

            content = resp.text
            
            if "#EXTM3U" not in content:
                return Response(
                    content=resp.content, 
                    media_type=resp.headers.get("content-type", "audio/mpeg"),
                    headers={"Access-Control-Allow-Origin": "*"}
                )

            # Reescreve os links
            lines = content.splitlines()
            new_lines = []
            for line in lines:
                line = line.strip()
                if line and not line.startswith("#"):
                    if not line.startswith("http"):
                        # Se RADIO_URL é .../a/playlist.m3u8, o segmento está em .../a/segmento.ts
                        full_segment_url = f"{RADIO_BASE}{line}"
                        new_lines.append(f"/stream/segment?url={full_segment_url}")
                    else:
                        new_lines.append(f"/stream/segment?url={line}")
                else:
                    new_lines.append(line)
            
            return Response(
                content="\n".join(new_lines), 
                media_type="application/vnd.apple.mpegurl",
                headers={"Cache-Control": "no-cache"}
            )
        except Exception as e:
            return Response(content=f"Error: {str(e)}", status_code=500)

@app.get("/stream/segment")
async def proxy_segment(url: str):
    """Busca um segmento individual (TS ou outra playlist)"""
    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "*/*"
        }
        
        try:
            resp = await client.get(url, headers=headers)
            
            # Se este segmento for na verdade outra playlist (HLS multinível)
            if "#EXTM3U" in resp.text[:100]:
                content = resp.text
                # A base para esta nova playlist é a URL dela mesma
                new_base = url.rsplit('/', 1)[0] + "/"
                
                lines = content.splitlines()
                new_lines = []
                for line in lines:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        if not line.startswith("http"):
                            new_lines.append(f"/stream/segment?url={new_base}{line}")
                        else:
                            new_lines.append(f"/stream/segment?url={line}")
                    else:
                        new_lines.append(line)
                return Response(content="\n".join(new_lines), media_type="application/vnd.apple.mpegurl")

            return Response(
                content=resp.content,
                media_type=resp.headers.get("content-type", "video/MP2T"),
                headers={
                    "Access-Control-Allow-Origin": "*",
                    "Cache-Control": "max-age=3600"
                }
            )
        except Exception as e:
            print(f"Proxy Segment Error: {str(e)}")
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
