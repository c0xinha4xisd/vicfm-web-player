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

# URL exata da rádio (Playlist Mestre)
RADIO_URL = "http://45.224.108.166:1923/BZCWmdKZy2GZnJeYodiZ/a/playlist.m3u8"

@app.get("/api/health")
def health_check():
    return {"status": "ok", "radio": "VICFM 91.5"}

# Proxy de Áudio Universal
@app.get("/stream/playlist.m3u8")
async def proxy_master(request: Request):
    """Busca o stream da rádio com múltiplas tentativas de URL"""
    async with httpx.AsyncClient(timeout=25.0, follow_redirects=True) as client:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "*/*",
            "Icy-MetaData": "1"
        }
        
        # Lista de URLs para tentar em ordem (baseada no novo link completo)
        urls_to_try = [
            RADIO_URL,
            RADIO_URL.replace("/playlist.m3u8", ""), # Tenta o link '.../a'
            RADIO_URL.replace("/a/playlist.m3u8", "/a") # Outra variação comum
        ]

        resp = None
        last_error = ""
        
        for url in urls_to_try:
            try:
                resp = await client.get(url, headers=headers)
                if resp.status_code < 400:
                    break
                last_error = f"Erro {resp.status_code} em {url}"
            except Exception as e:
                last_error = str(e)
                continue

        if not resp or resp.status_code >= 400:
            return Response(
                content=f"Fonte indisponível: {last_error}", 
                status_code=resp.status_code if resp else 500
            )

        # Se for HLS
        if b"#EXTM3U" in resp.content[:100]:
            content = resp.text
            lines = content.splitlines()
            new_lines = []
            
            # A base_url para links relativos agora é o diretório da playlist
            # Ex: de .../a/playlist.m3u8 para .../a/
            current_url = str(resp.url)
            base_url = current_url.rsplit('/', 1)[0] + "/"
            
            for line in lines:
                line = line.strip()
                if line and not line.startswith("#"):
                    if not line.startswith("http"):
                        # Resolve o link relativo de forma limpa
                        full_segment_url = base_url + line
                        new_lines.append(f"/stream/segment?url={full_segment_url}")
                    else:
                        new_lines.append(f"/stream/segment?url={line}")
                else:
                    new_lines.append(line)
            
            return Response(
                content="\n".join(new_lines),
                media_type="application/vnd.apple.mpegurl",
                headers={"Access-Control-Allow-Origin": "*", "Cache-Control": "no-cache"}
            )
        
        # Se for stream direto (MP3/AAC)
        async def direct_streamer():
            target_url = str(resp.url)
            async with client.stream("GET", target_url, headers=headers) as s:
                async for chunk in s.aiter_bytes(chunk_size=16384):
                    yield chunk

        return StreamingResponse(
            direct_streamer(),
            media_type=resp.headers.get("content-type", "audio/mpeg"),
            headers={
                "Access-Control-Allow-Origin": "*",
                "Accept-Ranges": "bytes",
                "Cache-Control": "no-cache",
                "Connection": "keep-alive"
            }
        )

@app.get("/stream/segment")
async def proxy_segment(url: str, request: Request):
    """Proxy para segmentos individuais com tratamento de erro 502"""
    async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "*/*"
        }
        
        try:
            # HEAD request primeiro para validar e pegar headers
            resp_head = await client.head(url, headers=headers)
            
            async def generate_stream():
                async with client.stream("GET", url, headers=headers) as resp:
                    async for chunk in resp.aiter_bytes(chunk_size=8192):
                        yield chunk

            return StreamingResponse(
                generate_stream(),
                status_code=resp_head.status_code,
                media_type=resp_head.headers.get("content-type", "video/MP2T"),
                headers={
                    "Access-Control-Allow-Origin": "*",
                    "Accept-Ranges": "bytes",
                    "Cache-Control": "max-age=3600"
                }
            )
        except Exception as e:
            # Em vez de crashar (502), retornamos uma mensagem limpa
            return Response(content=f"Erro no segmento: {str(e)}", status_code=404)

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
