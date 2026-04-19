from fastapi import FastAPI, Response, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
import os
import httpx
import re
import asyncio
from contextlib import asynccontextmanager

# Cliente HTTP Global para reutilizar conexões e evitar erros 502/Timeout
http_client = httpx.AsyncClient(
    timeout=httpx.Timeout(30.0, connect=10.0),
    follow_redirects=True,
    limits=httpx.Limits(max_connections=100, max_keepalive_connections=20)
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await http_client.aclose()

app = FastAPI(lifespan=lifespan)

# Configuração de CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# URLs da rádio (Link 01 e Link 02)
STREAMS = {
    "link01": "http://45.224.108.166:1923/BZCWmdKZy2GZnJeYodiZ/720p/chunks.m3u8",
    "link02": "http://45.224.108.166:1923/BZCWmdKZy2GZnJeYodiZ/a/playlist.m3u8"
}

@app.get("/api/health")
def health_check():
    return {"status": "ok", "radio": "VICFM 91.5"}

# Proxy de Áudio Universal
@app.get("/stream/playlist.m3u8")
async def proxy_master(request: Request, server: str = "link01"):
    """Busca o stream da rádio com suporte a múltiplos servidores e correção de base_url"""
    target_url = STREAMS.get(server, STREAMS["link01"])
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "*/*"
    }
    
    try:
        resp = await http_client.get(target_url, headers=headers)
        
        if resp.status_code >= 400:
            return Response(content=f"Erro no servidor {server}: {resp.status_code}", status_code=resp.status_code)

        # Se for HLS
        if b"#EXTM3U" in resp.content[:100]:
            content = resp.text
            lines = content.splitlines()
            new_lines = []
            
            # Base URL real retornada pelo servidor (fundamental para o Link 02)
            # O Link 02 tem uma estrutura diferente do Link 01
            current_resp_url = str(resp.url)
            base_url = current_resp_url.rsplit('/', 1)[0] + "/"
            
            for line in lines:
                line = line.strip()
                if line and not line.startswith("#"):
                    if not line.startswith("http"):
                        # Resolve o link relativo com base na URL de onde a playlist veio
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
        
        # Stream Direto
        async def direct_streamer():
            async with http_client.stream("GET", str(resp.url), headers=headers) as s:
                async for chunk in s.aiter_bytes(chunk_size=16384):
                    yield chunk

        return StreamingResponse(
            direct_streamer(),
            media_type=resp.headers.get("content-type", "audio/mpeg"),
            headers={"Access-Control-Allow-Origin": "*", "Accept-Ranges": "bytes"}
        )
    except Exception as e:
        return Response(content=f"Erro: {str(e)}", status_code=500)

@app.get("/stream/segment")
async def proxy_segment(url: str, request: Request):
    """Proxy otimizado para segmentos"""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "*/*"
    }
    
    try:
        # Iniciamos o stream diretamente para economizar tempo e evitar 502
        async def generate_stream():
            async with http_client.stream("GET", url, headers=headers) as resp:
                async for chunk in resp.aiter_bytes(chunk_size=16384):
                    yield chunk

        # Fazemos apenas uma requisição para pegar o tipo de conteúdo e iniciar o stream
        # Nota: StreamingResponse aceita um gerador assíncrono
        return StreamingResponse(
            generate_stream(),
            media_type="video/MP2T", # Padrão para segmentos HLS
            headers={
                "Access-Control-Allow-Origin": "*",
                "Accept-Ranges": "bytes",
                "Cache-Control": "max-age=3600"
            }
        )
    except Exception as e:
        return Response(content=str(e), status_code=404)

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
