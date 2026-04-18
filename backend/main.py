from fastapi import FastAPI, Response, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse
import os
import httpx
import re

app = FastAPI()

# Configuração da URL da rádio
# O usuário informou que este link funciona no VLC e 4G:
RADIO_URL = "http://45.224.108.166:1923/BZCWmdKZy2GZnJeYodiZ/a"

@app.get("/api/health")
def health_check():
    return {"status": "ok", "radio": "VICFM 91.5"}

# Proxy de Áudio
@app.get("/stream/playlist.m3u8")
async def proxy_master():
    """Busca a playlist principal da rádio"""
    async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        try:
            resp = await client.get(RADIO_URL, headers=headers)
            content = resp.text
            
            # Se o conteúdo não parecer uma playlist m3u8, mas a requisição deu certo,
            # pode ser que o servidor esteja retornando os bytes diretamente ou um redirect.
            if "#EXTM3U" not in content:
                # Se não for m3u8, servimos como stream direto
                return Response(content=resp.content, media_type=resp.headers.get("content-type", "audio/mpeg"))

            # Reescreve os links para passarem pelo nosso proxy de segmentos
            lines = content.splitlines()
            new_lines = []
            for line in lines:
                if line and not line.startswith("#"):
                    if not line.startswith("http"):
                        # Remove barras iniciais se existirem para evitar // no URL
                        clean_line = line.lstrip('/')
                        new_lines.append(f"/stream/segment?url={clean_line}")
                    else:
                        new_lines.append(f"/stream/segment?url={line}")
                else:
                    new_lines.append(line)
            
            return Response(
                content="\n".join(new_lines), 
                media_type="application/vnd.apple.mpegurl",
                headers={"Access-Control-Allow-Origin": "*"}
            )
        except Exception as e:
            return Response(content=f"Error: {str(e)}", status_code=500)

@app.get("/stream/segment")
async def proxy_segment(url: str):
    """Busca um segmento individual (TS ou outra playlist)"""
    async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
        # Se a URL não for completa, montamos com base na URL da rádio
        if not url.startswith("http"):
            # Pega a base da URL da rádio (removendo o 'a' final)
            base_url = RADIO_URL.rsplit('/', 1)[0]
            target_url = f"{base_url}/{url}"
        else:
            target_url = url

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        
        try:
            resp = await client.get(target_url, headers=headers)
            
            # Se este segmento for na verdade outra playlist (HLS multinível)
            if url.endswith(".m3u8") or "#EXTM3U" in resp.text[:100]:
                content = resp.text
                lines = content.splitlines()
                new_lines = []
                for line in lines:
                    if line and not line.startswith("#"):
                        new_lines.append(f"/stream/segment?url={line}")
                    else:
                        new_lines.append(line)
                return Response(content="\n".join(new_lines), media_type="application/vnd.apple.mpegurl")

            return Response(
                content=resp.content,
                media_type=resp.headers.get("content-type", "video/MP2T"),
                headers={"Access-Control-Allow-Origin": "*"}
            )
        except Exception as e:
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
