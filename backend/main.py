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
async def proxy_master(request: Request):
    """Busca a playlist principal da rádio com depuração aprimorada"""
    async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "*/*",
            "Connection": "keep-alive"
        }
        
        range_header = request.headers.get("range")
        if range_header:
            headers["Range"] = range_header

        try:
            # Tenta a URL principal
            print(f"DEBUG: Tentando acessar {RADIO_URL}")
            resp = await client.get(RADIO_URL, headers=headers)
            
            # Fallback se der 404
            if resp.status_code == 404:
                fallback_url = RADIO_URL.replace("/playlist.m3u8", "")
                print(f"DEBUG: 404 detectado, tentando fallback: {fallback_url}")
                resp = await client.get(fallback_url, headers=headers)

            if resp.status_code >= 400:
                print(f"DEBUG: Erro do servidor da rádio: {resp.status_code}")
                return Response(content=f"Erro no servidor da rádio: {resp.status_code}", status_code=resp.status_code)

            # Verifica o tipo de conteúdo
            content_type = resp.headers.get("content-type", "").lower()
            content = resp.text
            
            # Se for um stream direto (MP3/AAC) ou se não houver tags de playlist
            if "#EXTM3U" not in content:
                print(f"DEBUG: Detectado stream direto (não HLS). Type: {content_type}")
                return StreamingResponse(
                    iter([resp.content]),
                    status_code=resp.status_code,
                    media_type=content_type or "audio/mpeg",
                    headers={
                        "Access-Control-Allow-Origin": "*",
                        "Accept-Ranges": "bytes",
                        "Content-Range": resp.headers.get("Content-Range", ""),
                        "Content-Length": resp.headers.get("Content-Length", ""),
                        "Cache-Control": "no-cache"
                    }
                )

            # É HLS - Reescreve com inteligência
            print("DEBUG: Detectada playlist HLS. Reescrevendo links...")
            lines = content.splitlines()
            new_lines = []
            for line in lines:
                line = line.strip()
                if not line: continue
                
                if not line.startswith("#"):
                    if line.startswith("http"):
                        # URL absoluta - encadeia no proxy
                        new_lines.append(f"/stream/segment?url={line}")
                    else:
                        # URL relativa - limpa barras extras e monta
                        clean_path = line.lstrip('/')
                        full_url = f"{RADIO_BASE}{clean_path}"
                        new_lines.append(f"/stream/segment?url={full_url}")
                else:
                    new_lines.append(line)
            
            return Response(
                content="\n".join(new_lines), 
                media_type="application/vnd.apple.mpegurl",
                headers={
                    "Access-Control-Allow-Origin": "*",
                    "Cache-Control": "no-cache",
                    "X-Debug-Source": "HLS-Proxy"
                }
            )
        except Exception as e:
            print(f"DEBUG: Erro crítico no Proxy Master: {str(e)}")
            return Response(content=f"Error: {str(e)}", status_code=500)

@app.get("/stream/segment")
async def proxy_segment(url: str, request: Request):
    """Proxy para segmentos com streaming em tempo real"""
    async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "*/*"
        }
        
        range_header = request.headers.get("range")
        if range_header:
            headers["Range"] = range_header
        
        try:
            # Usa stream para não carregar arquivos grandes na memória
            async def generate_stream():
                async with client.stream("GET", url, headers=headers) as resp:
                    # Se for outra playlist dentro do segmento (HLS multinível)
                    if "mpegurl" in resp.headers.get("content-type", "").lower():
                        # Este caso é raro em segmentos, mas tratamos
                        data = await resp.aread()
                        yield data
                        return

                    async for chunk in resp.aiter_bytes(chunk_size=8192):
                        yield chunk

            # Precisamos saber o content-type antes de iniciar o StreamingResponse
            # Fazemos um HEAD rápido ou apenas uma requisição parcial
            resp_head = await client.head(url, headers=headers)
            final_content_type = resp_head.headers.get("content-type", "video/MP2T")

            return StreamingResponse(
                generate_stream(),
                status_code=resp_head.status_code,
                media_type=final_content_type,
                headers={
                    "Access-Control-Allow-Origin": "*",
                    "Accept-Ranges": "bytes",
                    "Content-Range": resp_head.headers.get("Content-Range", ""),
                    "Content-Length": resp_head.headers.get("Content-Length", ""),
                    "Cache-Control": "max-age=3600"
                }
            )
        except Exception as e:
            print(f"DEBUG: Erro no segmento {url}: {str(e)}")
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
