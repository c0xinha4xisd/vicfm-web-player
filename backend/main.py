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

# URL da rádio
RADIO_URL = "http://45.224.108.166:1923/BZCWmdKZy2GZnJeYodiZ/a"

@app.get("/api/health")
def health_check():
    return {"status": "ok", "radio": "VICFM 91.5"}

# Proxy de Áudio Universal
@app.get("/stream/playlist.m3u8")
async def proxy_master(request: Request):
    """Busca o stream da rádio e decide se serve como HLS ou Stream Direto"""
    async with httpx.AsyncClient(timeout=25.0, follow_redirects=True) as client:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "*/*",
            "Accept-Encoding": "identity",
            "Icy-MetaData": "1"
        }
        
        try:
            # Tenta acessar a URL da rádio
            resp = await client.get(RADIO_URL, headers=headers)
            
            # Se der 404, tenta a variação com playlist.m3u8
            if resp.status_code == 404:
                resp = await client.get(f"{RADIO_URL}/playlist.m3u8", headers=headers)

            if resp.status_code >= 400:
                return Response(
                    content=f"Fonte da rádio indisponível (Erro {resp.status_code}). O servidor da rádio pode estar bloqueando acessos de fora do Brasil ou o link mudou.", 
                    status_code=resp.status_code
                )

            # Se for HLS
            if b"#EXTM3U" in resp.content[:100]:
                content = resp.text
                lines = content.splitlines()
                new_lines = []
                
                # A base_url para HLS deve ser o diretório pai do arquivo 'a'
                # Se a URL é .../BZCWmdKZy2GZnJeYodiZ/a, a base é .../BZCWmdKZy2GZnJeYodiZ/
                base_url = RADIO_URL.rsplit('/', 1)[0] + "/"
                
                for line in lines:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        if not line.startswith("http"):
                            # Tenta montar o link relativo ao pai
                            new_lines.append(f"/stream/segment?url={base_url}{line}")
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
                async with client.stream("GET", RADIO_URL, headers=headers) as s:
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
            
        except Exception as e:
            return Response(content=f"Erro de conexão: {str(e)}", status_code=500)

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
